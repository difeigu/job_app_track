@echo off
setlocal
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
    echo Set up the virtual environment first using the instructions in README.md.
    echo Then run this file again.
    pause
    exit /b 1
)

echo Open http://127.0.0.1:5000 in your browser. Press Ctrl+C here to stop.
".venv\Scripts\python.exe" app.py
if errorlevel 1 pause
