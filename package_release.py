"""Package the existing frozen build, addon, licenses and matching application source."""
import argparse
import hashlib
import importlib.metadata
import shutil
from pathlib import Path
from zipfile import ZipFile, ZIP_DEFLATED


def archive_tree(source,output,prefix):
    with ZipFile(output,'w',ZIP_DEFLATED,compresslevel=6) as archive:
        for path in sorted(source.rglob('*')):
            if path.is_file(): archive.write(path,Path(prefix)/path.relative_to(source))
    with ZipFile(output) as archive:
        bad=archive.testzip()
        if bad: raise RuntimeError('ZIP integrity failure: '+bad)


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--destination',required=True);args=parser.parse_args()
    root=Path(__file__).resolve().parent;out=Path(args.destination).resolve();out.mkdir(parents=True,exist_ok=True)
    app=root/'dist/native-preview/ApexAssetStudio'
    if not (app/'ApexAssetStudio.exe').exists(): raise RuntimeError('Build the Windows EXE first')
    for name in ['README.txt','LICENSE','THIRD_PARTY_NOTICES.md']:
        shutil.copy2(root/name,app/name)
    addon=root/'blender_addon/ApexAssetStudio_Blender_5.2.zip'
    shutil.copy2(addon,app/addon.name);shutil.copy2(addon,out/addon.name)
    licenses=app/'third_party_licenses';licenses.mkdir(exist_ok=True)
    for name in ['pyooz','Pillow','texture2ddecoder','pyinstaller','numpy','PyOpenGL','pyopengltk']:
        distribution=importlib.metadata.distribution(name)
        for item in distribution.files or []:
            if any(word in str(item).lower() for word in ('license','copying','notice')):
                source=Path(distribution.locate_file(item))
                if source.is_file():
                    directory=licenses/name;directory.mkdir(exist_ok=True);shutil.copy2(source,directory/source.name)
    sourcezip=out/'ApexAssetStudio-0.3.1-source.zip'
    with ZipFile(sourcezip,'w',ZIP_DEFLATED,compresslevel=6) as archive:
        files=[p for p in root.iterdir() if p.is_file() and p.suffix in ('.py','.bat','.md','.toml','.txt','.spec')]
        files.append(root/'LICENSE')
        for folder in ['apex_asset_studio','tests','blender_addon','installer','third_party']:
            files.extend(p for p in (root/folder).rglob('*') if p.is_file() and '__pycache__' not in p.parts and p.suffix!='.pyc')
        for path in sorted(set(files)): archive.write(path,Path('ApexAssetStudio-source')/path.relative_to(root))
    with ZipFile(sourcezip) as archive:
        if archive.testzip(): raise RuntimeError('Source ZIP integrity failure')
    portable=out/'ApexAssetStudio-0.3.1-portable.zip';archive_tree(app,portable,'ApexAssetStudio')
    # Also provide a directly runnable extracted copy for this local workstation.
    shutil.copytree(app,out/'ApexAssetStudio',dirs_exist_ok=True)
    paths=[portable,sourcezip,out/addon.name]
    (out/'SHA256SUMS.txt').write_text('\n'.join(hashlib.sha256(p.read_bytes()).hexdigest()+'  '+p.name for p in paths)+'\n')
    for path in paths: print(path,path.stat().st_size)


if __name__=='__main__':main()
