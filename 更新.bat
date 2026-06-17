@echo off
cd /d "%~dp0"
echo   === TRPG2SKILL Update ===
echo.
echo   Fetching latest version...
git pull
if errorlevel 1 (
    echo   Update failed. Check network or download manually.
    pause
    exit /b 1
)
echo.
echo   Installing dependencies...
pip install -r requirements.txt -q
echo.
echo   Update complete!
echo   Double-click start.bat to launch.
echo.
pause
