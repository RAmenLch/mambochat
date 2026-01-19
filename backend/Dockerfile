# backend/Dockerfile (支持 MCP 扩展版)

# 使用清华大学的镜像源，你也可以换成其他的，比如：
# 阿里云: https://mirrors.aliyun.com/pypi/simple/
# 豆瓣: http://pypi.douban.com/simple/
FROM python:3.11-slim
ARG PYPI_INDEX_URL=https://pypi.tuna.tsinghua.edu.cn/simple

# 1. 安装 uv
RUN pip install --no-cache-dir uv -i  ${PYPI_INDEX_URL}

# 2. 准备环境依赖
WORKDIR /app

# 2.1 安装 Backend 依赖
COPY backend/pyproject.toml /app/backend/pyproject.toml
RUN uv pip install --system --no-cache -r /app/backend/pyproject.toml -i ${PYPI_INDEX_URL}

# 2.2 安装 Bing MCP 依赖 (这是超时的那一步)
COPY MCP_SERVER/ddgs/pyproject.toml /app/MCP_SERVER/ddgs/pyproject.toml
RUN uv pip install --system --no-cache -r /app/MCP_SERVER/ddgs/pyproject.toml -i ${PYPI_INDEX_URL}

# 3. 复制源代码
COPY backend /app/backend
COPY MCP_SERVER /app/MCP_SERVER

# 4. 设置 PYTHONPATH
ENV PYTHONPATH=/app

WORKDIR /app

# 5. 启动命令
CMD ["gunicorn", "-w", "1", "-k", "uvicorn.workers.UvicornWorker", "backend.main:app", "--bind", "0.0.0.0:8000"]
