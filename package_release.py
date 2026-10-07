"""Release archives and checksums."""
import argparse
import hashlib
import importlib.metadata
import shutil
from pathlib import Path
from zipfile import ZipFile, ZIP_DEFLATED

from apex_asset_studio import __version__ as VERSION


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--destination',help='default: the Releases folder next to Source');args=parser.parse_args()
    root=Path(__file__).resolve().parent;out=(Path(args.destination) if args.destination else Path(__file__).resolve().parent.parent/'Releases').resolve();out.mkdir(parents=True,exist_ok=True)
    master=root.parent  # Build outputs beside Source
    if not (master/'ApexAssetStudio.exe').exists() or not (master/'_internal').is_dir():
        raise RuntimeError('Build the Windows EXE first (Build portable app.bat)')
    addon=root/'blender_addon/ApexAssetStudio_Blender_5.2.zip'
    shutil.copy2(addon,out/addon.name)
    licenses={}
    for name in ['pyooz','Pillow','texture2ddecoder','pyinstaller','numpy','PyOpenGL','pyopengltk']:
        distribution=importlib.metadata.distribution(name)
        for item in distribution.files or []:
            if any(word in str(item).lower() for word in ('license','copying','notice')):
                source=Path(distribution.locate_file(item))
                if source.is_file(): licenses[f'third_party_licenses/{name}/{source.name}']=source
    import sys
    base=Path(sys.base_prefix)  # Python and Tcl/Tk licenses
    for name,source in (('Python/LICENSE.txt',base/'LICENSE.txt'),('Tcl/license.terms',base/'tcl'/'tcl8.6'/'license.terms'),
                        ('Tk/license.terms',base/'tcl'/'tk8.6'/'license.terms')):
        if source.is_file(): licenses[f'third_party_licenses/{name}']=source
    sourcezip=out/f'ApexAssetStudio-{VERSION}-source.zip'
    with ZipFile(sourcezip,'w',ZIP_DEFLATED,compresslevel=6) as archive:
        files=[p for p in root.iterdir() if p.is_file() and p.suffix in ('.py','.bat','.md','.toml','.txt','.spec')]
        files.append(root/'LICENSE')
        for folder in ['apex_asset_studio','tests','blender_addon','installer','third_party']:
            files.extend(p for p in (root/folder).rglob('*') if p.is_file() and '__pycache__' not in p.parts and p.suffix!='.pyc')
        for path in sorted(set(files)): archive.write(path,Path('ApexAssetStudio-source')/path.relative_to(root))
    with ZipFile(sourcezip) as archive:
        if archive.testzip(): raise RuntimeError('Source ZIP integrity failure')
    portable=out/f'ApexAssetStudio-{VERSION}-portable.zip'
    with ZipFile(portable,'w',ZIP_DEFLATED,compresslevel=6) as archive:
        archive.write(master/'ApexAssetStudio.exe','ApexAssetStudio/ApexAssetStudio.exe')
        for path in sorted((master/'_internal').rglob('*')):
            if path.is_file(): archive.write(path,Path('ApexAssetStudio')/path.relative_to(master))
        for name in ['README.md','LICENSE','THIRD_PARTY_NOTICES.md']: archive.write(root/name,f'ApexAssetStudio/{name}')
        archive.write(addon,f'ApexAssetStudio/{addon.name}')
        for name,source in licenses.items(): archive.write(source,f'ApexAssetStudio/{name}')
    with ZipFile(portable) as archive:
        if archive.testzip(): raise RuntimeError('Portable ZIP integrity failure')
    paths=[portable,sourcezip,out/addon.name]
    (out/'SHA256SUMS.txt').write_text('\n'.join(hashlib.sha256(p.read_bytes()).hexdigest()+'  '+p.name for p in paths)+'\n')
    for path in paths: print(path,path.stat().st_size)


if __name__=='__main__':main()
