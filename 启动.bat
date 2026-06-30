@echo off
cd /d "%~dp0"

python --version >nul 2>nul
if errorlevel 1 (
    echo [ERROR] Python not found. Install Python 3.12+
    pause
    exit /b 1
)

python -c "import flask" >nul 2>nul
if errorlevel 1 (
    echo   Installing dependencies...
    pip install -r requirements.txt -q
)

echo.
echo   === TRPG2SKILL v1.0.1-beta ===
echo.
echo   Starting Web GUI at http://127.0.0.1:8641
echo.
timeout /t 1 /nobreak >nul
start "" "http://127.0.0.1:8641"
python main.py serve
exit /b %ERRORLEVEL%
