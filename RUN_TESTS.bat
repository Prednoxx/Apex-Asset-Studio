@echo off
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo Run "Run Apex Asset Studio.bat" once first to set up Python.
  pause & exit /b 1
)
".venv\Scripts\python.exe" -m unittest discover -s tests -p "test_*.py" -v
pause
