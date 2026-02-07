@echo off
setlocal EnableDelayedExpansion
chcp 65001 >nul
title Mambo Chat Windows 一键启动器

echo ========================================================
echo          Mambo Chat Windows 智能启动助手
echo ========================================================

REM --- 1. 环境检测 ---
echo [1/6] 检测系统环境...

python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [错误] 未检测到 Python！请安装 Python 3.11+ 并勾选 "Add to PATH"。
    pause
    exit /b
)

node --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [错误] 未检测到 Node.js！前端编译和代理需要 Node 环境。
    echo 请访问 https://nodejs.org/ 下载安装 (LTS版本即可)。
    pause
    exit /b
)

REM --- 2. Python 后端环境准备 ---
echo [2/6] 准备后端 Python 环境...

if not exist "venv" (
    echo    - 创建虚拟环境...
    python -m venv venv
)

REM 激活虚拟环境
call venv\Scripts\activate

REM 检查 uv 是否安装
pip show uv >nul 2>&1
if %errorlevel% neq 0 (
    echo    - 安装 uv 包管理器...
    pip install uv -i https://pypi.tuna.tsinghua.edu.cn/simple
)

REM 安装后端依赖 (直接读取 pyproject.toml)
if not exist "venv\Lib\site-packages\installed_flag" (
    echo    - 正在安装/同步后端依赖 (这可能需要几分钟)...
    REM 安装 backend 依赖
    uv pip install -r backend/pyproject.toml -i https://pypi.tuna.tsinghua.edu.cn/simple
    REM 安装 MCP 依赖 (根据你的 Dockerfile)
    uv pip install -r MCP_SERVER/ddgs/pyproject.toml -i https://pypi.tuna.tsinghua.edu.cn/simple
    uv pip install -r MCP_SERVER/knowledge_base/pyproject.toml -i https://pypi.tuna.tsinghua.edu.cn/simple

    echo done > venv\Lib\site-packages\installed_flag
) else (
    echo    - 后端依赖已安装，跳过。
)

REM --- 3. 前端编译与准备 ---
echo [3/6] 准备前端环境...

cd frontend/mambo

if not exist "node_modules" (
    echo    - 安装前端依赖 (npm install)...
    call npm install
)

if not exist "dist" (
    echo    - 编译前端代码 (npm run build)...
    call npm run build
) else (
    echo    - 检测到 dist 目录，跳过编译。如需更新请手动删除 dist 目录。
)

cd ..\..

REM --- 4. 准备本地代理环境 ---
echo [4/6] 准备本地代理服务...

REM 在根目录安装运行 local_proxy.js 所需的轻量依赖
if not exist "node_modules" (
    echo    - 安装代理服务器依赖...
    call npm install express http-proxy-middleware connect-history-api-fallback --no-save --loglevel=error
)

REM --- 5. 设置环境变量并启动 ---
echo [5/6] 正在启动服务...

REM 设置 PYTHONPATH 确保 backend 模块能被找到
set PYTHONPATH=%cd%
REM 设置存储路径 (模拟 Docker volume)
if not exist "uploads" mkdir uploads
set STORAGE_PATH=%cd%\uploads
REM 设置数据库回显 (可选)
set DB_ECHO=False

REM --- 启动后端 (后台运行) ---
echo    - 启动 Python 后端 (Port 8000)...
start "Mambo Backend" /min cmd /c "call venv\Scripts\activate && python -m uvicorn backend.main:app --host 127.0.0.1 --port 8000 --workers 1"

REM --- 启动代理 (前台运行) ---
echo    - 启动 Node 代理 (Port 24911)...
echo.
echo [成功] 服务已启动！请保持此窗口打开。
echo [提示] 浏览器即将打开 http://localhost:24911

REM 延迟 3 秒等待后端就绪，然后打开浏览器
start "" cmd /c "timeout /t 3 >nul & start http://localhost:24911"

REM 启动代理服务器
node local_proxy.js
