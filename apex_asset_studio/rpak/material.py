"""Reflected material dependencies."""
import re
import math
import struct
from pathlib import Path
from .pages import PageReader
from .shader import material_bindings
from .texture import extract_texture
from .shader_analysis import convert_derivative_normal, convert_anisotropy_direction


def safe_name(text):
    return re.sub(r'[^A-Za-z0-9_ .-]+','_',text).strip(' .')[:100] or 'asset'


def decode_material(repository, guid, preferred=None, texture_directory=None):
    archive, asset = repository.asset(guid,preferred)
    if asset.type_name != 'matl' or asset.version != 23 or asset.header_struct_size not in (192,200):
        raise ValueError(f'material layout {asset.version}/{asset.header_struct_size} unsupported')
    r = PageReader(archive); p = r.header(asset)
    name = r.string(r.pointer(p+24))
    start = r.pointer(p+96); end = r.pointer(p+104)
    if end < start or (end-start)%8 or end-start > 8192: raise ValueError('invalid material texture table')
    sg = f'{struct.unpack_from("<Q",archive.data,p+88)[0]:016X}'
    desc = {'name':f'{safe_name(name.split("/")[-1])}__{guid}', 'game_name':name, 'guid':guid,
            'status':'decoded','source_rpak':str(archive.path),'shader_set':sg,'textures':[],
            'warnings':[]}
    snapshot=struct.unpack_from('<Q',archive.data,p+8)[0]
    if snapshot:
        sa,sx=repository.asset(f'{snapshot:016X}',archive.path)
        if sx.type_name!='msnp' or sx.version!=1 or sx.header_struct_size!=64: raise ValueError('Material render-state layout is unsupported')
        sr=PageReader(sa);sp=sr.header(sx)
        states=struct.unpack_from('<8I',sa.data,sp)
        desc['render_state']={'guid':f'{snapshot:016X}', 'blend_mask':struct.unpack_from('<I',sa.data,sp+32)[0],
            'targets':[{'enabled':bool(v&2),'source':(v>>2)&31,'destination':(v>>7)&31,
                        'operation':(v>>12)&7,'write_mask':v>>28} for v in states]}
        if texture_directory:
            original=Path(texture_directory)/'original';original.mkdir(parents=True,exist_ok=True)
            (original/'Material Render State.bin').write_bytes(sa.data[sp:sp+64])
    if getattr(archive,'pages_reconstructed',False): desc['patch_provenance'] = archive.patch_provenance
    reflection=None
    try:
        reflection = material_bindings(repository,sg)
        bindings = {x['slot']:x for x in reflection['resources'] if x['type']==2 and x['count']==1 and x.get('space',0)==0}
        resources = {x['slot']:x['name'] for x in reflection['resources'] if x['type']==2 and x['count']==1 and x.get('space',0)==0}
        desc['shader_reflection'] = {k:v for k,v in reflection.items() if not k.startswith('_')}
        if texture_directory:
            shader_dir=Path(texture_directory).parent.parent/'shaders';shader_dir.mkdir(parents=True,exist_ok=True)
            shader_stem=reflection['pixel_shader']+'_variant0'
            (shader_dir/(shader_stem+'.dxbc')).write_bytes(reflection['_bytecode'])
            if reflection['_disassembly']:
                (shader_dir/(shader_stem+'.txt')).write_text(reflection['_disassembly'],encoding='utf-8')
            desc['shader_reflection']['bytecode_path']='shaders/'+shader_stem+'.dxbc'
    except (ValueError,KeyError,OSError,struct.error) as exc:
        desc['warnings'].append(f'Shader reflection unresolved: {exc}'); resources = {}; bindings={}; desc['status'] = 'partial'
    try:
        cpu=r.resolve(asset.data,16) if asset.data.index>=0 else r.pointer(p+184,16,nullable=True)
        if cpu is not None:
            size=struct.unpack_from('<I',archive.data,cpu+8)[0]
            if size>4*1024*1024: raise ValueError('Material constant buffer exceeds size limit')
            pos=r.pointer(cpu,size); raw=bytes(archive.data[pos:pos+size])
            desc['constant_buffer']={'size':size,'values':{}}
            text=reflection.get('_disassembly') if reflection else None
            if text and '; cbuffer CBufUberStatic' in text:
                block=text.split('; cbuffer CBufUberStatic',1)[1].split('; cbuffer ',1)[0]
                for kind,width,name,offset in re.findall(r';\s*(float|uint|int|bool)([1-4]?)\s+(\w+)\s*;\s*; Offset:\s*(\d+)',block):
                    width=int(width or 1);offset=int(offset)
                    if offset+width*4<=size:
                        values=struct.unpack_from('<'+{'float':'f','int':'i','uint':'I','bool':'I'}[kind]*width,raw,offset)
                        item={'type':kind,'offset':offset,'value':[v if math.isfinite(v) else None for v in values]}
                        if None in item['value']: item['raw_hex']=raw[offset:offset+width*4].hex()
                        desc['constant_buffer']['values'][name]=item
            if texture_directory:
                original=Path(texture_directory)/'original';original.mkdir(parents=True,exist_ok=True)
                (original/'Material Constants.bin').write_bytes(raw)
                (original/'Material Header.bin').write_bytes(archive.data[p:p+asset.header_struct_size])
                desc['constant_buffer']['path']='textures/'+Path(texture_directory).name+'/original/Material Constants.bin'
    except (ValueError,struct.error,OSError) as exc:
        desc['warnings'].append(f'Material constants unresolved: {exc}');desc['status']='partial'
    # Roles from shader bindings
    known = {'colormap':'basecolor','basecolormap':'basecolor','albedomap':'basecolor',
             'normalmap':'normal','emissivemap':'emission','emissionmap':'emission',
             'specularmap':'specular','glossmap':'gloss','opacitymap':'alpha','aomap':'ao'}
    known.update({'albedotexture':'basecolor','normaltexture':'normal','emissivetexture':'emission',
                  'spectexture':'specular','glosstexture':'gloss','opacitymultiplytexture':'alpha','aotexture':'ao',
                  'cavitytexture':'cavity','scatterthicknesstexture':'scatter_thickness','anisospecdirtexture':'anisotropy_direction'})
    texture_names=set()
    for i,tg in enumerate(struct.unpack_from(f'<{(end-start)//8}Q',archive.data,start)):
        if not tg: continue
        semantic = resources.get(i)
        role = known.get((semantic or '').lower(),'unresolved')
        entry = {'slot':i,'guid':f'{tg:016X}','shader_resource':semantic,'role':role,'channels':'unresolved',
                 'colorspace':'sRGB' if role in ('basecolor','emission') else 'Non-Color'}
        channel_contract=bindings.get(i,{}).get('channel_contract',{})
        if channel_contract.get('sampled_components'):
            entry['shader_sampled_channels']=channel_contract['sampled_components']
            sampled=channel_contract['sampled_components']
            if len(sampled)==1 and sampled[0] in 'RGBA' and role in ('gloss','ao','alpha','cavity'):
                channel=sampled[0]
                entry['channels']={c:role if c==channel else 'not sampled' for c in 'RGBA'}
                entry['scalar_channel']=channel
                if role=='gloss' and channel_contract.get('one_minus_components')==[channel]:
                    entry['roughness_conversion']='one_minus_reflected_gloss_channel'
        direction=bindings.get(i,{}).get('anisotropy_contract')
        if role=='anisotropy_direction' and direction:
            entry['anisotropy_conversion']=direction
            entry['channels']={'R':'tangent angle in turns','G':'not sampled','B':'not sampled','A':'not sampled'}
        if role=='scatter_thickness' and channel_contract.get('sampled_components')==['A','B','G','R']:
            entry['channels']={'RGB':'skin scattering profile','A':'thickness; inverse used for transmission'}
            entry['blender_mapping']='physical_scattering_approximation'
        if texture_directory:
            try:
                ta,tx = repository.asset(entry['guid'],archive.path)
                stem = {'basecolor':'Base Color','normal':'Normal','gloss':'Gloss','specular':'Specular',
                        'ao':'Ambient Occlusion','cavity':'Cavity','alpha':'Alpha','emission':'Emission',
                        'scatter_thickness':'Skin Scattering','anisotropy_direction':'Strand Direction'}.get(role, safe_name(semantic or f'Slot {i}'))
                if stem in texture_names: stem+=f' Slot {i}'
                texture_names.add(stem)
                info = extract_texture(ta,tx,texture_directory,stem)
                entry['colorspace'] = 'sRGB' if info['srgb'] else 'Non-Color'
                entry['texture_type'] = info['texture_type']
                entry['role_evidence'] = reflection['method'] if semantic else 'unresolved; texture type code preserved'
                prefix='textures/'+Path(texture_directory).name+'/'
                entry.update({'dds':prefix+info['dds'],'path':prefix+info['png'] if info['png'] else None,
                              'texture_metadata':prefix+stem+'.texture.json','pixel_format':info['format'],
                              'status':'extracted' if info['png'] else 'dds_only'})
                if role=='anisotropy_direction' and direction and info['png']:
                    derived=stem+' Blender.png'
                    convert_anisotropy_direction(Path(texture_directory)/info['png'],Path(texture_directory)/derived,direction)
                    entry['original_png']=entry['path'];entry['path']=prefix+derived
                    entry['derived_channels']={'R':'tangent X, cosine remapped to 0-1',
                        'G':'tangent Y, negative sine remapped to 0-1','B':'8-bit midpoint; projected out of tangent'}
                if role == 'normal' and info['format'] == 8:
                    contract=bindings.get(i,{}).get('normal_contract')
                    entry['original_png']=entry['path']
                    if contract and info['png']:
                        derived=stem+' Blender.png'
                        convert_derivative_normal(Path(texture_directory)/info['png'],Path(texture_directory)/derived,contract)
                        entry['path']=prefix+derived;entry['normal_conversion']=contract
                        entry['derived_channels']={'R':'normal X remapped to 0-1','G':'normal Y remapped to 0-1','B':'normal Z remapped to 0-1'}
                        entry['channels']={'R':'tangent derivative X','G':'tangent derivative Y','B':'absent in original BC5','A':'absent in original BC5'}
                    else:
                        entry['role'] = 'normal_xy_unresolved'
                        entry['channels'] = {'R':'normal X','G':'normal Y','B':'absent in BC5','A':'absent in BC5'}
                        entry['warning'] = 'Normal encoding unsupported; texture is not connected.'
            except (ValueError,KeyError,OSError,struct.error,RuntimeError) as exc:
                entry['status'] = 'unresolved'; entry['error'] = str(exc)
                desc['status'] = 'partial'
        desc['textures'].append(entry)
    desc['unsupported_inputs']=[t.get('shader_resource') or f'Slot {t["slot"]}' for t in desc['textures']
                                if t['role'] not in ('basecolor','normal','specular','gloss','ao','cavity','emission','alpha')
                                and not (t['role']=='anisotropy_direction' and t.get('anisotropy_conversion'))
                                and not (t['role']=='scatter_thickness' and t.get('blender_mapping'))]
    if desc['unsupported_inputs']: desc['status']='partial'
    return desc
