# Render 部署指南

## 快速部署到Render

### 方式1: 使用Blueprint (推荐)

1. 确保项目推送到GitHub
2. 访问 [render.com](https://render.com)
3. 点击 "New" → "Blueprint" 
4. 连接GitHub仓库并选择 `fundley-app`
5. Render会自动检测到 `render.yaml` 配置文件
6. 点击 "Apply" 开始部署

### 方式2: 手动创建Web Service

1. 登录 [render.com](https://render.com)
2. 点击 "New" → "Web Service"
3. 连接GitHub仓库选择 `fundley-app`
4. 配置以下设置：

```
Name: motherduck-api
Root Directory: motherduck-api
Environment: Python 3
Build Command: pip install -r requirements.txt  
Start Command: uvicorn main:app --host 0.0.0.0 --port $PORT
Plan: Free
```

### 设置环境变量

在Render项目设置 → Environment 添加：

```
Key: MOTHERDUCK_TOKEN
Value: 你的MotherDuck令牌
```

## Render vs 其他平台对比

| 特性 | Render | Railway | Fly.io |
|------|--------|---------|--------|
| 免费额度 | 750小时/月 | $5 credit/月 | 3个小应用 |
| 部署速度 | 快 | 很快 | 中等 |
| 配置复杂度 | 简单 | 最简单 | 中等 |
| 自定义域名 | ✅ 免费 | ✅ 免费 | ✅ 免费 |
| 自动休眠 | ✅ | ❌ | ❌ |

## Render特有优化

### 1. 避免冷启动
Render免费版会休眠，第一次请求可能较慢。可以设置ping服务保持活跃：

```python
# 在main.py中添加启动事件
from fastapi import BackgroundTasks
import asyncio
import httpx

@app.on_event("startup")
async def startup_event():
    # 可选: 添加预热逻辑
    pass
```

### 2. 健康检查优化
Render会定期检查健康状态，确保 `/` 端点快速响应：

```python
@app.get("/")
async def health_check():
    return {"status": "healthy", "service": "motherduck-api"}
```

## 部署验证

部署成功后，Render会提供URL，格式如：
`https://motherduck-api-xxxx.onrender.com`

测试命令：
```bash
# 健康检查
curl https://your-app.onrender.com/

# 连接测试
curl https://your-app.onrender.com/test

# SQL查询
curl -X POST https://your-app.onrender.com/query \
  -H "Content-Type: application/json" \
  -d '{"sql": "SELECT 42 as test, CURRENT_TIMESTAMP as now"}'
```

## 故障排除

### 常见问题

1. **构建失败**
   ```
   解决: 检查requirements.txt中的包版本
   确保Python版本兼容 (默认3.11)
   ```

2. **启动超时**
   ```
   解决: 检查start command是否正确
   uvicorn main:app --host 0.0.0.0 --port $PORT
   ```

3. **MotherDuck连接失败**
   ```
   解决: 验证环境变量MOTHERDUCK_TOKEN设置正确
   检查token权限和有效性
   ```

### 查看日志
在Render dashboard → Logs 查看实时日志：
```
Building...
==> Installing dependencies
==> Starting service
INFO: Started server process
INFO: Uvicorn running on http://0.0.0.0:10000
```

## 性能优化

### 1. 连接池
对于高频查询，可以实现连接池：

```python
class ConnectionPool:
    def __init__(self):
        self.connections = {}
    
    def get_connection(self, token: str):
        if token not in self.connections:
            conn = duckdb.connect()
            conn.execute("INSTALL motherduck;")
            conn.execute("LOAD motherduck;") 
            conn.execute(f"SET motherduck_token='{token}';")
            self.connections[token] = conn
        return self.connections[token]
```

### 2. 查询缓存
对于重复查询，添加简单缓存：

```python
from functools import lru_cache
import hashlib

@lru_cache(maxsize=100)
def cached_query(sql_hash: str, sql: str):
    # 执行查询逻辑
    pass
```

## 成本考虑

- **免费层限制**: 750小时/月 (约31天 × 24小时)
- **休眠机制**: 15分钟无请求后休眠
- **唤醒时间**: 冷启动约10-30秒

**建议**: 对于开发和小规模使用，Render免费层完全足够。

## 监控建议

1. **UptimeRobot** - 免费监控服务状态
2. **内置健康检查** - Render自动监控
3. **日志分析** - 通过Render dashboard查看

部署后记得测试你的NVDA ROCE查询，应该会比WASM版本快很多！