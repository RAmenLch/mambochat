# backend/Dockerfile

# 使用官方 Python 3.11 slim 镜像作为基础
FROM python:3.11-slim

# 设置工作目录为 /app
# 我们将从这个目录启动应用，这样 Python 就能找到 'backend' 包
WORKDIR /app

# 复制依赖文件到工作目录
COPY requirements.txt .

# 安装依赖
RUN pip install --no-cache-dir -r requirements.txt

# 将您本地 backend/ 目录下的所有内容，
# 复制到容器内 /app/backend/ 这个新目录中
COPY . ./backend/

# 启动命令：
# 从 /app 目录启动，告诉 gunicorn 运行 backend 包里的 main 模块的 app 实例
# 这就解决了相对导入的问题
CMD ["gunicorn", "-w", "4", "-k", "uvicorn.workers.UvicornWorker", "backend.main:app", "--bind", "0.0.0.0:8000"]
