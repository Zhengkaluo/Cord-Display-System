@echo off
cd /d "%~dp0"
py -3 run.py --source auto --open
if errorlevel 1 (
  echo.
  echo Failed to start with the Python launcher. Trying python instead...
  python run.py --source auto --open
)
pause
