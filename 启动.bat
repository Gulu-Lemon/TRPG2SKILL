@echo off
cd /d "%~dp0"

python --version >nul 2>nul
if errorlevel 1 (
    echo [ERROR] Python not found. Install Python 3.12+
    pause
    exit /b 1
)

REM Check / install dependencies
python -c "import flask" >nul 2>nul
if errorlevel 1 (
    echo   Installing dependencies...
    pip install -r requirements.txt -q
    if errorlevel 1 (
        echo   [WARN] Some packages failed. The tool may not work correctly.
    )
)

echo.
echo   === TRPG2SKILL v1.0.0-beta ===
echo.
echo   Starting Web GUI at http://127.0.0.1:8641
echo.
start "" "http://127.0.0.1:8641"
python main.py serve
if errorlevel 1 pause
