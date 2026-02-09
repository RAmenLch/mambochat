@echo off
chcp 65001 >nul 2>&1
setlocal enabledelayedexpansion

echo ============================================
echo   MamboChat 一键启动脚本 (Windows)
echo ============================================

set "ROOT_DIR=%~dp0"
set "RUNTIME_DIR=%ROOT_DIR%runtime"
set "UV_DIR=%RUNTIME_DIR%\uv"
set "NODE_DIR=%RUNTIME_DIR%\node"
set "VENV_DIR=%RUNTIME_DIR%\.venv"
set "FRONTEND_DIR=%ROOT_DIR%frontend\mambo"

:: Python and Node versions
set "PYTHON_VERSION=3.11"
set "NODE_VERSION=22.16.0"

:: Create runtime directory
if not exist "%RUNTIME_DIR%" mkdir "%RUNTIME_DIR%"

:: ============================================
:: Step 1: Check/Install uv
:: ============================================
echo.
echo [1/6] 检查 uv 包管理器...

set "UV_EXE="

:: Priority 1: Check runtime directory
if exist "%UV_DIR%\uv.exe" (
    set "UV_EXE=%UV_DIR%\uv.exe"
    echo  √ uv 已安装在 runtime 目录
    goto :uv_ready
)

:: Priority 2: Check system PATH
:: [FIX] 使用 if exist 验证, 防止 cmd AutoRun 输出 (如 chcp) 被误捕获
for /f "delims=" %%i in ('where uv 2^>nul') do (
    if not defined UV_EXE if exist "%%i" set "UV_EXE=%%i"
)
if defined UV_EXE (
    echo  √ 检测到系统 uv: !UV_EXE!
    goto :uv_ready
)

:: Priority 3: Download uv
echo  × 未检测到 uv，正在下载...
if not exist "%UV_DIR%" mkdir "%UV_DIR%"

powershell -NoProfile -ExecutionPolicy Bypass -Command "[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12; $zipFile = '%RUNTIME_DIR%\uv.zip'; Write-Host '  下载中...'; Invoke-WebRequest -Uri 'https://github.com/astral-sh/uv/releases/latest/download/uv-x86_64-pc-windows-msvc.zip' -OutFile $zipFile; Write-Host '  解压中...'; Expand-Archive -Path $zipFile -DestinationPath '%RUNTIME_DIR%\uv_temp' -Force; Remove-Item $zipFile -Force; Get-ChildItem '%RUNTIME_DIR%\uv_temp' -Recurse -Filter 'uv.exe' | ForEach-Object { Copy-Item \"$($_.Directory.FullName)\*\" '%UV_DIR%\' -Force }; Remove-Item '%RUNTIME_DIR%\uv_temp' -Recurse -Force"

if exist "%UV_DIR%\uv.exe" (
    set "UV_EXE=%UV_DIR%\uv.exe"
    echo  √ uv 下载完成
) else (
    echo  × uv 下载失败，请检查网络或手动安装 uv
    echo    下载地址: https://github.com/astral-sh/uv/releases
    pause
    exit /b 1
)

:uv_ready

:: ============================================
:: Step 2: Install Python via uv
:: ============================================
echo.
echo [2/6] 检查 Python %PYTHON_VERSION%...

"%UV_EXE%" python find %PYTHON_VERSION% >nul 2>&1
if %errorlevel% equ 0 (
    echo  √ Python %PYTHON_VERSION% 已可用
) else (
    echo  正在通过 uv 安装 Python %PYTHON_VERSION%...
    "%UV_EXE%" python install %PYTHON_VERSION%
    if !errorlevel! neq 0 (
        echo  × Python 安装失败
        pause
        exit /b 1
    )
    echo  √ Python %PYTHON_VERSION% 安装完成
)

:: ============================================
:: Step 3: Create venv and install backend dependencies
:: ============================================
echo.
echo [3/6] 安装后端依赖...

set "PYTHON_EXE=%VENV_DIR%\Scripts\python.exe"

if not exist "%VENV_DIR%\Scripts\python.exe" (
    echo  创建虚拟环境...
    "%UV_EXE%" venv "%VENV_DIR%" --python %PYTHON_VERSION%
    if !errorlevel! neq 0 (
        echo  × 虚拟环境创建失败
        pause
        exit /b 1
    )
)

echo  安装 backend 依赖...
"%UV_EXE%" pip install --python "%PYTHON_EXE%" -e "%ROOT_DIR%backend" -i https://pypi.tuna.tsinghua.edu.cn/simple
if %errorlevel% neq 0 (
    echo  × backend 依赖安装失败
    pause
    exit /b 1
)

echo  安装 MCP Server (ddgs) 依赖...
"%UV_EXE%" pip install --python "%PYTHON_EXE%" -e "%ROOT_DIR%MCP_SERVER\ddgs" -i https://pypi.tuna.tsinghua.edu.cn/simple

echo  安装 MCP Server (knowledge_base) 依赖...
"%UV_EXE%" pip install --python "%PYTHON_EXE%" -e "%ROOT_DIR%MCP_SERVER\knowledge_base" -i https://pypi.tuna.tsinghua.edu.cn/simple

echo  √ 后端依赖安装完成

:: ============================================
:: Step 4: Check/Install Node.js
:: ============================================
echo.
echo [4/6] 检查 Node.js...

set "NODE_EXE="
set "NPM_CMD="

:: Priority 1: Check runtime directory
if exist "%NODE_DIR%\node.exe" (
    set "NODE_EXE=%NODE_DIR%\node.exe"
    set "NPM_CMD=%NODE_DIR%\npm.cmd"
    echo  √ Node.js 已安装在 runtime 目录
    goto :node_ready
)

:: Priority 2: Check system PATH
:: [FIX] 使用 if exist 验证, 防止 cmd AutoRun 输出被误捕获
for /f "delims=" %%i in ('where node 2^>nul') do (
    if not defined NODE_EXE if exist "%%i" set "NODE_EXE=%%i"
)
if defined NODE_EXE (
    :: 从 node.exe 路径推算同目录下的 npm.cmd
    for %%F in ("!NODE_EXE!") do set "NODE_BIN_DIR=%%~dpF"
    set "NPM_CMD=!NODE_BIN_DIR!npm.cmd"
    if not exist "!NPM_CMD!" (
        :: npm.cmd 不在 node 同目录, 尝试 where npm
        set "NPM_CMD="
        for /f "delims=" %%j in ('where npm 2^>nul') do (
            if not defined NPM_CMD if exist "%%j" set "NPM_CMD=%%j"
        )
    )
    if defined NPM_CMD (
        echo  √ 检测到系统 Node.js: !NODE_EXE!
        echo    npm 路径: !NPM_CMD!
        goto :node_ready
    )
    echo  ! 找到 node 但未找到 npm, 将重新下载完整 Node.js
    set "NODE_EXE="
)

:: Priority 3: Download Node.js
echo  × 未检测到 Node.js，正在下载 v%NODE_VERSION%...
if not exist "%NODE_DIR%" mkdir "%NODE_DIR%"

powershell -NoProfile -ExecutionPolicy Bypass -Command "[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12; $url = 'https://nodejs.org/dist/v%NODE_VERSION%/node-v%NODE_VERSION%-win-x64.zip'; $zipFile = '%RUNTIME_DIR%\node.zip'; Write-Host '  下载 Node.js v%NODE_VERSION% ...'; Invoke-WebRequest -Uri $url -OutFile $zipFile; Write-Host '  解压中...'; Expand-Archive -Path $zipFile -DestinationPath '%RUNTIME_DIR%' -Force; Remove-Item $zipFile -Force; $extracted = Get-ChildItem '%RUNTIME_DIR%' -Directory | Where-Object { $_.Name -like 'node-v*' } | Select-Object -First 1; if ($extracted) { Get-ChildItem $extracted.FullName | Move-Item -Destination '%NODE_DIR%\' -Force; Remove-Item $extracted.FullName -Recurse -Force }"

if exist "%NODE_DIR%\node.exe" (
    set "NODE_EXE=%NODE_DIR%\node.exe"
    set "NPM_CMD=%NODE_DIR%\npm.cmd"
    echo  √ Node.js v%NODE_VERSION% 下载完成
) else (
    echo  × Node.js 下载失败
    echo    请手动下载: https://nodejs.org/
    pause
    exit /b 1
)

:node_ready

if not exist "!NPM_CMD!" (
    echo  × 找不到 npm: !NPM_CMD!
    pause
    exit /b 1
)

echo  验证: npm 路径 = !NPM_CMD!

:: ============================================
:: Step 5: Install frontend dependencies and build
:: ============================================
echo.
echo [5/6] 安装前端依赖并构建...

if not exist "%FRONTEND_DIR%\node_modules\" (
    echo  未检测到 node_modules，正在安装 npm 依赖...
    pushd "%FRONTEND_DIR%"
    call "!NPM_CMD!" install
    if !errorlevel! neq 0 (
        echo  × npm install 失败
        popd
        pause
        exit /b 1
    )
    popd
    echo  √ npm 依赖安装完成
) else (
    echo  √ node_modules 已存在，跳过安装
)

echo  构建前端静态文件...
pushd "%FRONTEND_DIR%"
call "!NPM_CMD!" run build
if !errorlevel! neq 0 (
    echo  × 前端构建失败
    popd
    pause
    exit /b 1
)
popd

if not exist "%FRONTEND_DIR%\dist\index.html" (
    echo  × 前端构建产物不存在
    pause
    exit /b 1
)
echo  √ 前端构建完成

:: ============================================
:: Step 6: Start services
:: ============================================
echo.
echo [6/6] 启动服务...
echo.

set "PYTHONPATH=%ROOT_DIR%"
set "TZ=Asia/Shanghai"
set "STORAGE_PATH=%ROOT_DIR%uploads"

if not exist "%ROOT_DIR%uploads" mkdir "%ROOT_DIR%uploads"
if not exist "%ROOT_DIR%DB" mkdir "%ROOT_DIR%DB"

echo  清理可能残留的旧进程...
for /f "tokens=5" %%p in ('netstat -aon ^| findstr ":8000 " ^| findstr "LISTENING"') do (
    taskkill /PID %%p /F >nul 2>&1
)
for /f "tokens=5" %%p in ('netstat -aon ^| findstr ":24911 " ^| findstr "LISTENING"') do (
    taskkill /PID %%p /F >nul 2>&1
)

echo  启动后端服务 (端口 8000)...
start "MamboChat-Backend" cmd /k "title MamboChat-Backend && "%PYTHON_EXE%" -m uvicorn backend.main:app --host 127.0.0.1 --port 8000 --app-dir "%ROOT_DIR%""

echo  等待后端启动...
set "BACKEND_READY=0"
for /l %%i in (1,1,15) do (
    if !BACKEND_READY! equ 0 (
        timeout /t 1 /nobreak >nul
        powershell -NoProfile -Command "try { $r = Invoke-WebRequest -Uri 'http://127.0.0.1:8000/' -UseBasicParsing -TimeoutSec 2; exit 0 } catch { exit 1 }" >nul 2>&1
        if !errorlevel! equ 0 (
            set "BACKEND_READY=1"
            echo  √ 后端已就绪
        )
    )
)
if !BACKEND_READY! equ 0 (
    echo  ！后端可能还在启动中，继续启动前端...
)

echo  启动前端服务 (端口 24911)...
pushd "%FRONTEND_DIR%"
start "MamboChat-Frontend" cmd /k "title MamboChat-Frontend && call "!NPM_CMD!" run preview -- --port 24911 --host 127.0.0.1"
popd

timeout /t 3 /nobreak >nul

echo.
echo ============================================
echo.
echo   MamboChat 已启动!
echo.
echo   前端地址: http://localhost:24911
echo   后端API: http://localhost:8000
echo.
echo   提示: 关闭 MamboChat-Backend 和
echo         MamboChat-Frontend 窗口即可停止服务
echo.
echo ============================================
echo.
pause
