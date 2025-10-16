# backend/Dockerfile

# --- Stage 1: Build Stage ---
# 使用官方 Python 3.11 slim 镜像作为基础
FROM python:3.11-slim

# 设置工作目录
WORKDIR /app

# 复制依赖文件
COPY requirements.txt .

# 安装依赖，使用 --no-cache-dir 减小镜像体积
RUN pip install --no-cache-dir -r requirements.txt

# 复制所有后端代码到工作目录
COPY . .

# --- Gunicorn 启动命令 ---
# -w 4: 启动 4 个工作进程 (可根据 CPU 核心数调整, 推荐 2 * cores + 1)
# -k uvicorn.workers.UvicornWorker: 使用 Uvicorn 的 worker 类来运行 ASGI 应用
# backend.main:app: Gunicorn 要运行的应用实例
# --bind 0.0.0.0:8000: 监听容器内的 8000 端口
CMD ["gunicorn", "-w", "4", "-k", "uvicorn.workers.UvicornWorker", "main:app", "--bind", "0.0.0.0:8000"]
