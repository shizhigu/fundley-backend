"""
极简FastAPI服务 - MotherDuck SQL查询 + 财务数据分析
"""
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import duckdb
import pandas as pd
import os
import traceback
import httpx
from typing import List, Dict, Any, Optional
from datetime import datetime

app = FastAPI(title="MotherDuck SQL API", version="1.0.0")

# CORS设置
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class QueryRequest(BaseModel):
    sql: str

class QueryResponse(BaseModel):
    success: bool
    data: List[Dict[str, Any]] = []
    row_count: int = 0
    error: str = ""

# 财务数据请求模型
class FinancialDataRequest(BaseModel):
    symbols: List[str]
    sqlFormulas: Dict[str, str]  # metricId -> SQL formula mapping
    quarters: int

# 财务数据响应模型
class FinancialDataResponse(BaseModel):
    symbol: str
    fiscalYear: int
    period: str
    date: Optional[str]
    metrics: Dict[str, Dict[str, Any]]

@app.get("/")
async def health_check():
    return {"status": "healthy", "service": "motherduck-api"}

@app.post("/query", response_model=QueryResponse)
async def execute_query(request: QueryRequest):
    """执行DuckDB SQL查询"""
    try:
        # 获取MotherDuck token
        motherduck_token = os.getenv("MOTHERDUCK_TOKEN")
        if not motherduck_token:
            raise HTTPException(status_code=500, detail="MOTHERDUCK_TOKEN environment variable not set")
        
        # 连接MotherDuck数据库
        # 格式: md:database_name 或 md:database_name.schema_name
        motherduck_db = os.getenv("MOTHERDUCK_DATABASE", "financial_db")
        connection_string = f"md:{motherduck_db}?motherduck_token={motherduck_token}"
        
        conn = duckdb.connect(connection_string)
        
        # 执行SQL查询
        result = conn.execute(request.sql)
        rows = result.fetchall()
        
        # 获取列名
        columns = [desc[0] for desc in result.description] if result.description else []
        
        # 转换为字典格式
        data = []
        for row in rows:
            row_dict = {}
            for i, value in enumerate(row):
                if i < len(columns):
                    row_dict[columns[i]] = value
            data.append(row_dict)
        
        # 关闭连接
        conn.close()
        
        return QueryResponse(
            success=True,
            data=data,
            row_count=len(data)
        )
        
    except Exception as e:
        error_msg = str(e)
        print(f"❌ Query failed: {error_msg}")
        print(f"🔍 Traceback: {traceback.format_exc()}")
        
        return QueryResponse(
            success=False,
            error=error_msg
        )

@app.get("/test")
async def test_connection():
    """测试DuckDB连接"""
    try:
        motherduck_token = os.getenv("MOTHERDUCK_TOKEN")
        if not motherduck_token:
            return {"success": False, "error": "MOTHERDUCK_TOKEN not set"}
        
        # 连接MotherDuck数据库
        motherduck_db = os.getenv("MOTHERDUCK_DATABASE", "financial_db")
        connection_string = f"md:{motherduck_db}?motherduck_token={motherduck_token}"
        
        conn = duckdb.connect(connection_string)
        
        # 简单测试查询
        result = conn.execute("SELECT 42 as test_number, 'Hello MotherDuck' as test_message")
        rows = result.fetchall()
        conn.close()
        
        return {
            "success": True,
            "message": "MotherDuck connection successful",
            "test_result": rows[0] if rows else None
        }
        
    except Exception as e:
        return {
            "success": False,
            "error": str(e)
        }

# 财务数据处理函数
def build_dynamic_sql(symbols: List[str], sql_formulas: Dict[str, str], quarters: int) -> str:
    """构建动态SQL查询，使用窗口函数确保每个symbol都有正确的季度数"""
    # 基础字段
    base_fields = ["symbol", "fiscalyear", "period", "filingdate", "date"]

    # SQL公式字段
    formula_fields = list(sql_formulas.values())

    # 构建WITH子句使用窗口函数
    # 在WITH子句中先选择所有字段，然后计算公式
    sql = f"""
    WITH ranked_data AS (
        SELECT *,
               {', '.join(formula_fields)},
               ROW_NUMBER() OVER (
                   PARTITION BY symbol
                   ORDER BY fiscalyear DESC, period DESC
               ) as rn
        FROM financial_statements
        WHERE symbol IN ({', '.join([f"'{s}'" for s in symbols])})
          AND period IN ('Q1', 'Q2', 'Q3', 'Q4')
    )
    SELECT {', '.join(base_fields)}, {', '.join(formula_fields)}
    FROM ranked_data
    WHERE rn <= {quarters}
    ORDER BY symbol, fiscalyear DESC, period DESC
    """

    return sql

def calculate_trends(df: pd.DataFrame, sql_formulas: Dict[str, str]) -> pd.DataFrame:
    """计算同比环比增长率"""
    if df.empty:
        return df

    # 确保数据按时间排序
    df = df.sort_values(['symbol', 'fiscalyear', 'period'])

    # 从SQL公式中提取字段名（AS后面的部分）
    metric_fields = []
    for sql_formula in sql_formulas.values():
        if ' AS ' in sql_formula:
            field_name = sql_formula.split(' AS ')[-1].strip()
            metric_fields.append(field_name)

    for metric in metric_fields:
        if metric in df.columns:
            # 环比 (QoQ) - 与上一季度比较
            df[f'{metric}_qoq'] = df.groupby('symbol')[metric].pct_change() * 100

            # 同比 (YoY) - 与去年同期比较 (lag 4 quarters)
            df[f'{metric}_yoy'] = df.groupby(['symbol', 'period'])[metric].pct_change() * 100

    return df

def format_for_frontend(df: pd.DataFrame, sql_formulas: Dict[str, str]) -> List[FinancialDataResponse]:
    """格式化为前端友好的JSON结构"""
    result = []

    # 从SQL公式中提取字段名（AS后面的部分）
    metric_fields = []
    for sql_formula in sql_formulas.values():
        if ' AS ' in sql_formula:
            field_name = sql_formula.split(' AS ')[-1].strip()
            metric_fields.append(field_name)

    for _, row in df.iterrows():
        record = {
            'symbol': row['symbol'],
            'fiscalYear': int(row['fiscalyear']) if pd.notna(row['fiscalyear']) else 0,
            'period': row['period'] if pd.notna(row['period']) else '',
            'date': row['date'].isoformat() if pd.notna(row['date']) else None,
            'metrics': {}
        }

        # 处理每个指标，使用AS后面的字段名作为key
        for metric in metric_fields:
            if metric in df.columns:
                qoq_col = f'{metric}_qoq'
                yoy_col = f'{metric}_yoy'

                # 获取QoQ和YoY值
                qoq_value = row[qoq_col] if qoq_col in df.columns and pd.notna(row[qoq_col]) else None
                yoy_value = row[yoy_col] if yoy_col in df.columns and pd.notna(row[yoy_col]) else None

                record['metrics'][metric] = {
                    'value': float(row[metric]) if pd.notna(row[metric]) else None,
                    'qoq': {
                        'value': float(qoq_value) if qoq_value is not None else None,
                        'direction': 'up' if qoq_value and qoq_value > 0 else 'down'
                    },
                    'yoy': {
                        'value': float(yoy_value) if yoy_value is not None else None,
                        'direction': 'up' if yoy_value and yoy_value > 0 else 'down'
                    }
                }

        result.append(record)

    return result

@app.post("/financial-data")
async def get_financial_data(request: FinancialDataRequest):
    """获取财务数据并计算同比环比"""
    try:
        print(f"📊 Processing request: {len(request.symbols)} symbols, {len(request.sqlFormulas)} SQL formulas, {request.quarters} quarters")

        # 获取MotherDuck连接
        motherduck_token = os.getenv("MOTHERDUCK_TOKEN")
        if not motherduck_token:
            raise HTTPException(status_code=500, detail="MOTHERDUCK_TOKEN environment variable not set")

        motherduck_db = os.getenv("MOTHERDUCK_DATABASE", "financial_db")
        connection_string = f"md:{motherduck_db}?motherduck_token={motherduck_token}"

        # 1. 构建动态SQL（使用SQL公式）
        sql = build_dynamic_sql(request.symbols, request.sqlFormulas, request.quarters)
        print(f"🔍 Generated SQL:\n{sql}")

        # 2. 执行SQL查询
        conn = duckdb.connect(connection_string)
        df = conn.execute(sql).df()
        conn.close()

        print(f"📈 Retrieved {len(df)} rows from database")

        if df.empty:
            print("⚠️  No data found for given criteria")
            return []

        # 3. 计算同比环比
        df_with_trends = calculate_trends(df, request.sqlFormulas)
        print(f"🧮 Calculated trends for {len(request.sqlFormulas)} metrics")

        # 4. 格式化为前端格式
        result = format_for_frontend(df_with_trends, request.sqlFormulas)
        print(f"✅ Formatted {len(result)} records for frontend")

        return result

    except Exception as e:
        error_msg = str(e)
        print(f"❌ Financial data processing failed: {error_msg}")
        print(f"🔍 Traceback: {traceback.format_exc()}")

        raise HTTPException(
            status_code=500,
            detail=f"Failed to process financial data: {error_msg}"
        )

if __name__ == "__main__":
    import uvicorn
    import os
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)