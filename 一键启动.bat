@echo off
setlocal EnableDelayedExpansion
chcp 65001 >nul
title Mambo Chat - 全自动部署启动器

REM ================= 配置区域 =================
REM 定义下载版本
set "NODE_VERSION=v20.11.0"
set "NODE_URL=https://nodejs.org/dist/%NODE_VERSION%/node-%NODE_VERSION%-win-x64.zip"
REM uv 下载地址 (使用 latest release)
set "UV_URL=https://github.com/astral-sh/uv/releases/download/0.1.21/uv-x86_64-pc-windows-msvc.zip"

REM 定义本地工具目录
set "TOOLS_DIR=%~dp0bin"
set "NODE_DIR=%TOOLS_DIR%\node-%NODE_VERSION%-win-x64"
set "UV_EXE=%TOOLS_DIR%\uv.exe"

REM 创建工具目录
if not exist "%TOOLS_DIR%" mkdir "%TOOLS_DIR%"

echo.
echo ========================================================
echo          Mambo Chat Windows 全自动部署脚本
echo ========================================================
echo.

REM ================= 1. 环境检测与自动下载 =================

REM --- 1.1 检查/下载 uv ---
if not exist "%UV_EXE%" (
    echo [1/5] 正在下载 uv (Python 包管理器)...
    powershell -Command "Invoke-WebRequest -Uri '%UV_URL%' -OutFile '%TOOLS_DIR%\uv.zip'"
    if !errorlevel! neq 0 ( echo [错误] uv 下载失败，请检查网络。 & pause & exit /b )

    echo [1/5] 解压 uv...
    powershell -Command "Expand-Archive -Path '%TOOLS_DIR%\uv.zip' -DestinationPath '%TOOLS_DIR%' -Force"
    del "%TOOLS_DIR%\uv.zip"
) else (
    echo [1/5] uv 已安装。
)

REM --- 1.2 检查/下载 Node.js ---
if not exist "%NODE_DIR%\node.exe" (
    echo [2/5] 正在下载 Node.js (前端运行环境)...
    echo 下载地址: %NODE_URL%
    powershell -Command "Invoke-WebRequest -Uri '%NODE_URL%' -OutFile '%TOOLS_DIR%\node.zip'"
    if !errorlevel! neq 0 ( echo [错误] Node.js 下载失败，请检查网络。 & pause & exit /b )

    echo [2/5] 解压 Node.js...
    powershell -Command "Expand-Archive -Path '%TOOLS_DIR%\node.zip' -DestinationPath '%TOOLS_DIR%' -Force"
    del "%TOOLS_DIR%\node.zip"
) else (
    echo [2/5] Node.js 已安装。
)

REM --- 1.3 设置临时环境变量 (不污染系统) ---
set "PATH=%TOOLS_DIR%;%NODE_DIR%;%PATH%"

REM ================= 2. 后端依赖安装 =================
echo.
echo [3/5] 正在准备 Python 后端环境...

REM 使用 uv 创建虚拟环境 (uv 会自动下载 Python，无需手动安装!)
if not exist ".venv" (
    echo    - 创建虚拟环境 (自动下载 Python 3.11+)...
    "%UV_EXE%" venv --python 3.11
)

REM 激活虚拟环境
call .venv\Scripts\activate

REM 安装依赖 (读取 pyproject.toml)
if not exist ".venv\Lib\site-packages\installed_flag" (
    echo    - 正在安装后端依赖 (使用清华源)...

    REM 安装 backend
    "%UV_EXE%" pip install -r backend/pyproject.toml -i https://pypi.tuna.tsinghua.edu.cn/simple

    REM 安装 MCP 扩展
    "%UV_EXE%" pip install -r MCP_SERVER/ddgs/pyproject.toml -i https://pypi.tuna.tsinghua.edu.cn/simple
    "%UV_EXE%" pip install -r MCP_SERVER/knowledge_base/pyproject.toml -i https://pypi.tuna.tsinghua.edu.cn/simple

    echo done > .venv\Lib\site-packages\installed_flag
) else (
    echo    - 后端依赖已就绪。
)

REM ================= 3. 前端编译与代理准备 =================
echo.
echo [4/5] 正在准备前端环境...

REM 安装根目录代理脚本的依赖 (express 等)
if not exist "node_modules" (
    echo    - 安装本地服务器依赖...
    call npm install express http-proxy-middleware --no-save --loglevel=error
)

REM 编译前端项目
cd frontend/mambo
if not exist "dist" (
    echo    - 安装前端依赖 (npm install)...
    call npm install --loglevel=error

    echo    - 编译前端代码 (npm run build)...
    call npm run build
) else (
    echo    - 前端已编译，跳过。
)
cd ..\..

REM ================= 4. 启动服务 =================
echo.
echo [5/5] 正在启动服务...

REM 设置后端所需的路径变量
set "PYTHONPATH=%cd%"
if not exist "uploads" mkdir uploads
set "STORAGE_PATH=%cd%\uploads"
set "DB_ECHO=False"

REM 启动后端 (新窗口最小化运行)
start "Mambo Backend" /min cmd /c "call .venv\Scripts\activate && python -m uvicorn backend.main:app --host 127.0.0.1 --port 8000 --workers 1"

REM 启动前端代理 (当前窗口)
echo.
echo [成功] 服务已启动！
echo [提示] 请勿关闭此窗口。
echo [提示] 正在打开浏览器...

REM 延迟 3 秒后打开浏览器
start "" cmd /c "timeout /t 3 >nul & start http://localhost:24911"

REM 运行 Node 代理服务器
node local_server.js

pause
