"""Imports an Apex Asset Studio export (.aas.json): the glTF/GLB model or animation plus its materials."""
import json
from pathlib import Path

import bpy

from .materials import build_material


def build_manifest_materials(path: Path):
    desc = json.loads(path.read_text(encoding='utf-8'))
    mats = [build_material(item,path.parent) for item in desc.get('materials', []) if item.get('status')!='unused']
    return desc,mats


def import_manifest(path: Path):
    desc = json.loads(path.read_text(encoding="utf-8"))
    base = path.parent
    before = set(bpy.data.objects)
    selected=set(bpy.context.selected_objects)
    targets={o for o in selected if o.type=='ARMATURE'}
    targets.update(m.object for o in selected if o.type=='MESH' for m in o.modifiers if m.type=='ARMATURE' and m.object)
    animation_only=desc.get('kind')=='animation'
    if animation_only and len(targets)>1: raise ValueError('Select one model or armature')
    gltf = desc.get("gltf") or desc.get("model")
    if not gltf:
        raise ValueError('Manifest contains no glTF/GLB model')
    model_path = (base / gltf).resolve() if not Path(gltf).is_absolute() else Path(gltf)
    if not model_path.exists() or model_path.suffix.lower() not in {'.gltf','.glb'}:
        raise ValueError('Manifest model file is missing or unsupported')
    if desc.get('animations'):
        clip=desc['animations'][0]
        bpy.context.scene.render.fps=round(clip['fps'])
        bpy.context.scene.render.fps_base=round(clip['fps'])/clip['fps']
        bpy.context.scene.frame_start=0;bpy.context.scene.frame_end=clip['frames']-1
    bpy.ops.import_scene.gltf(filepath=str(model_path))
    imported = [o for o in bpy.data.objects if o not in before]
    if animation_only:
        rigs=[o for o in imported if o.type=='ARMATURE']
        if len(rigs)!=1: raise ValueError('Animation file does not contain one skeleton')
        source=rigs[0]
        if not source.animation_data or not source.animation_data.action: raise ValueError('Animation file contains no playable action')
        action=source.animation_data.action;slot=source.animation_data.action_slot
        action['aas_model_guid']=desc['metadata']['model_guid']
        if targets:
            target=next(iter(targets))
            try:
                if set(target.data.bones.keys())!=set(source.data.bones.keys()): raise ValueError('Animation skeleton does not match the selected model')
                for bone in source.data.bones:
                    other=target.data.bones[bone.name]
                    if (bone.parent.name if bone.parent else None)!=(other.parent.name if other.parent else None):
                        raise ValueError('Animation bone hierarchy does not match: '+bone.name)
                    if max(abs(bone.matrix_local[r][c]-other.matrix_local[r][c]) for r in range(4) for c in range(4))>1e-5:
                        raise ValueError('Animation bind pose does not match: '+bone.name)
                target.animation_data_create()
                previous=target.animation_data.action
                if previous and previous!=action:
                    track=target.animation_data.nla_tracks.new();track.name=previous.name;track.mute=True
                    strip=track.strips.new(previous.name,int(previous.frame_range[0]),previous)
                    strip.action_slot=target.animation_data.action_slot
                target.animation_data.action=action;target.animation_data.action_slot=slot
                target['aas_animation_manifest']=str(path)
                action.use_fake_user=True
            finally:
                for obj in imported: bpy.data.objects.remove(obj,do_unlink=True)
            bpy.context.view_layer.objects.active=target;target.select_set(True)
        else:
            source['aas_model_guid']=desc['metadata']['model_guid'];source['aas_animation_manifest']=str(path)
        return desc,[]
    desc,mats = build_manifest_materials(path)
    if any(t.get('role')=='alpha' for m in desc['materials'] for t in m.get('textures',[])):
        bpy.context.scene.cycles.transparent_max_bounces=max(16,bpy.context.scene.cycles.transparent_max_bounces)
    by_name = {m.name:m for m in mats}
    by_guid = {m['aas_guid']:m for m in mats}
    for obj in imported:
        obj['aas_manifest'] = str(path)
        obj['aas_model_guid']=desc.get('metadata',{}).get('model_guid','')
        if obj.type != 'MESH':
            continue
        for slot in obj.material_slots:
            if not slot.material:
                continue
            name = slot.material.name
            matching = by_guid.get(slot.material.get('apex_guid'))
            if matching is None:
                matching=next((mat for key,mat in by_name.items() if name == key or name.startswith(key+'.')),None)
            if matching:
                slot.material = matching
    return desc, mats
