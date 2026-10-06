@echo off
setlocal
cd /d "%~dp0"
if not exist .venv\Scripts\python.exe (
  py -3 -m venv .venv || exit /b 1
)
.venv\Scripts\python.exe -m pip install --disable-pip-version-check -e . pyinstaller || exit /b 1
for /f %%v in ('.venv\Scripts\python.exe -c "import apex_asset_studio as a; print(a.__version__)"') do set VERSION=%%v
echo Building Apex Asset Studio %VERSION%

echo Running tests...
.venv\Scripts\python.exe -m unittest discover -s tests -p "test_*.py" || (echo Tests failed; build stopped. & exit /b 1)

.venv\Scripts\python.exe -m apex_asset_studio.package_addon || exit /b 1
rem The command line below is the single source of build settings (no .spec file is kept).
rem --noupx: UPX-packed executables are often flagged by antivirus and start slower.
.venv\Scripts\python.exe -m PyInstaller --noconfirm --clean --windowed --noupx --name ApexAssetStudio ^
  --specpath build ^
  --distpath dist\native-preview --workpath build\native-preview ^
  --hidden-import ooz --hidden-import texture2ddecoder ^
  --collect-submodules OpenGL --hidden-import pyopengltk.win32 ^
  --icon "%CD%\apex_asset_studio\resources\app_icon.ico" ^
  --add-data "%CD%\apex_asset_studio\resources;apex_asset_studio\resources" ^
  --add-data "%CD%\third_party\dxc;third_party\dxc" ^
  --add-data "%CD%\blender_addon\ApexAssetStudio_Blender_5.2.zip;blender_addon" ^
  launcher.py || exit /b 1
copy /y blender_addon\ApexAssetStudio_Blender_5.2.zip dist\native-preview\ApexAssetStudio\ >nul
copy /y README.txt dist\native-preview\ApexAssetStudio\ >nul
copy /y LICENSE dist\native-preview\ApexAssetStudio\ >nul
copy /y THIRD_PARTY_NOTICES.md dist\native-preview\ApexAssetStudio\ >nul
echo Portable build: dist\native-preview\ApexAssetStudio\ApexAssetStudio.exe
where iscc >nul 2>nul
if not errorlevel 1 iscc /DMyAppVersion=%VERSION% installer\ApexAssetStudio.iss
