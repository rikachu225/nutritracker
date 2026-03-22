@echo off
setlocal
cd /d "%~dp0"

echo.
echo   ┌──────────────────────────────────────────────┐
echo   │           NutriTracker Installer              │
echo   │   Private food tracking with AI analysis      │
echo   └──────────────────────────────────────────────┘
echo.

:: Check for Python
where python >nul 2>&1
if %ERRORLEVEL% neq 0 (
    echo   [!] Python not found. Installing via winget...
    winget install Python.Python.3.12 --accept-source-agreements --accept-package-agreements
    if %ERRORLEVEL% neq 0 (
        echo   [ERROR] Failed to install Python. Install manually from python.org
        pause
        exit /b 1
    )
    echo   [OK] Python installed. You may need to restart your terminal.
    echo       Then run install.bat again.
    pause
    exit /b 0
)

echo   [OK] Python found:
python --version

:: Create virtual environment
if not exist "venv" (
    echo   [*] Creating virtual environment...
    python -m venv venv
    if %ERRORLEVEL% neq 0 (
        echo   [ERROR] Failed to create venv.
        pause
        exit /b 1
    )
    echo   [OK] Virtual environment created.
) else (
    echo   [OK] Virtual environment exists.
)

:: Activate and install dependencies
echo   [*] Installing dependencies...
call venv\Scripts\activate.bat
pip install -r requirements.txt --quiet
if %ERRORLEVEL% neq 0 (
    echo   [ERROR] Failed to install dependencies.
    pause
    exit /b 1
)

:: Generate icons if Pillow available and icons missing
if not exist "frontend\assets\icons\icon-192.png" (
    echo   [*] Generating app icons...
    pip install Pillow --quiet 2>nul
    python generate_icons.py 2>nul
    if exist "frontend\assets\icons\icon-192.png" (
        echo   [OK] Icons generated.
    ) else (
        echo   [SKIP] Icon generation skipped — app will work without them.
    )
)

:: Initialize database
echo   [*] Initializing database...
python -c "from backend.database import init_db; init_db(); print('  [OK] Database ready.')"

echo.
echo   ┌──────────────────────────────────────────────┐
echo   │           Installation Complete!              │
echo   │                                               │
echo   │   Run start.bat to launch the server.         │
echo   │   Then open the URL on your phone.            │
echo   └──────────────────────────────────────────────┘
echo.
pause
