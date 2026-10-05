bl_info = {
    "name": "Apex Asset Studio",
    "author": "Apex Asset Studio",
    "version": (0, 3, 1),
    "blender": (5, 2, 0),
    "location": "View3D > Sidebar > AAS",
    "description": "Import models and materials from Apex Asset Studio",
    "category": "Import-Export",
}

import json
from pathlib import Path
import bpy
from bpy.props import StringProperty
from bpy.types import Operator, Panel, PropertyGroup


def build_material(desc, base):
    name=desc['name']
    mat=next((m for m in bpy.data.materials if m.get('aas_guid')==desc['guid']),None)
    if mat is None:
        existing=bpy.data.materials.get(name)
        mat=existing if existing is not None and existing.get('aas_guid',existing.get('apex_guid'))==desc['guid'] else bpy.data.materials.new(name)
    mat.use_nodes=True
    mat['aas_guid']=desc['guid']
    mat['aas_resolution_status']=desc['status']
    tree=mat.node_tree; tree.nodes.clear()
    textures={t['role']:t for t in desc.get('textures',[]) if t.get('path')}
    constants={k:v['value'] for k,v in desc.get('constant_buffer',{}).get('values',{}).items()}
    scatter=constants.get('c_L0_scatterAmountAndRatio',[0,0,0,0])
    blend=desc.get('render_state',{}).get('targets',[{'enabled':False}])[0]['enabled']
    opacity=constants.get('c_opacity',[1.])[0]
    roles=[r for r in ('basecolor','normal','specular','gloss','ao','cavity','emission','alpha') if r in textures]
    if 'scatter_thickness' in textures and textures['scatter_thickness'].get('blender_mapping') and scatter[3]>0:
        roles.append('scatter_thickness')
    if 'anisotropy_direction' in textures and textures['anisotropy_direction'].get('anisotropy_conversion'):
        roles.append('anisotropy_direction')
    defaults={}
    if 'specular' not in roles and all('c_L0_perfSpecColor'+a in constants and constants['c_L0_perfSpecColor'+a][0] is not None for a in 'XYZ'):
        roles.append('specular');defaults['specular']=tuple(constants['c_L0_perfSpecColor'+a][0] for a in 'XYZ')+(1.,)
    if 'gloss' not in roles and constants.get('c_L0_perfGlossAndL1_albedoTint',[None])[0] is not None:
        roles.append('gloss');defaults['gloss']=constants['c_L0_perfGlossAndL1_albedoTint'][0]
    group_name='AAS Surface '+desc['guid']
    group=bpy.data.node_groups.get(group_name) or bpy.data.node_groups.new(group_name,'ShaderNodeTree')
    group.nodes.clear(); group.interface.clear()
    names={'basecolor':'Base Color','normal':'Normal','specular':'Specular','gloss':'Gloss',
           'ao':'AO','cavity':'Cavity','emission':'Emission','alpha':'Alpha',
           'scatter_thickness':'Skin Profile','anisotropy_direction':'Strand Direction'}
    for role in roles:
        scalar=role in ('gloss','ao','cavity','alpha')
        socket=group.interface.new_socket(name=names[role],in_out='INPUT',socket_type='NodeSocketFloat' if scalar else 'NodeSocketColor')
        socket.default_value=defaults.get(role,1. if scalar else (1,1,1,1))
    group.interface.new_socket(name='Shader',in_out='OUTPUT',socket_type='NodeSocketShader')
    nodes=group.nodes; links=group.links
    inputs=nodes.new('NodeGroupInput'); inputs.location=(-850,0)
    output=nodes.new('NodeGroupOutput'); output.location=(700,0)
    diffuse=nodes.new('ShaderNodeBsdfDiffuse'); diffuse.location=(100,120)
    color=inputs.outputs.get('Base Color')
    for role in ('ao','cavity'):
        if role not in roles: continue
        multiply=nodes.new('ShaderNodeMixRGB'); multiply.blend_type='MULTIPLY'
        multiply.inputs[0].default_value=1.; multiply.location=(-350,-150*roles.index(role))
        if color: links.new(color,multiply.inputs[1])
        links.new(inputs.outputs[names[role]],multiply.inputs[2]); color=multiply.outputs[0]
    normal=None
    if 'normal' in roles:
        normal=nodes.new('ShaderNodeNormalMap'); normal.location=(-100,-250)
        links.new(inputs.outputs['Normal'],normal.inputs['Color'])
        links.new(normal.outputs['Normal'],diffuse.inputs['Normal'])
    roughness=None
    if 'gloss' in roles:
        if 'gloss' in textures and textures['gloss'].get('roughness_conversion')!='one_minus_reflected_gloss_channel':
            raise ValueError('Gloss conversion is unresolved for '+name)
        roughness=nodes.new('ShaderNodeMath');roughness.operation='SUBTRACT';roughness.location=(-100,-100)
        roughness.inputs[0].default_value=1.;roughness.use_clamp=True
        links.new(inputs.outputs['Gloss'],roughness.inputs[1])
        links.new(roughness.outputs[0],diffuse.inputs['Roughness'])
    surface=diffuse.outputs[0];glossy=None
    if 'specular' in roles:
        inverse=nodes.new('ShaderNodeVectorMath'); inverse.operation='SUBTRACT'; inverse.location=(-550,200)
        inverse.inputs[0].default_value=(1,1,1)
        links.new(inputs.outputs['Specular'],inverse.inputs[1])
        energy=nodes.new('ShaderNodeMixRGB'); energy.blend_type='MULTIPLY'; energy.location=(-100,160)
        energy.inputs[0].default_value=1.
        if color: links.new(color,energy.inputs[1])
        links.new(inverse.outputs[0],energy.inputs[2]); color=energy.outputs[0]
        glossy=nodes.new('ShaderNodeBsdfMetallic');glossy.fresnel_type='F82';glossy.distribution='MULTI_GGX';glossy.location=(100,-80)
        glossy.label='GGX Fresnel';glossy.inputs['Edge Tint'].default_value=(1,1,1,1)
        links.new(inputs.outputs['Specular'],glossy.inputs['Base Color'])
        if normal: links.new(normal.outputs['Normal'],glossy.inputs['Normal'])
        if roughness: links.new(roughness.outputs[0],glossy.inputs['Roughness'])
        if 'anisotropy_direction' in roles and roughness:
            tangent=nodes.new('ShaderNodeNormalMap');tangent.label='Strand tangent';tangent.location=(-100,-520)
            links.new(inputs.outputs['Strand Direction'],tangent.inputs['Color']);links.new(tangent.outputs[0],glossy.inputs['Tangent'])
            stretch=constants.get('c_L0_anisoSpecStretchAmount',[0])[0]
            widen=nodes.new('ShaderNodeMath');widen.operation='MULTIPLY';widen.inputs[1].default_value=stretch
            links.new(inputs.outputs['Gloss'],widen.inputs[0]);widen.location=(-550,-700)
            second=nodes.new('ShaderNodeMath');second.operation='ADD';second.location=(-350,-700)
            links.new(roughness.outputs[0],second.inputs[0]);links.new(widen.outputs[0],second.inputs[1])
            product=nodes.new('ShaderNodeMath');product.operation='MULTIPLY';product.location=(-100,-700)
            links.new(roughness.outputs[0],product.inputs[0]);links.new(second.outputs[0],product.inputs[1])
            geometric=nodes.new('ShaderNodeMath');geometric.operation='SQRT';geometric.location=(100,-700)
            links.new(product.outputs[0],geometric.inputs[0]);links.new(geometric.outputs[0],glossy.inputs['Roughness'])
            ratio=nodes.new('ShaderNodeMath');ratio.operation='DIVIDE';ratio.location=(-350,-900)
            links.new(roughness.outputs[0],ratio.inputs[0]);links.new(second.outputs[0],ratio.inputs[1])
            fourth=nodes.new('ShaderNodeMath');fourth.operation='POWER';fourth.inputs[1].default_value=4.;fourth.location=(-100,-900)
            links.new(ratio.outputs[0],fourth.inputs[0])
            invert=nodes.new('ShaderNodeMath');invert.operation='SUBTRACT';invert.inputs[0].default_value=1.;invert.location=(100,-900)
            links.new(fourth.outputs[0],invert.inputs[1])
            amount=nodes.new('ShaderNodeMath');amount.operation='DIVIDE';amount.inputs[1].default_value=.9;amount.use_clamp=True;amount.location=(300,-900)
            links.new(invert.outputs[0],amount.inputs[0]);links.new(amount.outputs[0],glossy.inputs['Anisotropy'])
    if color: links.new(color,diffuse.inputs['Color'])
    if 'scatter_thickness' in roles:
        skin=nodes.new('ShaderNodeSubsurfaceScattering');skin.falloff='RANDOM_WALK_SKIN';skin.location=(100,450)
        skin.label='Skin scattering';skin.inputs['Scale'].default_value=.005
        links.new(inputs.outputs['Skin Profile'],skin.inputs['Radius'])
        if color: links.new(color,skin.inputs['Color'])
        if normal: links.new(normal.outputs[0],skin.inputs['Normal'])
        if roughness and skin.inputs.get('Roughness'): links.new(roughness.outputs[0],skin.inputs['Roughness'])
        mix=nodes.new('ShaderNodeMixShader');mix.inputs[0].default_value=scatter[3];mix.location=(350,400)
        links.new(surface,mix.inputs[1]);links.new(skin.outputs[0],mix.inputs[2]);surface=mix.outputs[0]
        mat['aas_skin_mapping']='Blender physical approximation; profile RGB radius, 0.005 m scale'
    if glossy:
        add=nodes.new('ShaderNodeAddShader');add.location=(500,200)
        links.new(surface,add.inputs[0]);links.new(glossy.outputs[0],add.inputs[1]);surface=add.outputs[0]
    if 'emission' in roles:
        emission=nodes.new('ShaderNodeEmission'); emission.location=(100,-450)
        links.new(inputs.outputs['Emission'],emission.inputs['Color'])
        add=nodes.new('ShaderNodeAddShader'); add.location=(500,120)
        links.new(surface,add.inputs[0]); links.new(emission.outputs[0],add.inputs[1]); surface=add.outputs[0]
    if 'alpha' in roles or blend:
        transparent=nodes.new('ShaderNodeBsdfTransparent'); transparent.location=(350,-300)
        mix=nodes.new('ShaderNodeMixShader'); mix.location=(500,0)
        mix.inputs[0].default_value=opacity
        if 'alpha' in roles: links.new(inputs.outputs['Alpha'],mix.inputs[0])
        links.new(transparent.outputs[0],mix.inputs[1])
        links.new(surface,mix.inputs[2]); surface=mix.outputs[0]
        mat.surface_render_method='DITHERED'
    links.new(surface,output.inputs['Shader'])
    shader=tree.nodes.new('ShaderNodeGroup'); shader.node_tree=group; shader.label='Apex Surface'; shader.location=(0,0)
    out=tree.nodes.new('ShaderNodeOutputMaterial'); out.location=(280,0)
    tree.links.new(shader.outputs['Shader'],out.inputs['Surface'])
    missing=[]
    for index,role in enumerate(roles):
        if role not in textures: continue
        tex=textures[role]; path=base/tex['path']
        if not path.exists(): missing.append(str(path)); continue
        node=tree.nodes.new('ShaderNodeTexImage'); node.label=names[role]; node.location=(-600,-240*index)
        node.image=bpy.data.images.load(str(path),check_existing=True)
        node.image.reload()
        node.image.colorspace_settings.name=tex['colorspace']
        node.image.alpha_mode='CHANNEL_PACKED'
        node['aas_role']=role; node['aas_guid']=tex['guid']
        node['aas_channels']=json.dumps(tex.get('derived_channels',tex['channels']))
        source=node.outputs['Color']
        if role in ('gloss','ao','cavity','alpha'):
            channel=tex.get('scalar_channel')
            if channel not in ('R','G','B','A'): raise ValueError('Channel is unresolved: '+role+' / '+name)
            if channel=='A': source=node.outputs['Alpha']
            else:
                split=tree.nodes.new('ShaderNodeSeparateColor'); split.location=(-330,-240*index)
                tree.links.new(source,split.inputs['Color']); source=split.outputs[{'R':'Red','G':'Green','B':'Blue'}[channel]]
        tree.links.new(source,shader.inputs[names[role]])
    if blend and 'alpha' not in roles and 'basecolor' in textures and 'A' in textures['basecolor'].get('shader_sampled_channels',[]):
        image=next((n for n in tree.nodes if n.type=='TEX_IMAGE' and n.get('aas_role')=='basecolor'),None)
        if image is None: raise FileNotFoundError(textures['basecolor']['path'])
        alpha=nodes.new('ShaderNodeMath');alpha.operation='MULTIPLY';alpha.inputs[1].default_value=opacity;alpha.location=(350,-400)
        # Alpha is independent of RGB in the source packed image.
        socket=group.interface.new_socket(name='Base Alpha',in_out='INPUT',socket_type='NodeSocketFloat');socket.default_value=1.
        links.new(inputs.outputs['Base Alpha'],alpha.inputs[0]);links.new(alpha.outputs[0],mix.inputs[0])
        tree.links.new(image.outputs['Alpha'],shader.inputs['Base Alpha'])
    mat['aas_missing_textures']=json.dumps(missing)
    if missing: mat['aas_resolution_status']='missing_textures'
    mat['aas_shader_revision']=2
    return mat


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


class AASSettings(PropertyGroup):
    manifest_path: StringProperty(name="Asset Manifest", subtype="FILE_PATH")


class AAS_OT_Import(Operator):
    bl_idname = "aas.import_asset"
    bl_label = "Import Apex Asset"
    bl_options = {"REGISTER", "UNDO"}
    filepath: StringProperty(subtype="FILE_PATH")
    filter_glob: StringProperty(default='*.aas.json', options={'HIDDEN'})

    def execute(self, context):
        path = Path(self.filepath or context.scene.aas_settings.manifest_path)
        if not path.exists():
            self.report({"ERROR"}, "Select a valid .aas.json manifest")
            return {"CANCELLED"}
        try:
            context.scene.aas_settings.manifest_path = str(path)
            desc, mats = import_manifest(path)
            self.report({"INFO"}, f"Imported {desc.get('display_name','Apex asset')} / {len(mats)} materials")
            return {"FINISHED"}
        except Exception as exc:
            self.report({"ERROR"}, str(exc))
            return {"CANCELLED"}

    def invoke(self, context, event):
        context.window_manager.fileselect_add(self)
        return {"RUNNING_MODAL"}


class AAS_OT_Rebuild(Operator):
    bl_idname = "aas.rebuild_materials"
    bl_label = "Build / Rebuild Materials"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        path = Path(context.scene.aas_settings.manifest_path)
        if not path.exists():
            self.report({"ERROR"}, "Select an .aas.json file")
            return {"CANCELLED"}
        try:
            desc, mats = build_manifest_materials(path)
            self.report({"INFO"}, f"Rebuilt {len(mats)} materials")
            return {"FINISHED"}
        except Exception as exc:
            self.report({"ERROR"}, str(exc))
            return {"CANCELLED"}


class AAS_OT_Retry(Operator):
    bl_idname = "aas.retry_materials"
    bl_label = "Retry Materials"
    bl_options = {"REGISTER", "UNDO"}

    execute = AAS_OT_Rebuild.execute


class AAS_PT_Main(Panel):
    bl_label = "Apex Asset Studio"
    bl_idname = "AAS_PT_main"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "AAS"

    def draw(self, context):
        layout = self.layout
        settings = context.scene.aas_settings
        layout.prop(settings, "manifest_path", text="Export file")
        layout.operator("aas.import_asset", icon="IMPORT")
        layout.separator()
        layout.operator("aas.rebuild_materials", icon="MATERIAL")
        layout.operator("aas.retry_materials", icon="FILE_REFRESH")


classes = (AASSettings, AAS_OT_Import, AAS_OT_Rebuild, AAS_OT_Retry, AAS_PT_Main)


def menu_func_import(self, context):
    self.layout.operator(AAS_OT_Import.bl_idname, text="Apex Asset Studio (.aas.json)")


def register():
    for cls in classes:
        bpy.utils.register_class(cls)
    bpy.types.Scene.aas_settings = bpy.props.PointerProperty(type=AASSettings)
    bpy.types.TOPBAR_MT_file_import.append(menu_func_import)


def unregister():
    bpy.types.TOPBAR_MT_file_import.remove(menu_func_import)
    del bpy.types.Scene.aas_settings
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
