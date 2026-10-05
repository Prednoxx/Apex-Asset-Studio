@echo off
setlocal
cd /d "%~dp0"

where py >nul 2>nul
if errorlevel 1 (
  echo Python 3 was not found. Install Python 3.11+ from python.org.
  pause
  exit /b 1
)

if not exist ".venv\Scripts\python.exe" (
  echo Creating Apex Asset Studio runtime...
  py -3 -m venv .venv || goto :fail
)

".venv\Scripts\python.exe" -c "import ooz" >nul 2>nul
if errorlevel 1 (
  echo Installing open-source Oodle decompressor ^(pyooz^)...
  ".venv\Scripts\python.exe" -m pip install --disable-pip-version-check pyooz==0.0.8 || goto :fail
)

".venv\Scripts\python.exe" -m apex_asset_studio.diagnostics --out "%USERPROFILE%\Documents\ApexAssetStudio_Diagnostics.json"
echo.
echo Report saved to Documents\ApexAssetStudio_Diagnostics.json
pause
exit /b 0

:fail
echo.
echo Apex Asset Studio diagnostic setup failed.
pause
exit /b 1
