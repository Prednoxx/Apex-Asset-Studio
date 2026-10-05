"""Independent CAST v1 serializer. See dtzxporter/cast format specification."""
import struct
from pathlib import Path


class Node:
    def __init__(self, kind, hash_id):
        self.kind, self.hash = kind.encode(), hash_id
        self.properties, self.children = [], []
    def prop(self, name, kind, values):
        components = {'2v':2,'3v':3,'4v':4}.get(kind,1)
        if kind == 's': count, data = 1, values.encode('utf-8') + b'\0'
        else:
            values = [x for row in values for x in row] if components > 1 else list(values)
            count = len(values)//components
            fmt = {'b':'B','h':'H','i':'I','l':'Q','f':'f','2v':'f','3v':'f','4v':'f'}[kind]
            data = struct.pack('<' + fmt*len(values), *values)
        name = name.encode(); self.properties.append(struct.pack('<2sHI',kind.encode(),len(name),count)+name+data)
        return self
    def encode(self):
        body = b''.join(self.properties) + b''.join(n.encode() for n in self.children)
        return struct.pack('<4sIQII',self.kind,24+len(body),self.hash,len(self.properties),len(self.children))+body


def write_cast(model, materials, path, lod=0, animation=None):
    counter = 1
    def node(kind):
        nonlocal counter
        n = Node(kind,counter); counter += 1; return n
    root = node('root'); mn = node('modl').prop('n','s',Path(model.name).stem)
    root.children.append(mn)
    mat_hashes = {}
    for i,desc in enumerate(materials):
        mat = node('matl').prop('n','s',desc['name']).prop('t','s','pbr')
        slots={'basecolor':'albedo','normal':'normal','specular':'specular','emission':'emissive',
               'gloss':'gloss','roughness':'roughness','ao':'ao','cavity':'cavity'}
        assigned=set()
        for binding in desc.get('textures',[]):
            slot=slots.get(binding.get('role'))
            if not slot or not binding.get('path') or slot in assigned: continue
            reference=node('file').prop('p','s',binding['path'])
            mat.children.append(reference);mat.prop(slot,'l',[reference.hash]);assigned.add(slot)
        mn.children.append(mat); mat_hashes[desc.get('source_slot',i)]=mat.hash
    skeleton = node('skel'); mn.children.append(skeleton)
    for bone in model.bones:
        bn = node('bone').prop('n','s',bone.name).prop('p','i',[bone.parent & 0xffffffff])
        bn.prop('lp','3v',[bone.translation]).prop('lr','4v',[bone.rotation]).prop('s','3v',[bone.scale]).prop('ssc','b',[0])
        skeleton.children.append(bn)
    for mesh in model.lods[lod]:
        if not mesh.positions or not mesh.indices: continue
        max_weight = max(len(w) for w in mesh.weights)
        layers = len(mesh.uvs[0]) if mesh.uvs else 0
        me = node('mesh').prop('n','s',mesh.name).prop('vp','3v',mesh.positions).prop('vn','3v',mesh.normals)
        if mesh.tangents: me.prop('vt','3v',[t[:3] for t in mesh.tangents])
        indices = [index for i in range(0, len(mesh.indices), 3)
                   for index in (mesh.indices[i], mesh.indices[i+2], mesh.indices[i+1])]
        me.prop('f','h',indices).prop('m','l',[mat_hashes[mesh.material]]).prop('ul','b',[layers])
        me.prop('mi','b',[max_weight]).prop('sm','s','linear')
        bones, weights = [], []
        for influences in mesh.weights:
            bones.extend([b for b,w in influences] + [0]*(max_weight-len(influences)))
            weights.extend([w for b,w in influences] + [0]*(max_weight-len(influences)))
        me.prop('wb','h',bones).prop('wv','f',weights)
        for i in range(layers): me.prop(f'u{i}','2v',[uv[i] for uv in mesh.uvs])
        if mesh.colors: me.prop('cl','b',[1]).prop('c0','4v',[tuple(c/255 for c in row) for row in mesh.colors])
        mn.children.append(me)
    if animation is not None:
        clip=node('anim').prop('n','s',animation['name']).prop('fr','f',[animation['fps']]).prop('lo','b',[int(animation['loop'])])
        root.children.append(clip)
        animation_skeleton=node('skel');clip.children.append(animation_skeleton)
        for bone in model.bones:
            bn=node('bone').prop('n','s',bone.name).prop('p','i',[bone.parent & 0xffffffff])
            bn.prop('lp','3v',[bone.translation]).prop('lr','4v',[bone.rotation]).prop('s','3v',[bone.scale]).prop('ssc','b',[0])
            animation_skeleton.children.append(bn)
        for i,bone in enumerate(model.bones):
            channels=[('rq','4v',animation['rotations'][:,i])]
            channels.extend((f't{axis}','f',animation['positions'][:,i,j]) for j,axis in enumerate('xyz'))
            channels.extend((f's{axis}','f',animation['scales'][:,i,j]) for j,axis in enumerate('xyz'))
            for key,kind,values in channels:
                curve=node('curv').prop('nn','s',bone.name).prop('kp','s',key).prop('m','s','absolute')
                curve.prop('kb','i',range(animation['frames'])).prop('kv',kind,values)
                clip.children.append(curve)
    path = Path(path)
    path.write_bytes(struct.pack('<4sIII',b'cast',1,1,0)+root.encode())
    return path
