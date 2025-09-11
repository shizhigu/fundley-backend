"""
极简FastAPI服务 - MotherDuck SQL查询
"""
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import duckdb
import os
import traceback
from typing import List, Dict, Any

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

if __name__ == "__main__":
    import uvicorn
    import os
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)