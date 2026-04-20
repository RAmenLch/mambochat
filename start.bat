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

:: Default ports
set "BACKEND_PORT=8000"
set "FRONTEND_PORT=24911"

:: Detect free backend port (8000 - 8010)
echo   Detecting available backend port...
:check_backend_port
netstat -aon | findstr ":%BACKEND_PORT% " | findstr "LISTENING" >nul 2>&1
if !errorlevel! equ 0 (
    if !BACKEND_PORT! geq 8010 (
        echo   [Error] Cannot find free port for backend in range 8000-8010!
        echo   Please close applications using these ports and try again.
        pause
        exit /b 1
    )
    echo   Port !BACKEND_PORT! is in use, trying next...
    set /a "BACKEND_PORT+=1"
    goto :check_backend_port
)
echo   [OK] Backend port: !BACKEND_PORT!

:: Detect free frontend port (24911 - 24920)
echo   Detecting available frontend port...
:check_frontend_port
netstat -aon | findstr ":%FRONTEND_PORT% " | findstr "LISTENING" >nul 2>&1
if !errorlevel! equ 0 (
    if !FRONTEND_PORT! geq 24921 (
        echo   [Error] Cannot find free port for frontend in range 24911-24920!
        echo   Please close applications using these ports and try again.
        pause
        exit /b 1
    )
    echo   Port !FRONTEND_PORT! is in use, trying next...
    set /a "FRONTEND_PORT+=1"
    goto :check_frontend_port
)
echo   [OK] Frontend port: !FRONTEND_PORT!

:: Start Backend
echo.
echo   Starting Backend (Port !BACKEND_PORT!)...
start "MamboChat-Backend" cmd /k "title MamboChat-Backend [Port !BACKEND_PORT!] && "%PYTHON_EXE%" -m uvicorn backend.main:app --host 127.0.0.1 --port !BACKEND_PORT! --app-dir "%ROOT_DIR%""

:: Wait for backend to be ready (up to 30s)
echo   Waiting for backend...
set "BACKEND_READY=0"
for /l %%i in (1,1,30) do (
    if !BACKEND_READY! equ 0 (
        timeout /t 1 /nobreak >nul
        powershell -NoProfile -Command "try { Invoke-WebRequest -Uri 'http://127.0.0.1:!BACKEND_PORT!/' -UseBasicParsing -TimeoutSec 2 | Out-Null; exit 0 } catch { exit 1 }" >nul 2>&1
        if !errorlevel! equ 0 (
            set "BACKEND_READY=1"
            echo   [OK] Backend is ready on port !BACKEND_PORT!
        )
    )
)
if !BACKEND_READY! equ 0 (
    echo.
    echo   [Error] Backend failed to start on port !BACKEND_PORT! within 30 seconds!
    echo   Please check the MamboChat-Backend window for error details.
    echo.
    pause
    exit /b 1
)

:: Start Frontend (--strictPort ensures the detected port is used exactly)
echo   Starting Frontend (Port !FRONTEND_PORT!)...
pushd "%FRONTEND_DIR%"
start "MamboChat-Frontend" cmd /k "title MamboChat-Frontend [Port !FRONTEND_PORT!] && call "%NPM_CMD%" run preview -- --port !FRONTEND_PORT! --host 127.0.0.1 --strictPort"
popd

timeout /t 3 /nobreak >nul

echo.
echo ============================================
echo.
echo   MamboChat Started
echo.
echo   Frontend: http://localhost:!FRONTEND_PORT!
echo   Backend:  http://localhost:!BACKEND_PORT!
echo.
echo   Tip: Close the MamboChat-Backend and
echo        MamboChat-Frontend windows to stop.
echo.
echo ============================================
echo.
pause
