# Railway 部署指南

## 快速部署步骤

### 1. 准备代码
确保所有文件都在 `motherduck-api` 文件夹中：
- `main.py` - FastAPI应用
- `requirements.txt` - Python依赖
- `Dockerfile` - Docker配置
- `railway.toml` - Railway配置

### 2. Railway部署

1. 访问 [railway.app](https://railway.app)
2. 使用GitHub账号登录
3. 点击 "New Project" → "Deploy from GitHub repo"
4. 选择你的fundley-app仓库
5. 在Root Directory中输入: `motherduck-api`
6. 点击 "Deploy"

### 3. 设置环境变量

在Railway项目设置中添加：
```
MOTHERDUCK_TOKEN=你的MotherDuck令牌
```

### 4. 验证部署

部署完成后，Railway会提供一个URL，例如：
`https://your-app-name-production.up.railway.app`

测试API：
```bash
# 健康检查
curl https://your-app-name-production.up.railway.app/

# 连接测试
curl https://your-app-name-production.up.railway.app/test

# SQL查询测试
curl -X POST https://your-app-name-production.up.railway.app/query \
  -H "Content-Type: application/json" \
  -d '{"sql": "SELECT 1 as test"}'
```

## 其他部署选项

### Fly.io
```bash
# 安装flyctl
curl -L https://fly.io/install.sh | sh

# 登录并部署
fly auth login
fly launch
fly deploy
```

### Render
1. 连接GitHub仓库
2. 选择 "Web Service"
3. Root Directory: `motherduck-api`
4. Build Command: `pip install -r requirements.txt`
5. Start Command: `uvicorn main:app --host 0.0.0.0 --port $PORT`

## 环境变量

| 变量名 | 描述 | 必需 |
|--------|------|------|
| `MOTHERDUCK_TOKEN` | MotherDuck访问令牌 | ✅ |
| `PORT` | 服务端口 (自动设置) | ❌ |

## 故障排除

### 常见问题

1. **DuckDB版本错误**
   - 确保requirements.txt中使用 `duckdb==1.3.2`

2. **MotherDuck连接失败**
   - 检查环境变量 `MOTHERDUCK_TOKEN` 是否正确设置
   - 确认token有效且有相应权限

3. **端口绑定问题**
   - 确保Dockerfile使用 `${PORT:-8000}` 动态端口

### 日志检查

Railway部署日志可在项目面板查看，常见启动日志：
```
INFO: Started server process
INFO: Waiting for application startup.
INFO: Application startup complete.
INFO: Uvicorn running on http://0.0.0.0:8000
```

## 成本估算

- **Railway**: 免费额度每月 $5 credit
- **Fly.io**: 免费额度足够小型应用
- **Render**: 免费层有750小时/月限制

推荐使用Railway，配置最简单且性能稳定。