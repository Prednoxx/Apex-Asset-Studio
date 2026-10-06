@echo off
setlocal
cd /d "%~dp0"
if not exist .venv\Scripts\python.exe (
  py -3 -m venv .venv || exit /b 1
)
.venv\Scripts\python.exe -m pip install -e . pyinstaller || exit /b 1
.venv\Scripts\python.exe -m apex_asset_studio.package_addon || exit /b 1
.venv\Scripts\python.exe -m PyInstaller --noconfirm --windowed --name ApexAssetStudio ^
  --distpath dist\native-preview --workpath build\native-preview ^
  --hidden-import ooz --hidden-import texture2ddecoder ^
  --collect-submodules OpenGL --hidden-import pyopengltk.win32 ^
  --icon "apex_asset_studio\resources\app_icon.ico" ^
  --add-data "apex_asset_studio\resources;apex_asset_studio\resources" ^
  --add-data "third_party\dxc;third_party\dxc" ^
  --add-data "blender_addon\ApexAssetStudio_Blender_5.2.zip;blender_addon" ^
  launcher.py || exit /b 1
copy /y blender_addon\ApexAssetStudio_Blender_5.2.zip dist\native-preview\ApexAssetStudio\ >nul
copy /y README.txt dist\native-preview\ApexAssetStudio\ >nul
copy /y LICENSE dist\native-preview\ApexAssetStudio\ >nul
copy /y THIRD_PARTY_NOTICES.md dist\native-preview\ApexAssetStudio\ >nul
echo Portable build: dist\native-preview\ApexAssetStudio\ApexAssetStudio.exe
where iscc >nul 2>nul
if not errorlevel 1 iscc installer\ApexAssetStudio.iss
