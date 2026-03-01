@echo off
chcp 65001 >nul 2>&1
setlocal enabledelayedexpansion

echo ============================================
echo   MamboChat Portable Quick Start
echo ============================================

set "ROOT_DIR=%~dp0"
set "RUNTIME_DIR=%ROOT_DIR%runtime"
set "PYTHON_DIR=%RUNTIME_DIR%\python"
set "NODE_DIR=%RUNTIME_DIR%\node"
set "FRONTEND_DIR=%ROOT_DIR%frontend\mambo"

set "PYTHON_EXE=%PYTHON_DIR%\python.exe"
set "NPM_CMD=%NODE_DIR%\npm.cmd"

:: Check if portable environment exists
if not exist "%PYTHON_EXE%" (
    echo [Error] Portable environment not found!
    echo Please run 'build_and_start.bat' first.
    pause
    exit /b 1
)

if not exist "%FRONTEND_DIR%\dist\index.html" (
    echo [Error] Frontend build artifacts not found.
    echo Please run 'build_and_start.bat' first.
    pause
    exit /b 1
)

:: Setup Environment
set "PATH=%NODE_DIR%;%PYTHON_DIR%;%PATH%"
set "PYTHONPATH=%ROOT_DIR%"
set "TZ=Asia/Shanghai"

:: Create Data Directories
if not exist "%ROOT_DIR%uploads" mkdir "%ROOT_DIR%uploads"
if not exist "%ROOT_DIR%DB" mkdir "%ROOT_DIR%DB"

echo.
echo Cleaning up old processes...
for /f "tokens=5" %%p in ('netstat -aon ^| findstr ":8000 " ^| findstr "LISTENING"') do taskkill /PID %%p /F >nul 2>&1
for /f "tokens=5" %%p in ('netstat -aon ^| findstr ":24911 " ^| findstr "LISTENING"') do taskkill /PID %%p /F >nul 2>&1

echo.
echo [1/2] Starting Backend...
start "MamboChat-Backend" cmd /k "title MamboChat-Backend && "%PYTHON_EXE%" -m uvicorn backend.main:app --host 127.0.0.1 --port 8000 --app-dir "%ROOT_DIR%""

echo   Waiting for backend...
set "BACKEND_READY=0"
for /l %%i in (1,1,15) do (
    if !BACKEND_READY! equ 0 (
        timeout /t 1 /nobreak >nul
        powershell -NoProfile -Command "try { Invoke-WebRequest -Uri 'http://127.0.0.1:8000/' -UseBasicParsing -TimeoutSec 2 | Out-Null; exit 0 } catch { exit 1 }" >nul 2>&1
        if !errorlevel! equ 0 set "BACKEND_READY=1"
    )
)

echo.
echo [2/2] Starting Frontend...
pushd "%FRONTEND_DIR%"
start "MamboChat-Frontend" cmd /k "title MamboChat-Frontend && call "%NPM_CMD%" run preview -- --port 24911 --host 127.0.0.1"
popd

timeout /t 3 /nobreak >nul

echo.
echo ============================================
echo.
echo   MamboChat Started
echo.
echo   Frontend: http://localhost:24911
echo   Backend:  http://localhost:8000
echo.
echo   Tip: Close the MamboChat-Backend and
echo        MamboChat-Frontend windows to stop.
echo.
echo ============================================
echo.
pause
