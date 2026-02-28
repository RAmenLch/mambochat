@echo off
chcp 65001 >nul 2>&1
setlocal enabledelayedexpansion

echo ============================================
echo   MamboChat Setup Script
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
echo [1/6] Checking uv package manager...

set "UV_EXE="

:: Priority 1: Check runtime directory
if exist "%UV_DIR%\uv.exe" (
    set "UV_EXE=%UV_DIR%\uv.exe"
    echo   [OK] uv is installed in runtime directory
    goto :uv_ready
)

:: Priority 2: Check system PATH
for /f "delims=" %%i in ('where uv 2^>nul') do (
    if not defined UV_EXE if exist "%%i" set "UV_EXE=%%i"
)
if defined UV_EXE (
    echo   [OK] Detected system uv: !UV_EXE!
    goto :uv_ready
)

:: Priority 3: Download uv
echo   [!] uv not found, downloading...
if not exist "%UV_DIR%" mkdir "%UV_DIR%"

powershell -NoProfile -ExecutionPolicy Bypass -Command "[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12; $zipFile = '%RUNTIME_DIR%\uv.zip'; Write-Host '  Downloading...'; Invoke-WebRequest -Uri 'https://github.com/astral-sh/uv/releases/latest/download/uv-x86_64-pc-windows-msvc.zip' -OutFile $zipFile; Write-Host '  Extracting...'; Expand-Archive -Path $zipFile -DestinationPath '%RUNTIME_DIR%\uv_temp' -Force; Remove-Item $zipFile -Force; Get-ChildItem '%RUNTIME_DIR%\uv_temp' -Recurse -Filter 'uv.exe' | ForEach-Object { Copy-Item \"$($_.Directory.FullName)\*\" '%UV_DIR%\' -Force }; Remove-Item '%RUNTIME_DIR%\uv_temp' -Recurse -Force"

if exist "%UV_DIR%\uv.exe" (
    set "UV_EXE=%UV_DIR%\uv.exe"
    echo   [OK] uv download complete
) else (
    echo   [X] uv download failed. Please check network or install manually.
    echo       Download URL: https://github.com/astral-sh/uv/releases
    :: [FIX] Clean up residual folders
    if exist "%UV_DIR%" rd /s /q "%UV_DIR%"
    pause
    exit /b 1
)

:uv_ready

:: ============================================
:: Step 2: Install Python via uv
:: ============================================
echo.
echo [2/6] Checking Python %PYTHON_VERSION%...

"%UV_EXE%" python find %PYTHON_VERSION% >nul 2>&1
if %errorlevel% equ 0 (
    echo   [OK] Python %PYTHON_VERSION% is available
) else (
    echo   Installing Python %PYTHON_VERSION% via uv...
    "%UV_EXE%" python install %PYTHON_VERSION%
    if !errorlevel! neq 0 (
        echo   [X] Python installation failed
        pause
        exit /b 1
    )
    echo   [OK] Python %PYTHON_VERSION% installation complete
)

:: ============================================
:: Step 3: Create venv and install backend dependencies
:: ============================================
echo.
echo [3/6] Installing backend dependencies...

set "PYTHON_EXE=%VENV_DIR%\Scripts\python.exe"

if not exist "%VENV_DIR%\Scripts\python.exe" (
    echo   Creating virtual environment...
    "%UV_EXE%" venv "%VENV_DIR%" --python %PYTHON_VERSION%
    if !errorlevel! neq 0 (
        echo   [X] Virtual environment creation failed
        :: [FIX] Clean up residual folders
        if exist "%VENV_DIR%" rd /s /q "%VENV_DIR%"
        pause
        exit /b 1
    )
)

echo   Installing backend dependencies...
"%UV_EXE%" pip install --python "%PYTHON_EXE%" -e "%ROOT_DIR%backend" -i https://pypi.tuna.tsinghua.edu.cn/simple
if %errorlevel% neq 0 (
    echo   [X] Backend dependencies installation failed
    :: [FIX] Clean up residual folders
    if exist "%VENV_DIR%" rd /s /q "%VENV_DIR%"
    pause
    exit /b 1
)

echo   Installing MCP Server (ddgs) dependencies...
"%UV_EXE%" pip install --python "%PYTHON_EXE%" -e "%ROOT_DIR%MCP_SERVER\ddgs" -i https://pypi.tuna.tsinghua.edu.cn/simple
if %errorlevel% neq 0 (
    echo   [X] MCP Server (ddgs) dependencies installation failed
    if exist "%VENV_DIR%" rd /s /q "%VENV_DIR%"
    pause
    exit /b 1
)

echo   Installing MCP Server (knowledge_base) dependencies...
"%UV_EXE%" pip install --python "%PYTHON_EXE%" -e "%ROOT_DIR%MCP_SERVER\knowledge_base" -i https://pypi.tuna.tsinghua.edu.cn/simple
if %errorlevel% neq 0 (
    echo   [X] MCP Server (knowledge_base) dependencies installation failed
    if exist "%VENV_DIR%" rd /s /q "%VENV_DIR%"
    pause
    exit /b 1
)

echo   [OK] Backend dependencies installed

:: ============================================
:: Step 4: Check/Install Node.js
:: ============================================
echo.
echo [4/6] Checking Node.js...

set "NODE_EXE="
set "NPM_CMD="

:: Priority 1: Check runtime directory
if exist "%NODE_DIR%\node.exe" (
    set "NODE_EXE=%NODE_DIR%\node.exe"
    set "NPM_CMD=%NODE_DIR%\npm.cmd"
    echo   [OK] Node.js is installed in runtime directory
    goto :node_ready
)

:: Priority 2: Check system PATH
for /f "delims=" %%i in ('where node 2^>nul') do (
    if not defined NODE_EXE if exist "%%i" set "NODE_EXE=%%i"
)
if defined NODE_EXE (
    for %%F in ("!NODE_EXE!") do set "NODE_BIN_DIR=%%~dpF"
    set "NPM_CMD=!NODE_BIN_DIR!npm.cmd"
    if not exist "!NPM_CMD!" (
        set "NPM_CMD="
        for /f "delims=" %%j in ('where npm 2^>nul') do (
            if not defined NPM_CMD if exist "%%j" set "NPM_CMD=%%j"
        )
    )
    if defined NPM_CMD (
        echo   [OK] Detected system Node.js: !NODE_EXE!
        echo       npm path: !NPM_CMD!
        goto :node_ready
    )
    echo   [!] Found node but not npm, will re-download complete Node.js
    set "NODE_EXE="
)

:: Priority 3: Download Node.js
echo   [!] Node.js not found, downloading v%NODE_VERSION%...
if not exist "%NODE_DIR%" mkdir "%NODE_DIR%"

powershell -NoProfile -ExecutionPolicy Bypass -Command "[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12; $url = 'https://nodejs.org/dist/v%NODE_VERSION%/node-v%NODE_VERSION%-win-x64.zip'; $zipFile = '%RUNTIME_DIR%\node.zip'; Write-Host '  Downloading Node.js v%NODE_VERSION% ...'; Invoke-WebRequest -Uri $url -OutFile $zipFile; Write-Host '  Extracting...'; Expand-Archive -Path $zipFile -DestinationPath '%RUNTIME_DIR%' -Force; Remove-Item $zipFile -Force; $extracted = Get-ChildItem '%RUNTIME_DIR%' -Directory | Where-Object { $_.Name -like 'node-v*' } | Select-Object -First 1; if ($extracted) { Get-ChildItem $extracted.FullName | Move-Item -Destination '%NODE_DIR%\' -Force; Remove-Item $extracted.FullName -Recurse -Force }"

if exist "%NODE_DIR%\node.exe" (
    set "NODE_EXE=%NODE_DIR%\node.exe"
    set "NPM_CMD=%NODE_DIR%\npm.cmd"
    echo   [OK] Node.js v%NODE_VERSION% download complete
) else (
    echo   [X] Node.js download failed
    echo       Please download manually: https://nodejs.org/
    :: [FIX] Clean up residual folders
    if exist "%NODE_DIR%" rd /s /q "%NODE_DIR%"
    pause
    exit /b 1
)

:node_ready

if not exist "!NPM_CMD!" (
    echo   [X] Cannot find npm: !NPM_CMD!
    pause
    exit /b 1
)

echo   Verify: npm path = !NPM_CMD!

:: Add Node.js directory to PATH
set "PATH=%NODE_DIR%;%PATH%"

:: ============================================
:: Step 5: Install frontend dependencies and build
:: ============================================
echo.
echo [5/6] Installing frontend dependencies and building...

if not exist "%FRONTEND_DIR%\node_modules\" (
    echo   node_modules not found, installing npm dependencies...
    pushd "%FRONTEND_DIR%"
    :: [FIX] Added taobao mirror parameter
    call "!NPM_CMD!" install --registry=https://registry.npmmirror.com
    if !errorlevel! neq 0 (
        echo.
        echo   [X] npm install failed
        echo   [!] Cleaning node_modules for next retry...
        :: [FIX] Clean up residual folders
        if exist "%FRONTEND_DIR%\node_modules" rd /s /q "%FRONTEND_DIR%\node_modules"
        popd
        pause
        exit /b 1
    )
    popd
    echo   [OK] npm dependencies installed
) else (
    echo   [OK] node_modules exists, skipping installation
)

echo   Building frontend static files...
pushd "%FRONTEND_DIR%"
call "!NPM_CMD!" run build
if !errorlevel! neq 0 (
    echo   [X] Frontend build failed
    popd
    pause
    exit /b 1
)
popd

if not exist "%FRONTEND_DIR%\dist\index.html" (
    echo   [X] Frontend build artifacts do not exist
    pause
    exit /b 1
)
echo   [OK] Frontend build complete

:: ============================================
:: Step 6: Start services
:: ============================================
echo.
echo [6/6] Starting services...
echo.

set "PYTHONPATH=%ROOT_DIR%"
set "TZ=Asia/Shanghai"
set "STORAGE_PATH=%ROOT_DIR%uploads"

if not exist "%ROOT_DIR%uploads" mkdir "%ROOT_DIR%uploads"
if not exist "%ROOT_DIR%DB" mkdir "%ROOT_DIR%DB"

echo   Cleaning up potential old processes...
for /f "tokens=5" %%p in ('netstat -aon ^| findstr ":8000 " ^| findstr "LISTENING"') do (
    taskkill /PID %%p /F >nul 2>&1
)
for /f "tokens=5" %%p in ('netstat -aon ^| findstr ":24911 " ^| findstr "LISTENING"') do (
    taskkill /PID %%p /F >nul 2>&1
)

echo   Starting backend service (Port 8000)...
start "MamboChat-Backend" cmd /k "title MamboChat-Backend && "%PYTHON_EXE%" -m uvicorn backend.main:app --host 127.0.0.1 --port 8000 --app-dir "%ROOT_DIR%""

echo   Waiting for backend to start...
set "BACKEND_READY=0"
for /l %%i in (1,1,15) do (
    if !BACKEND_READY! equ 0 (
        timeout /t 1 /nobreak >nul
        powershell -NoProfile -Command "try { $r = Invoke-WebRequest -Uri 'http://127.0.0.1:8000/' -UseBasicParsing -TimeoutSec 2; exit 0 } catch { exit 1 }" >nul 2>&1
        if !errorlevel! equ 0 (
            set "BACKEND_READY=1"
            echo   [OK] Backend is ready
        )
    )
)
if !BACKEND_READY! equ 0 (
    echo   [!] Backend might still be starting, proceeding to frontend...
)

echo   Starting frontend service (Port 24911)...
pushd "%FRONTEND_DIR%"
start "MamboChat-Frontend" cmd /k "title MamboChat-Frontend && call "!NPM_CMD!" run preview -- --port 24911 --host 127.0.0.1"
popd

timeout /t 3 /nobreak >nul

echo.
echo ============================================
echo.
echo   MamboChat Started
echo.
echo   Frontend: http://localhost:24911
echo   Backend API: http://localhost:8000
echo.
echo   Tip: Close the MamboChat-Backend and
echo        MamboChat-Frontend windows to stop services.
echo.
echo ============================================
echo.
pause
