@echo off
setlocal
cd /d "%~dp0"
rem Output: master folder
for %%m in ("%~dp0..") do set "MASTER=%%~fm"
set "STAGE=%CD%\build\stage"
set "WORK=%CD%\build\work"

if not exist .venv\Scripts\python.exe (
  py -3 -m venv .venv || goto :fail
)
.venv\Scripts\python.exe -m pip install --disable-pip-version-check -e . pyinstaller || goto :fail
for /f %%v in ('.venv\Scripts\python.exe -c "import apex_asset_studio as a; print(a.__version__)"') do set VERSION=%%v
echo Building Apex Asset Studio %VERSION%

echo Running tests...
.venv\Scripts\python.exe -m unittest discover -s tests -p "test_*.py" || (echo Tests failed; build stopped. & goto :fail)

.venv\Scripts\python.exe -m apex_asset_studio.package_addon || goto :fail

tasklist /fi "imagename eq ApexAssetStudio.exe" | find /i "ApexAssetStudio.exe" >nul
if not errorlevel 1 (
  echo Apex Asset Studio is running. Close it and run the build again.
  goto :fail
)

rem Build settings (no UPX)
.venv\Scripts\python.exe -m PyInstaller --noconfirm --clean --windowed --noupx --name ApexAssetStudio ^
  --specpath "%WORK%" --distpath "%STAGE%" --workpath "%WORK%" ^
  --hidden-import ooz --hidden-import texture2ddecoder ^
  --collect-submodules OpenGL --hidden-import pyopengltk.win32 ^
  --icon "%CD%\apex_asset_studio\resources\app_icon.ico" ^
  --add-data "%CD%\apex_asset_studio\resources;apex_asset_studio\resources" ^
  --add-data "%CD%\third_party\dxc;third_party\dxc" ^
  launcher.py || goto :fail

rem Optional installer
where iscc >nul 2>nul
if not errorlevel 1 iscc /DMyAppVersion=%VERSION% "/DStageDir=%STAGE%\ApexAssetStudio" "/O%MASTER%" installer\ApexAssetStudio.iss

echo Copying the app into %MASTER%
copy /y "%STAGE%\ApexAssetStudio\ApexAssetStudio.exe" "%MASTER%\" >nul || goto :fail
robocopy "%STAGE%\ApexAssetStudio\_internal" "%MASTER%\_internal" /mir /njh /njs /ndl /nfl /np >nul
if errorlevel 8 goto :fail

echo Writing release ZIPs to %MASTER%\Releases
.venv\Scripts\python.exe package_release.py || goto :fail

rem Clean up
rmdir /s /q "%STAGE%" 2>nul
rmdir /s /q "%WORK%" 2>nul
rmdir /s /q dist 2>nul
rmdir /s /q build\native-preview 2>nul

echo.
echo Done: %MASTER%\ApexAssetStudio.exe
exit /b 0

:fail
echo.
echo Build failed.
pause
exit /b 1
