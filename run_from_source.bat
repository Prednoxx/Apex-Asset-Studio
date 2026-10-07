@echo off
setlocal
cd /d "%~dp0"

where py >nul 2>nul
if errorlevel 1 (
  echo Python 3 was not found. Install Python 3.11+ from python.org and include Tcl/Tk.
  pause
  exit /b 1
)

if not exist ".venv\Scripts\python.exe" (
  echo Creating Apex Asset Studio runtime...
  py -3 -m venv .venv || goto :fail
)

".venv\Scripts\python.exe" -c "import ooz, PIL, texture2ddecoder" >nul 2>nul
if errorlevel 1 (
  echo Installing native exporter dependencies...
  ".venv\Scripts\python.exe" -m pip install --disable-pip-version-check -e . || goto :fail
)

".venv\Scripts\python.exe" -m apex_asset_studio
if errorlevel 1 pause
exit /b 0

:fail
echo.
echo Apex Asset Studio setup failed.
pause
exit /b 1
