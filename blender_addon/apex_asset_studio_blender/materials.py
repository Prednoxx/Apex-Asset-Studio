"""Builds Blender materials from the material descriptions in an Apex Asset Studio manifest."""
import json

import bpy


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
