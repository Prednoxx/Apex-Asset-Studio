"""Consumer export bundle with explicit provenance and unresolved-data reporting."""
import json
from pathlib import Path
import struct
import tempfile
from dataclasses import replace
from ..repository import AssetRepository
from ..rpak.material import decode_material, safe_name
from .gltf import write_gltf
from .cast import write_cast


def export_animation(model, animation, path):
    path=Path(path)
    if not path.name.endswith('.aas.json'): raise ValueError('Animation export requires an .aas.json file')
    name=path.name[:-9]
    model_file=path.with_name(name+'.glb')
    skeleton=replace(model,lods={0:[]})
    write_gltf(skeleton,[],model_file,animation=animation)
    clip={k:v for k,v in animation.items() if k not in ('positions','rotations','scales')}
    manifest={'schema':1,'kind':'animation','display_name':animation['name'],'status':'decoded',
              'gltf':model_file.name,'materials':[],'animations':[clip],
              'metadata':{'model_guid':model.guid,'bone_count':len(model.bones),'blender_target':'5.2.2'}}
    path.write_text(json.dumps(manifest,indent=2,ensure_ascii=False),encoding='utf-8')
    return path,manifest


FORMATS = ('.glb', '.gltf', '.cast')


def export_package(model, catalog, game_root, destination, display_name, cosmetic=None, all_lods=False, progress=None, overwrite=False,
                   animation=None, formats=FORMATS, debug_data=False):
    formats = tuple(f for f in FORMATS if f in formats)
    if not formats: raise ValueError('Choose at least one export format')
    if not model.material_family_resolved:
        raise ValueError(f'Material set unavailable: {model.family}')
    root = Path(destination).expanduser().resolve(); root.mkdir(parents=True,exist_ok=True)
    label = safe_name(cosmetic['name'] if cosmetic else display_name)
    final = root/safe_name(display_name)
    if final.exists() and not overwrite: raise FileExistsError(final)
    if final.is_symlink(): raise ValueError(f'Export folder is a symbolic link: {final}')
    staging = tempfile.TemporaryDirectory(prefix='.export-',dir=root)
    directory = Path(staging.name)/'new'; directory.mkdir()
    materials = []
    used = {m.material for meshes in model.lods.values() for m in meshes}
    with AssetRepository(catalog,game_root) as repository:
        names = set()
        for index in sorted(used):
            guid=model.materials[index]
            if progress: progress(f'Resolving material {len(materials)+1}/{len(used)}')
            try:
                material = decode_material(repository,guid,model.source)
                part = safe_name(material['game_name'].rsplit('/',1)[-1].rsplit('_',1)[-1].replace('_',' ').title())
                name = part
                suffix = 2
                while name in names:
                    name=f'{part} {suffix}'; suffix+=1
                names.add(name)
                material = decode_material(repository,guid,model.source,directory/'textures'/name)
                material['name'] = name
            except (ValueError,KeyError,OSError,RuntimeError,struct.error) as exc:
                material = {'name':f'unresolved_{guid}','guid':guid,'status':'unresolved','textures':[],'error':str(exc)}
            material['source_slot']=index; materials.append(material)
        warnings = sorted(repository.warnings) + list(model.warnings)
    status = 'partial' if any(m.get('status') in ('partial','unresolved') for m in materials) or warnings else 'decoded'
    lods = sorted(model.lods) if all_lods else [min(model.lods)]
    files = []
    for lod in lods:
        if progress: progress(f'Writing LOD {lod}: ' + ', '.join(f[1:].upper() for f in formats))
        stem = label if lod==min(model.lods) else f'{label} LOD {lod}'
        writers = {'.glb': write_gltf, '.gltf': write_gltf, '.cast': write_cast}
        for extension in formats:
            writers[extension](model,materials,directory/(stem+extension),lod,animation if lod==min(model.lods) else None)
        if debug_data:  # raw packed normals, for decoder verification only
            raw_normals = [v for mesh in model.lods[lod] for v in mesh.packed_normals]
            (directory/(stem+'.packed_normals.bin')).write_bytes(struct.pack(f'<{len(raw_normals)}I',*raw_normals))
        files.append({'lod':lod,**{f[1:]: stem+f for f in formats},
                      'vertices':sum(len(m.positions) for m in model.lods[lod]),
                      'triangles':sum(len(m.indices)//3 for m in model.lods[lod]),
                      'uv_channels':{m.name:m.uv_indices for m in model.lods[lod]}})
    first = files[0]
    manifest = {'schema':1,'display_name':display_name,'source_game':'Apex Legends','status':status,
                'gltf':first.get('glb') or first.get('gltf'),'cast':first.get('cast'),'formats':[f[1:] for f in formats],'animations':[{k:animation[k] for k in
                    ('guid','name','fps','frames','loop','rig_guid','data_guid','blend','mapped_bones','source_name',
                     'sequence_name','activity','ik_rules','autolayers')}]
                    if animation is not None else [],'materials':materials,
                'metadata':{'model_guid':model.guid,'source_rpak':model.source,'material_family':model.family,
                'material_guids':model.materials,'lods':files,'lod_thresholds':model.thresholds,
                'bone_count':len(model.bones),'rig_guids':model.rig_guids,'cosmetic':cosmetic,
                'warnings':warnings,'animation_status':'decoded' if animation is not None else 'not_selected','blender_target':'5.2.2',
                'units':{'cast':'inches','gltf':'metres'},'up_axis':'Y',
                'unsupported_material_bindings':{m['guid']:m.get('unsupported_inputs',[]) for m in materials if m.get('unsupported_inputs')}}}
    manifest_path = directory/(label+'.aas.json')
    manifest_path.write_text(json.dumps(manifest,indent=2,ensure_ascii=False),encoding='utf-8')
    previous=Path(staging.name)/'previous'
    if final.exists(): final.replace(previous)
    try: directory.replace(final)
    except OSError:
        if previous.exists(): previous.replace(final)
        raise
    staging.cleanup()
    return final/manifest_path.name, manifest
