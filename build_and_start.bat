@echo off
chcp 65001 >nul 2>&1
setlocal enabledelayedexpansion

echo ============================================
echo   MamboChat Portable Build and Start
echo ============================================

set "ROOT_DIR=%~dp0"
set "RUNTIME_DIR=%ROOT_DIR%runtime"
set "PYTHON_DIR=%RUNTIME_DIR%\python"
set "NODE_DIR=%RUNTIME_DIR%\node"
set "FRONTEND_DIR=%ROOT_DIR%frontend\mambo"

:: Versions
set "PYTHON_VERSION=3.11.9"
set "PYTHON_EMBED_URL=https://www.python.org/ftp/python/%PYTHON_VERSION%/python-%PYTHON_VERSION%-embed-amd64.zip"
set "NODE_VERSION=22.16.0"

:: Create runtime directory
if not exist "%RUNTIME_DIR%" mkdir "%RUNTIME_DIR%"

:: ============================================
:: Step 1: Setup Portable Python (Build Once)
:: ============================================
set "PYTHON_EXE=%PYTHON_DIR%\python.exe"
set "NEED_BUILD=0"

if not exist "%PYTHON_EXE%" (
    echo.
    echo [Setup] Portable Python not found. Setting up...
    set "NEED_BUILD=1"

    echo   Downloading Python %PYTHON_VERSION% Embeddable Package...
    powershell -NoProfile -Command "Invoke-WebRequest -Uri '%PYTHON_EMBED_URL%' -OutFile '%RUNTIME_DIR%\python_embed.zip'"

    echo   Extracting...
    if not exist "%PYTHON_DIR%" mkdir "%PYTHON_DIR%"
    powershell -NoProfile -Command "Expand-Archive -Path '%RUNTIME_DIR%\python_embed.zip' -DestinationPath '%PYTHON_DIR%' -Force"
    del "%RUNTIME_DIR%\python_embed.zip"

    echo   Configuring python311._pth for portable site-packages...
    (
        echo python311.zip
        echo .
        echo Lib
        echo Lib\site-packages
        echo ..\..
        echo import site
    ) > "%PYTHON_DIR%\python311._pth"

    echo   Installing pip...
    powershell -NoProfile -Command "Invoke-WebRequest -Uri 'https://bootstrap.pypa.io/get-pip.py' -OutFile '%PYTHON_DIR%\get-pip.py'"
    "%PYTHON_EXE%" "%PYTHON_DIR%\get-pip.py" --no-warn-script-location
    del "%PYTHON_DIR%\get-pip.py"

    echo   [OK] Portable Python created.
) else (
    echo [Check] Portable Python found.
)

:: ============================================
:: Step 2: Install Backend Dependencies (Build Once)
:: ============================================
echo.
echo [Check] Backend dependencies...

:: mambo-agents 是仅存在于官方 PyPI 的预发布包(国内镜像不同步),且频繁更新。
:: 校验其已安装版本是否与 pyproject.toml 锁定版本一致,不一致则重新安装。
"%PYTHON_EXE%" -c "import tomllib,importlib.metadata as m,sys;d=tomllib.load(open(r'%ROOT_DIR%backend\pyproject.toml','rb'))['project']['dependencies'];r=next(x for x in d if x.lower().startswith('mambo-agents'));sys.exit(0 if m.version('mambo-agents')==r.split('==')[-1].strip() else 1)" >nul 2>&1
if %errorlevel% neq 0 (
    echo   Installing backend dependencies...
    :: 清华镜像为主源(快),官方 PyPI 为补充源(提供 mambo-agents 预发布版)
    "%PYTHON_EXE%" -m pip install -e "%ROOT_DIR%backend" -i https://pypi.tuna.tsinghua.edu.cn/simple --extra-index-url https://pypi.org/simple/
    echo   [OK] Dependencies installed.
) else (
    echo   [OK] Backend dependencies verified.
)

:: ============================================
:: Step 3: Setup Node.js (Build Once)
:: ============================================
echo.
echo [Check] Node.js environment...

set "NPM_CMD=%NODE_DIR%\npm.cmd"
set "PATH=%NODE_DIR%;%PATH%"

if not exist "%NODE_DIR%\node.exe" (
    echo   Downloading Node.js %NODE_VERSION%...
    powershell -NoProfile -Command "$url = 'https://nodejs.org/dist/v%NODE_VERSION%/node-v%NODE_VERSION%-win-x64.zip'; $zip = '%RUNTIME_DIR%\node.zip'; Invoke-WebRequest -Uri $url -OutFile $zip; Expand-Archive -Path $zip -DestinationPath '%RUNTIME_DIR%' -Force; Remove-Item $zip -Force;"

    :: Move files from subfolder to NODE_DIR
    for /d %%i in ("%RUNTIME_DIR%\node-v*") do (
        if not exist "%NODE_DIR%" mkdir "%NODE_DIR%"
        xcopy "%%i\*" "%NODE_DIR%\" /E /I /Y >nul
        rd /s /q "%%i"
    )
    echo   [OK] Node.js ready.
) else (
    echo   [OK] Node.js found.
)

:: ============================================
:: Step 4: Frontend Dependencies and Build
:: ============================================
echo.
echo [Check] Frontend dependencies...

if not exist "%FRONTEND_DIR%\node_modules\" (
    echo   Installing npm dependencies...
    pushd "%FRONTEND_DIR%"
    call "%NPM_CMD%" install --registry=https://registry.npmmirror.com
    popd
) else (
    echo   [OK] node_modules found.
)

echo [Check] Frontend build artifacts...
if not exist "%FRONTEND_DIR%\dist\index.html" (
    echo   Building frontend...
    pushd "%FRONTEND_DIR%"
    call "%NPM_CMD%" run build
    popd
    if not exist "%FRONTEND_DIR%\dist\index.html" (
        echo   [X] Frontend build failed!
        pause
        exit /b 1
    )
    echo   [OK] Frontend built.
) else (
    echo   [OK] Frontend build found.
)

:: ============================================
:: Step 5: Start Services
:: ============================================
echo.
echo ============================================
echo   Starting Services...
echo ============================================
echo.

set "PYTHONPATH=%ROOT_DIR%"
set "TZ=Asia/Shanghai"

if not exist "%ROOT_DIR%uploads" mkdir "%ROOT_DIR%uploads"
if not exist "%ROOT_DIR%DB" mkdir "%ROOT_DIR%DB"

:: --- Detect available ports ---
:: Use TcpListener bind test: tries to actually bind the port at OS level.
:: If any process (HTTP, WSL, any type) is using the port, the OS will refuse.
:: This is more reliable than netstat or HTTP probing.

echo.
echo   Detecting available ports...
set "BACKEND_PORT=8000"

:check_backend_port
if !BACKEND_PORT! gtr 8010 goto :backend_no_port
powershell -NoProfile -Command "try { $l = [System.Net.Sockets.TcpListener]::new([System.Net.IPAddress]::Loopback, !BACKEND_PORT!); $l.Start(); $l.Stop(); exit 0 } catch { exit 1 }" >nul 2>&1
if !errorlevel! equ 0 (
    echo   [OK] Backend port: !BACKEND_PORT!
    goto :check_frontend_port
)
echo   Port !BACKEND_PORT! is in use, trying next...
set /a "BACKEND_PORT+=1"
goto :check_backend_port

:backend_no_port
echo   [Error] Cannot find free port for backend in range 8000-8010!
echo   Please close applications using these ports and try again.
pause
exit /b 1

:check_frontend_port
set "FRONTEND_PORT=24911"
:check_fe_port_loop
if !FRONTEND_PORT! gtr 24920 goto :frontend_no_port
powershell -NoProfile -Command "try { $l = [System.Net.Sockets.TcpListener]::new([System.Net.IPAddress]::Loopback, !FRONTEND_PORT!); $l.Start(); $l.Stop(); exit 0 } catch { exit 1 }" >nul 2>&1
if !errorlevel! equ 0 (
    echo   [OK] Frontend port: !FRONTEND_PORT!
    goto :ports_done
)
echo   Port !FRONTEND_PORT! is in use, trying next...
set /a "FRONTEND_PORT+=1"
goto :check_fe_port_loop

:frontend_no_port
echo   [Error] Cannot find free port for frontend in range 24911-24920!
echo   Please close applications using these ports and try again.
pause
exit /b 1

:ports_done

:: --- Start Backend ---
echo.
echo   Starting Backend (Port !BACKEND_PORT!)...
start "MamboChat-Backend" cmd /k "title MamboChat-Backend [Port !BACKEND_PORT!] && "%PYTHON_EXE%" -m uvicorn backend.main:app --host 127.0.0.1 --port !BACKEND_PORT! --app-dir "%ROOT_DIR%""

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
    echo   Common causes:
    echo     - Database migration failed
    echo     - Missing Python dependencies
    echo.
    pause
    exit /b 1
)

:: --- Start Frontend ---
echo.
echo   Starting Frontend (Port !FRONTEND_PORT!)...
pushd "%FRONTEND_DIR%"
start "MamboChat-Frontend" cmd /k "set BACKEND_PORT=!BACKEND_PORT! && title MamboChat-Frontend [Port !FRONTEND_PORT!] && call "%NPM_CMD%" run preview -- --port !FRONTEND_PORT! --host 127.0.0.1 --strictPort"
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
