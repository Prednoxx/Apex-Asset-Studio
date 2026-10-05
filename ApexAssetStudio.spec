# -*- mode: python ; coding: utf-8 -*-
from PyInstaller.utils.hooks import collect_submodules

hiddenimports = ['ooz', 'texture2ddecoder', 'pyopengltk.win32']
hiddenimports += collect_submodules('OpenGL')


a = Analysis(
    ['launcher.py'],
    pathex=[],
    binaries=[],
    datas=[('apex_asset_studio/resources', 'apex_asset_studio/resources'), ('third_party/dxc', 'third_party/dxc'), ('blender_addon/ApexAssetStudio_Blender_5.2.zip', 'blender_addon')],
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='ApexAssetStudio',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=['apex_asset_studio/resources/asuka.ico'],
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='ApexAssetStudio',
)
