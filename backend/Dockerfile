# backend/Dockerfile (支持 MCP 扩展版)

FROM python:3.11-slim

# 1. 安装 uv
RUN pip install --no-cache-dir uv

# 2. 准备环境依赖
# --- 分层构建技巧：先复制依赖文件，利用 Docker 缓存 ---

WORKDIR /app

# 2.1 安装 Backend 依赖
COPY backend/pyproject.toml /app/backend/pyproject.toml
# 注意：这里显式指定路径安装
RUN uv pip install --system --no-cache -r /app/backend/pyproject.toml

# 2.2 安装 Bing MCP 依赖
# 如果未来有更多 MCP，可以在这里继续追加
COPY MCP_SERVER/bing/pyproject.toml /app/MCP_SERVER/bing/pyproject.toml
RUN uv pip install --system --no-cache -r /app/MCP_SERVER/bing/pyproject.toml

# 3. 复制源代码
# --- 此时依赖已安完，复制具体代码 ---

# 3.1 复制 Backend 代码
COPY backend /app/backend

# 3.2 复制 MCP 代码
COPY MCP_SERVER /app/MCP_SERVER

# 4. 设置 PYTHONPATH
# 确保 python 能找到 backend 模块，也能找到 MCP 模块（如果需要 import 的话）
ENV PYTHONPATH=/app

WORKDIR /app

# 5. 启动命令
CMD ["gunicorn", "-w", "1", "-k", "uvicorn.workers.UvicornWorker", "backend.main:app", "--bind", "0.0.0.0:8000"]
