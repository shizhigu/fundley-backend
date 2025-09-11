# MotherDuck FastAPI Service

极简的FastAPI服务，用于执行MotherDuck SQL查询。

## 本地运行

1. 安装依赖：
```bash
pip install -r requirements.txt
```

2. 设置环境变量：
```bash
export MOTHERDUCK_TOKEN=your_token_here
```

3. 启动服务：
```bash
python main.py
```

服务运行在 http://localhost:8000

## API端点

### POST /query
执行SQL查询

请求体：
```json
{
  "sql": "SELECT * FROM your_table LIMIT 10"
}
```

响应：
```json
{
  "success": true,
  "data": [...],
  "row_count": 10,
  "error": ""
}
```

### GET /test
测试MotherDuck连接

### GET /
健康检查

## Railway部署

1. 在Railway中创建新项目
2. 连接到此代码仓库
3. 设置环境变量 `MOTHERDUCK_TOKEN`
4. 自动部署

## Docker本地测试

```bash
# 构建镜像
docker build -t motherduck-api .

# 运行容器
docker run -p 8000:8000 -e MOTHERDUCK_TOKEN=your_token motherduck-api
```