"""Create an installable Blender addon ZIP from source, excluding bytecode."""
from pathlib import Path
from zipfile import ZipFile, ZIP_DEFLATED


def main():
    root = Path(__file__).resolve().parent.parent/'blender_addon'
    source = root/'apex_asset_studio_blender'
    with ZipFile(root/'ApexAssetStudio_Blender_5.2.zip','w',ZIP_DEFLATED) as archive:
        for path in sorted(source.rglob('*')):
            if path.is_file() and '__pycache__' not in path.parts and path.suffix != '.pyc':
                archive.write(path,path.relative_to(root))


if __name__ == '__main__': main()
