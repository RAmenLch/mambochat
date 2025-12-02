# backend/Dockerfile

# 使用官方 Python 3.11 slim 镜像作为基础
FROM python:3.11-slim

# 1. 安装 uv
RUN pip install --no-cache-dir uv

# 2. 设置工作目录为 /app/backend
# 这样我们可以直接复制文件到正确的位置
WORKDIR /app/backend

# 3. 复制 pyproject.toml 并安装依赖
# 这是利用层缓存的关键。只要 pyproject.toml 不变，这一层就会被缓存。
COPY pyproject.toml .

# --- 修正点 ---
# 使用 uv 安装 pyproject.toml 中定义的依赖。
# `.` 代表当前目录，uv 会自动寻找 pyproject.toml 并安装其定义的项目依赖。
RUN uv pip install --system --no-cache .

# 4. 复制应用代码
# 将宿主机的 backend/ 目录内容复制到容器的 /app/backend/ 目录
COPY . .

# 5. 将工作目录切换回 /app
# 这是为了让 gunicorn 的启动命令能正确解析 `backend.main:app`
WORKDIR /app

# 启动命令：
# 从 /app 目录启动，告诉 gunicorn 运行 backend 包里的 main 模块的 app 实例
# 这就解决了相对导入的问题
CMD ["gunicorn", "-w", "1", "-k", "uvicorn.workers.UvicornWorker", "backend.main:app", "--bind", "0.0.0.0:8000"]
