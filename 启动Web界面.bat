@echo off
setlocal
chcp 65001 >nul
cd /d "%~dp0"
py -3 --version >nul 2>&1
if errorlevel 1 (
    echo Python 3.10 or newer is required.
    pause
    exit /b 1
)
echo Starting Mini SE at http://127.0.0.1:8002
py -3 -X utf8 -m mini_se_workflow --web --open-browser --port 8002
set "MINISE_EXIT_CODE=%ERRORLEVEL%"
if not "%MINISE_EXIT_CODE%"=="0" pause
endlocal & exit /b %MINISE_EXIT_CODE%
