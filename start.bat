@echo off
setlocal enabledelayedexpansion

echo ============================================
echo   MamboChat Quick Start
echo ============================================

set "ROOT_DIR=%~dp0"
set "RUNTIME_DIR=%ROOT_DIR%runtime"
set "NODE_DIR=%RUNTIME_DIR%\node"
set "VENV_DIR=%RUNTIME_DIR%\.venv"
set "FRONTEND_DIR=%ROOT_DIR%frontend\mambo"

:: ============================================
:: 1. Integrity Check
:: ============================================

:: 1.1 Check Python Venv
set "PYTHON_EXE=%VENV_DIR%\Scripts\python.exe"
if not exist "!PYTHON_EXE!" (
    echo.
    echo [ERROR] Python virtual environment not found.
    goto :missing_env
)

:: 1.2 Check Node/NPM
set "NPM_CMD="
if exist "%NODE_DIR%\npm.cmd" (
    set "NPM_CMD=%NODE_DIR%\npm.cmd"
    set "PATH=%NODE_DIR%;%PATH%"
) else (
    where npm >nul 2>&1
    if !errorlevel! equ 0 (
        set "NPM_CMD=npm"
    )
)

if not defined NPM_CMD (
    echo.
    echo [ERROR] Node.js or NPM not found.
    goto :missing_env
)

:: 1.3 Check Frontend Build
if not exist "%FRONTEND_DIR%\node_modules\" (
    echo.
    echo [ERROR] Frontend node_modules missing.
    goto :missing_env
)

if not exist "%FRONTEND_DIR%\dist\index.html" (
    echo.
    echo [ERROR] Frontend build artifacts (dist folder) missing.
    goto :missing_env
)

:: ============================================
:: 2. Start Services
:: ============================================
echo.
echo Environment check passed. Starting...

set "PYTHONPATH=%ROOT_DIR%"
set "TZ=Asia/Shanghai"

if not exist "%ROOT_DIR%uploads" mkdir "%ROOT_DIR%uploads"
if not exist "%ROOT_DIR%DB" mkdir "%ROOT_DIR%DB"

echo Clearing ports (8000, 24911)...
for /f "tokens=5" %%p in ('netstat -aon ^| findstr ":8000 " ^| findstr "LISTENING"') do (
    taskkill /PID %%p /F >nul 2>&1
)
for /f "tokens=5" %%p in ('netstat -aon ^| findstr ":24911 " ^| findstr "LISTENING"') do (
    taskkill /PID %%p /F >nul 2>&1
)

echo.
echo Starting Backend...
start "MamboChat-Backend" cmd /k "title MamboChat-Backend && "%PYTHON_EXE%" -m uvicorn backend.main:app --host 127.0.0.1 --port 8000 --app-dir "%ROOT_DIR%""

echo Waiting for backend response...
set "BACKEND_READY=0"
for /l %%i in (1,1,15) do (
    if !BACKEND_READY! equ 0 (
        timeout /t 1 /nobreak >nul
        powershell -NoProfile -Command "try { $r = Invoke-WebRequest -Uri 'http://127.0.0.1:8000/' -UseBasicParsing -TimeoutSec 2; exit 0 } catch { exit 1 }" >nul 2>&1
        if !errorlevel! equ 0 (
            set "BACKEND_READY=1"
            echo - Backend is ready.
        )
    )
)

echo.
echo Starting Frontend...
pushd "%FRONTEND_DIR%"
start "MamboChat-Frontend" cmd /k "title MamboChat-Frontend && call "!NPM_CMD!" run preview -- --port 24911 --host 127.0.0.1"
popd

timeout /t 3 /nobreak >nul

echo.
echo ============================================
echo.
echo   MamboChat is running!
echo.
echo   Frontend: http://localhost:24911
echo   Backend:  http://localhost:8000
echo.
echo   Tip: Close the backend and frontend
echo        CMD windows to stop the service.
echo.
echo ============================================
echo.
pause
exit /b 0

:: ============================================
:: Error Handling
:: ============================================
:missing_env
echo.
echo ============================================
echo   Dependencies missing or not built!
echo.
echo   Please run the full installation script:
echo   build_and_start.bat.bat
echo ============================================
echo.
pause
exit /b 1
