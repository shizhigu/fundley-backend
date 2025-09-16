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
import asyncio
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
def build_single_symbol_sql(symbol: str, sql_formulas: Dict[str, str], quarters: int) -> str:
    """为单个symbol构建SQL查询"""
    # 基础字段
    base_fields = ["symbol", "fiscalyear", "period", "filingdate", "date"]

    # SQL公式字段
    formula_fields = list(sql_formulas.values())

    # 构建简单的SQL查询
    # 为了计算YoY和QoQ，需要额外的历史数据
    # YoY需要前4个季度，QoQ需要前1个季度，所以多取4个季度的数据
    extra_quarters = 4
    total_limit = quarters + extra_quarters

    sql = f"""
    SELECT {', '.join(base_fields)}, {', '.join(formula_fields)}
    FROM financial_statements
    WHERE symbol = '{symbol}'
      AND period IN ('Q1', 'Q2', 'Q3', 'Q4')
    ORDER BY fiscalyear DESC,
             CASE period
                WHEN 'Q4' THEN 1
                WHEN 'Q3' THEN 2
                WHEN 'Q2' THEN 3
                WHEN 'Q1' THEN 4
                ELSE 5
             END ASC
    LIMIT {total_limit}
    """

    return sql

async def query_single_symbol_async(symbol: str, sql_formulas: Dict[str, str], quarters: int, connection_string: str) -> pd.DataFrame:
    """异步查询单个symbol的数据"""
    try:
        # 为每个symbol创建独立连接
        conn = duckdb.connect(connection_string)
        sql = build_single_symbol_sql(symbol, sql_formulas, quarters)
        print(f"🔍 Querying {symbol}: {sql[:100]}...")

        # 在线程池中执行SQL查询
        def execute_query():
            return conn.execute(sql).df()

        # 使用asyncio的线程池执行阻塞操作
        loop = asyncio.get_event_loop()
        df = await loop.run_in_executor(None, execute_query)

        conn.close()

        if not df.empty:
            print(f"✅ {symbol}: {len(df)} records")
            return df
        else:
            print(f"⚠️  {symbol}: No data found")
            return pd.DataFrame()

    except Exception as e:
        print(f"❌ Error querying {symbol}: {e}")
        return pd.DataFrame()

async def execute_multi_symbol_query_async(symbols: List[str], sql_formulas: Dict[str, str], quarters: int, connection_string: str) -> pd.DataFrame:
    """异步执行多个symbol的查询并合并结果"""
    print(f"🚀 Starting async queries for {len(symbols)} symbols")

    # 创建所有查询任务
    tasks = [
        query_single_symbol_async(symbol, sql_formulas, quarters, connection_string)
        for symbol in symbols
    ]

    # 并行执行所有查询
    dataframes = await asyncio.gather(*tasks, return_exceptions=True)

    # 过滤出成功的结果
    all_dataframes = []
    for i, df in enumerate(dataframes):
        if isinstance(df, pd.DataFrame) and not df.empty:
            all_dataframes.append(df)
        elif isinstance(df, Exception):
            print(f"❌ Exception for {symbols[i]}: {df}")

    # 合并所有数据
    if all_dataframes:
        combined_df = pd.concat(all_dataframes, ignore_index=True)

        # 添加period排序辅助列
        period_order = {'Q4': 1, 'Q3': 2, 'Q2': 3, 'Q1': 4}
        combined_df['period_order'] = combined_df['period'].map(period_order)

        # 排序：按symbol分组，每组内按时间倒序（最新在前）
        combined_df = combined_df.sort_values(['symbol', 'fiscalyear', 'period_order'], ascending=[True, False, True])

        # 删除辅助列
        combined_df = combined_df.drop('period_order', axis=1)

        print(f"📊 Combined result: {len(combined_df)} total records")
        return combined_df
    else:
        print("❌ No data found for any symbols")
        return pd.DataFrame()

def execute_multi_symbol_query(symbols: List[str], sql_formulas: Dict[str, str], quarters: int, conn) -> pd.DataFrame:
    """同步版本的多symbol查询（保留作为备用）"""
    all_dataframes = []

    for symbol in symbols:
        try:
            sql = build_single_symbol_sql(symbol, sql_formulas, quarters)
            print(f"🔍 Querying {symbol}: {sql[:100]}...")

            df = conn.execute(sql).df()
            if not df.empty:
                print(f"✅ {symbol}: {len(df)} records")
                all_dataframes.append(df)
            else:
                print(f"⚠️  {symbol}: No data found")

        except Exception as e:
            print(f"❌ Error querying {symbol}: {e}")
            continue

    # 合并所有数据
    if all_dataframes:
        combined_df = pd.concat(all_dataframes, ignore_index=True)

        # 添加period排序辅助列
        period_order = {'Q4': 1, 'Q3': 2, 'Q2': 3, 'Q1': 4}
        combined_df['period_order'] = combined_df['period'].map(period_order)

        # 排序：按symbol分组，每组内按时间倒序（最新在前）
        combined_df = combined_df.sort_values(['symbol', 'fiscalyear', 'period_order'], ascending=[True, False, True])

        # 删除辅助列
        combined_df = combined_df.drop('period_order', axis=1)

        print(f"📊 Combined result: {len(combined_df)} total records")
        return combined_df
    else:
        print("❌ No data found for any symbols")
        return pd.DataFrame()

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

        # 1. 执行多symbol查询（使用异步拆分方案）
        df = await execute_multi_symbol_query_async(request.symbols, request.sqlFormulas, request.quarters, connection_string)

        print(f"📈 Retrieved {len(df)} rows from database")

        if df.empty:
            print("⚠️  No data found for given criteria")
            return []

        # 3. 计算同比环比
        df_with_trends = calculate_trends(df, request.sqlFormulas)
        print(f"🧮 Calculated trends for {len(request.sqlFormulas)} metrics")

        # 4. 只保留前端需要的季度数（去掉用于计算趋势的额外数据）
        def filter_latest_quarters(group):
            # 按时间倒序排序，然后取前request.quarters个
            sorted_group = group.sort_values(['fiscalyear', 'period_order'], ascending=[False, True])
            return sorted_group.head(request.quarters)

        # 添加period排序辅助列进行筛选
        period_order = {'Q4': 1, 'Q3': 2, 'Q2': 3, 'Q1': 4}
        df_with_trends['period_order'] = df_with_trends['period'].map(period_order)

        # 按symbol分组，每组只保留最新的quarters个季度
        df_filtered = df_with_trends.groupby('symbol').apply(filter_latest_quarters).reset_index(drop=True)

        # 删除辅助列
        df_filtered = df_filtered.drop('period_order', axis=1)

        print(f"🔽 Filtered to {len(df_filtered)} records for frontend (showing latest {request.quarters} quarters per symbol)")

        # 5. 格式化为前端格式
        result = format_for_frontend(df_filtered, request.sqlFormulas)
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