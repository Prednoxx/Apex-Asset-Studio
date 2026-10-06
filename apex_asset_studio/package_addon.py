"""Create the installable Blender add-on ZIP from source, excluding bytecode.

The files sit at the root of the ZIP next to blender_manifest.toml, which is the Blender 4.2+ extension layout:
install it with Edit > Preferences > Get Extensions > (menu) Install from Disk, or drag it into Blender."""
from pathlib import Path
from zipfile import ZipFile, ZIP_DEFLATED


def main():
    root = Path(__file__).resolve().parent.parent/'blender_addon'
    source = root/'apex_asset_studio_blender'
    with ZipFile(root/'ApexAssetStudio_Blender_5.2.zip','w',ZIP_DEFLATED) as archive:
        for path in sorted(source.rglob('*')):
            if path.is_file() and '__pycache__' not in path.parts and path.suffix != '.pyc':
                archive.write(path,path.relative_to(source))


if __name__ == '__main__': main()
