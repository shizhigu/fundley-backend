# Python 3.11 slim镜像
FROM python:3.11-slim

# 设置工作目录
WORKDIR /app

# 安装系统依赖
RUN apt-get update && apt-get install -y \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# 复制requirements.txt
COPY requirements.txt .

# 安装Python依赖
RUN pip install --no-cache-dir -r requirements.txt

# 复制应用代码
COPY main.py .

# 暴露端口 (Railway会动态分配)
EXPOSE 8000

# 启动命令 (使用环境变量PORT)
CMD uvicorn main:app --host 0.0.0.0 --port ${PORT:-8000}