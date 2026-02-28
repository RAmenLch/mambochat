@echo off
chcp 65001 >nul 2>&1
setlocal enabledelayedexpansion

echo ============================================
echo   MamboChat 快速启动脚本
echo ============================================

set "ROOT_DIR=%~dp0"
set "RUNTIME_DIR=%ROOT_DIR%runtime"
set "NODE_DIR=%RUNTIME_DIR%\node"
set "VENV_DIR=%RUNTIME_DIR%\.venv"
set "FRONTEND_DIR=%ROOT_DIR%frontend\mambo"

:: ============================================
:: 1. 环境完整性检查
:: ============================================

:: 1.1 检查 Python 虚拟环境
set "PYTHON_EXE=%VENV_DIR%\Scripts\python.exe"
if not exist "!PYTHON_EXE!" (
    echo.
    echo [错误] 未检测到 Python 虚拟环境！
    echo 路径不存在: !PYTHON_EXE!
    goto :missing_env
)

:: 1.2 检查 Node/NPM (优先检查 runtime，其次检查系统)
set "NPM_CMD="
if exist "%NODE_DIR%\npm.cmd" (
    set "NPM_CMD=%NODE_DIR%\npm.cmd"
    :: 将 runtime node 加入 PATH，防止前端找不到 node
    set "PATH=%NODE_DIR%;%PATH%"
) else (
    where npm >nul 2>&1
    if !errorlevel! equ 0 (
        set "NPM_CMD=npm"
    )
)

if not defined NPM_CMD (
    echo.
    echo [错误] 未检测到 Node.js 或 NPM！
    goto :missing_env
)

:: 1.3 检查前端依赖
if not exist "%FRONTEND_DIR%\node_modules\" (
    echo.
    echo [错误] 前端 node_modules 缺失！
    goto :missing_env
)

:: ============================================
:: 2. 启动服务
:: ============================================
echo.
echo 环境检查通过，准备启动...

set "PYTHONPATH=%ROOT_DIR%"
set "TZ=Asia/Shanghai"

:: 创建必要目录（防止被意外删除）
if not exist "%ROOT_DIR%uploads" mkdir "%ROOT_DIR%uploads"
if not exist "%ROOT_DIR%DB" mkdir "%ROOT_DIR%DB"

echo 清理端口占用 (8000, 24911)...
for /f "tokens=5" %%p in ('netstat -aon ^| findstr ":8000 " ^| findstr "LISTENING"') do (
    taskkill /PID %%p /F >nul 2>&1
)
for /f "tokens=5" %%p in ('netstat -aon ^| findstr ":24911 " ^| findstr "LISTENING"') do (
    taskkill /PID %%p /F >nul 2>&1
)

echo.
echo [1/2] 启动后端服务...
start "MamboChat-Backend" cmd /k "title MamboChat-Backend && "%PYTHON_EXE%" -m uvicorn backend.main:app --host 127.0.0.1 --port 8000 --app-dir "%ROOT_DIR%""

echo 等待后端响应...
set "BACKEND_READY=0"
for /l %%i in (1,1,15) do (
    if !BACKEND_READY! equ 0 (
        timeout /t 1 /nobreak >nul
        powershell -NoProfile -Command "try { $r = Invoke-WebRequest -Uri 'http://127.0.0.1:8000/' -UseBasicParsing -TimeoutSec 2; exit 0 } catch { exit 1 }" >nul 2>&1
        if !errorlevel! equ 0 (
            set "BACKEND_READY=1"
            echo √ 后端已就绪
        )
    )
)

echo.
echo [2/2] 启动前端服务...
pushd "%FRONTEND_DIR%"
:: 使用 preview 模式通常比 dev 更快且更稳定，前提是已经 build 过
:: 如果你想用开发模式，把 run preview 改为 run dev
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
exit /b 0

:: ============================================
:: 错误处理
:: ============================================
:missing_env
echo.
echo ============================================
echo   检测到环境缺失或未安装依赖！
echo.
echo   请先运行完整安装脚本:
echo   build_and_start.bat
echo ============================================
echo.
pause
exit /b 1
