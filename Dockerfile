FROM python:3.11-slim
WORKDIR /app
# 安装系统依赖
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc g++ && rm -rf /var/lib/apt/lists/*
# 安装 Python 依赖
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
# 复制后端代码
COPY server/ ./server/
# 复制前端构建产物 (需先在本地 npm run build)
COPY frontend/dist/ ./frontend/dist/
# 数据目录
RUN mkdir -p /app/data
VOLUME ["/app/data"]
EXPOSE 7860
# 仅后端模式 (无 PyWebView 窗口)
CMD ["python", "-m", "uvicorn", "server.main:app", "--host", "0.0.0.0", "--port", "7860"]
