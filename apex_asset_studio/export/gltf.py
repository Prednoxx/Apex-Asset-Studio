"""glTF 2.0 writer; native geometry and all skin influences, without converter tools."""
import json
import struct
from pathlib import Path
from urllib.parse import quote


def write_gltf(model, materials, path, lod=0, animation=None):
    path = Path(path)
    data = bytearray()
    doc = {'asset': {'version': '2.0', 'generator': 'Apex Asset Studio native exporter'},
           'scene': 0, 'scenes': [{'nodes': [0]}], 'nodes': [{'name': Path(model.name).stem, 'children': []}],
           'meshes': [], 'skins': [], 'materials': [], 'bufferViews': [], 'accessors': [],
           'buffers': [{'byteLength': 0}], 'extras': {'apex_model_guid': model.guid, 'skin_family': model.family,
           'lod': lod, 'source_units': 'inches', 'warnings': model.warnings}}
    def accessor(values, fmt, component, kind, components, target=None, bounds=False):
        while len(data) % 4: data.append(0)
        start = len(data)
        flat = [x for row in values for x in row] if components > 1 else list(values)
        data.extend(struct.pack('<' + fmt * len(flat), *flat))
        view = {'buffer': 0, 'byteOffset': start, 'byteLength': len(data) - start}
        if target: view['target'] = target
        vi = len(doc['bufferViews']); doc['bufferViews'].append(view)
        item = {'bufferView': vi, 'componentType': component, 'count': len(values), 'type': kind}
        if bounds:
            item['min'] = [min(row[i] for row in values) for i in range(components)]
            item['max'] = [max(row[i] for row in values) for i in range(components)]
        ai = len(doc['accessors']); doc['accessors'].append(item); return ai
    textures = {}
    def texture(uri):
        if uri not in textures:
            idx = len(textures); textures[uri] = idx
            doc.setdefault('images', []).append({'uri': uri})
            doc.setdefault('textures', []).append({'source': idx})
        return {'index': textures[uri]}
    material_indices={m.get('source_slot',i):i for i,m in enumerate(materials)}
    for i, desc in enumerate(materials):
        mat = {'name': desc['name'], 'extras': {'apex_guid': desc.get('guid',model.materials[desc.get('source_slot',i)]), 'resolution_status': desc.get('status', 'unresolved')},
               'pbrMetallicRoughness': {'metallicFactor': 0}}
        for binding in desc.get('textures', []):
            if binding.get('role') == 'basecolor' and binding.get('path'):
                mat['pbrMetallicRoughness']['baseColorTexture'] = texture(binding['path'])
            if binding.get('role') == 'normal' and binding.get('path'):
                mat['normalTexture'] = texture(binding['path'])
        doc['materials'].append(mat)
    bone_start = 1
    for i, bone in enumerate(model.bones):
        doc['nodes'].append({'name': bone.name, 'translation': [v*.0254 for v in bone.translation], 'rotation': list(bone.rotation),
                             'scale': list(bone.scale)})
        parent = 0 if bone.parent < 0 else bone_start + bone.parent
        doc['nodes'][parent].setdefault('children', []).append(bone_start + i)
    if model.bones:
        matrices = []
        for bone in model.bones:
            m = bone.inverse_bind
            matrices.append((m[0],m[4],m[8],0, m[1],m[5],m[9],0, m[2],m[6],m[10],0, m[3]*.0254,m[7]*.0254,m[11]*.0254,1))
        ibm = accessor(matrices, 'f', 5126, 'MAT4', 16)
        doc['skins'].append({'name': 'ApexSkeleton', 'inverseBindMatrices': ibm, 'joints': list(range(1,len(model.bones)+1)), 'skeleton': 1})
    for mesh in model.lods[lod]:
        if not mesh.positions or not mesh.indices: continue
        attr = {'POSITION': accessor([tuple(v*.0254 for v in p) for p in mesh.positions], 'f', 5126, 'VEC3', 3, 34962, True),
                'NORMAL': accessor(mesh.normals, 'f', 5126, 'VEC3', 3, 34962)}
        if mesh.tangents: attr['TANGENT'] = accessor(mesh.tangents,'f',5126,'VEC4',4,34962)
        for layer in range(len(mesh.uvs[0]) if mesh.uvs else 0):
            attr[f'TEXCOORD_{layer}'] = accessor([uv[layer] for uv in mesh.uvs], 'f',5126,'VEC2',2,34962)
        if mesh.colors:
            attr['COLOR_0'] = accessor([tuple(c/255 for c in row) for row in mesh.colors], 'f',5126,'VEC4',4,34962)
        groups = (max((len(w) for w in mesh.weights), default=0)+3)//4
        for group in range(groups):
            joints, weights = [], []
            for influences in mesh.weights:
                part = influences[group*4:group*4+4]
                joints.append(tuple([b for b,w in part] + [0]*(4-len(part))))
                weights.append(tuple([w for b,w in part] + [0]*(4-len(part))))
            attr[f'JOINTS_{group}'] = accessor(joints,'H',5123,'VEC4',4,34962)
            attr[f'WEIGHTS_{group}'] = accessor(weights,'f',5126,'VEC4',4,34962)
        # Native VG triangles are clockwise; glTF defines counter-clockwise fronts.
        # Preserve decoded normals and vertices, and convert the index order only.
        indices = [index for i in range(0, len(mesh.indices), 3)
                   for index in (mesh.indices[i], mesh.indices[i+2], mesh.indices[i+1])]
        inds = accessor(indices,'H',5123,'SCALAR',1,34963)
        mi = len(doc['meshes'])
        doc['meshes'].append({'name': mesh.name, 'primitives': [{'attributes': attr, 'indices': inds,'material':material_indices[mesh.material],'mode':4}],
                              'extras': {'apex_material_guid': model.materials[mesh.material], 'lod':lod,
                                         'apex_uv_channels':getattr(mesh, 'uv_indices', [])}})
        node = {'name':mesh.name,'mesh':mi}
        if model.bones: node['skin'] = 0
        doc['scenes'][0]['nodes'].append(len(doc['nodes'])); doc['nodes'].append(node)
    if animation is not None:
        frames=animation['frames']
        times=accessor([i/animation['fps'] for i in range(frames)],'f',5126,'SCALAR',1)
        doc['accessors'][times].update(min=[0.],max=[(frames-1)/animation['fps']])
        clip={'name':animation['name'],'samplers':[],'channels':[],
              'extras':{k:animation[k] for k in ('guid','fps','loop','rig_guid','data_guid','blend')}}
        for i in range(len(model.bones)):
            for key,kind,width,factor in [('positions','translation',3,.0254),('rotations','rotation',4,1.),('scales','scale',3,1.)]:
                values=animation[key][:,i]*factor
                output=accessor(values,'f',5126,f'VEC{width}',width)
                clip['channels'].append({'sampler':len(clip['samplers']),'target':{'node':i+1,'path':kind}})
                clip['samplers'].append({'input':times,'output':output,'interpolation':'LINEAR'})
        doc['animations']=[clip]
    if not doc['skins']: del doc['skins']
    for key in ('meshes','materials'):
        if not doc[key]: del doc[key]
    if path.suffix.lower()=='.glb':
        for item in doc.get('images',[]):
            source=(path.parent/item.pop('uri')).resolve()
            if not source.is_relative_to(path.parent.resolve()): raise ValueError('image outside export package')
            while len(data)%4: data.append(0)
            start=len(data);data.extend(source.read_bytes())
            item['bufferView']=len(doc['bufferViews']);item['mimeType']='image/png'
            doc['bufferViews'].append({'buffer':0,'byteOffset':start,'byteLength':len(data)-start})
    doc['buffers'][0]['byteLength'] = len(data)
    if path.suffix.lower() == '.glb':
        raw = json.dumps(doc, separators=(',', ':')).encode()
        raw += b' ' * ((-len(raw)) % 4); data.extend(b'\0' * ((-len(data)) % 4))
        out = struct.pack('<4sII', b'glTF',2,12+8+len(raw)+8+len(data))
        out += struct.pack('<I4s',len(raw),b'JSON')+raw+struct.pack('<I4s',len(data),b'BIN\0')+data
        path.write_bytes(out)
    else:
        for image in doc.get('images',[]): image['uri']=quote(image['uri'])
        binary = path.with_suffix('.bin'); binary.write_bytes(data)
        doc['buffers'][0]['uri'] = quote(binary.name)
        path.write_text(json.dumps(doc, indent=2), encoding='utf-8')
    return path
