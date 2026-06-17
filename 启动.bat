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
echo   [1] Web GUI     (http://127.0.0.1:8641)
echo   [2] Compile     (world book -^> SKILL)
echo   [3] Play        (CLI mode)
echo   [4] Setup       (API config)
echo.
set /p choice="  Choice [1-4, Enter=1]: "
if "%choice%"=="" set choice=1

if "%choice%"=="1" goto serve
if "%choice%"=="2" goto compile
if "%choice%"=="3" goto play
if "%choice%"=="4" goto setup
goto serve

:serve
echo.
echo   Starting Web GUI ...
echo   http://127.0.0.1:8641
echo   Press Ctrl+C to stop
echo.
python main.py serve
if errorlevel 1 pause
goto :eof

:compile
echo.
set /p input="  World book file: "
if "%input%"=="" goto :eof
set /p output="  Output dir [Enter=default]: "
if "%output%"=="" (
    python main.py compile "%input%"
) else (
    python main.py compile "%input%" --output "%output%"
)
pause
goto :eof

:play
echo.
set /p gamedir="  SKILL directory: "
if "%gamedir%"=="" goto :eof
python main.py play "%gamedir%"
pause
goto :eof

:setup
echo.
python main.py setup
pause
goto :eof
