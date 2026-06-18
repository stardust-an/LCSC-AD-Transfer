@echo off
echo ================================================
echo   LCSC-AD-Transfer Converter Service
echo ================================================
echo.

cd /d "%~dp0converter"

echo [1/2] Checking Node.js...
where node >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERROR] Node.js not found.
    echo Please install Node.js 16+: https://nodejs.org/
    pause
    exit /b 1
)
echo         Node.js OK

echo [2/2] Checking dependencies...
if not exist "node_modules\" (
    echo         Installing npm packages...
    call npm install
    if %errorlevel% neq 0 (
        echo [ERROR] npm install failed.
        pause
        exit /b 1
    )
)
echo         Dependencies OK

echo.
echo Starting server on http://localhost:3001
echo.
node server.js

if %errorlevel% neq 0 (
    echo.
    echo [ERROR] Server failed to start.
    echo.
    echo Possible causes:
    echo   1. Port 3001 already in use -- run: taskkill /F /IM node.exe
    echo   2. Missing dependencies -- run: npm install
    echo   3. jsapi.min.js missing from converter\ folder
    pause
)
