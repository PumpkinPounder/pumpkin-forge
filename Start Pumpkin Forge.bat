@echo off
cd /d "%~dp0"
python -u "%~dp0main.py"
if errorlevel 1 (
    echo.
    echo Pumpkin Forge stopped because startup failed.
)
pause
