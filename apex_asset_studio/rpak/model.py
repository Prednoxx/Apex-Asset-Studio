"""Studio v20, VG rev4."""
from dataclasses import dataclass, field
import math
import struct
import numpy as np
from .pages import PageReader
from .streaming import StreamingReader
from .rtech import OodleRuntime
from .oodle_stream import decompress_stream


def fix(v):
    return (v & 0xfffe) << (4 * (v & 1))


class Buffer:
    def __init__(self, data): self.data = data
    def unpack(self, fmt, pos):
        n = struct.calcsize(fmt)
        if pos < 0 or pos + n > len(self.data): raise ValueError('model read outside buffer')
        return struct.unpack_from(fmt, self.data, pos)
    def u16(self, p): return self.unpack('<H', p)[0]
    def string(self, p):
        if p < 0 or p >= len(self.data): raise ValueError('invalid model string offset')
        end = self.data.find(b'\0', p, min(len(self.data), p + 4096))
        if end < 0: raise ValueError('unterminated model string')
        return self.data[p:end].decode('utf-8')


@dataclass
class Bone:
    name: str
    parent: int
    translation: tuple
    rotation: tuple
    scale: tuple
    inverse_bind: tuple


@dataclass
class Mesh:
    name: str
    material: int
    positions: list = field(default_factory=list)
    normals: list = field(default_factory=list)
    packed_normals: list = field(default_factory=list)
    tangents: list = field(default_factory=list)
    uvs: list = field(default_factory=list)
    weights: list = field(default_factory=list)
    indices: list = field(default_factory=list)
    colors: list = field(default_factory=list)
    uv_indices: list = field(default_factory=list)


@dataclass
class Model:
    guid: str
    name: str
    source: str
    family: str
    families: list
    materials: list
    bones: list
    lods: dict
    thresholds: list
    rig_guids: list
    warnings: list
    material_family_resolved: bool = True
    lod_levels: list = field(default_factory=list)  # Includes undecoded LODs
    partial: bool = False                            # First-LOD preview only


def unpack_normal(value):
    major = (value >> 29) & 3
    if major == 3: raise ValueError('invalid packed normal major axis')
    n = [0.0, 0.0, 0.0]
    n[major] = -255.0 if value & (1 << 28) else 255.0
    n[(0x124 >> (2 * major + 2)) & 3] = ((value >> 19) & 511) - 256
    n[(0x124 >> (2 * major + 4)) & 3] = ((value >> 10) & 511) - 256
    size = math.sqrt(sum(x*x for x in n))
    return tuple(x / size for x in n)


def unpack_tangent(value, normal):
    x,y,z = normal
    if z < -0.999899983:
        a,b = (0,-1,0),(-1,0,0)
    else:
        v = -1/(1+z)
        a,b = (1+v*x*x,v*x*y,-x),(v*x*y,1+v*y*y,-y)
    angle = (value & 1023) * 0.00614192151
    t = [a[i]*math.cos(angle)+b[i]*math.sin(angle) for i in range(3)]
    length = math.sqrt(sum(x*x for x in t))
    return tuple(x/length for x in t) + (-1.0 if value & 0x80000000 else 1.0,)


def uv_channel_indices(flags):
    channels = []
    for index in range(10):
        encoding = (flags >> (24 + index * 4)) & 15
        if not encoding: continue
        if encoding != 2: raise ValueError(f'UV {index} encoding {encoding} is not supported')
        channels.append(index)
    return channels


def simple_bone_influences(w0, w1, packed_bones):
    extra_count = packed_bones >> 24
    if extra_count > 2: raise ValueError('invalid packed bone weight count')
    stored = [w0, w1][:extra_count]
    weights = stored + [32767 - sum(stored)]
    return [((packed_bones >> (i * 8)) & 255, weight) for i, weight in enumerate(weights)]


def decode_vertices_reference(mesh, g, base, vc, stride, vf, flags, states, extra_base, es):
    """Reference per-vertex decoder."""
    for v in range(vc):
        p = base + v * stride
        start = p
        fmt = vf & 3
        if fmt == 1: position = g.unpack('<3f', p); p += 12
        elif fmt == 2:
            packed = g.unpack('<Q', p)[0]; p += 8
            position = ((packed & 0x1fffff)/1024-1024,
                        ((packed >> 21) & 0x1fffff)/1024-1024,
                        ((packed >> 42) & 0x3fffff)/1024-2048)
        else: raise ValueError(f'vertex position encoding {fmt} unsupported')
        influences = []
        weight_format = (vf >> 12) & 7
        if weight_format != 5: raise ValueError(f'vertex weight encoding {weight_format} unsupported')
        w0, w1, packed_bones = g.unpack('<HHI', p); p += 8
        if flags & 0x4000:
            first, last = packed_bones & 1023, (packed_bones >> 10) & 1023
            n = packed_bones >> 24
            if n > 15: raise ValueError('too many extended bone weights')
            source = [(first, w0)]
            remaining = 32767 - w0
            for middle in range(n - 1):
                idx = w1 + middle
                if idx * 4 + 4 > es: raise ValueError('extra weight index outside mesh')
                weight, bone = g.unpack('<HH', extra_base + idx * 4)
                source.append((bone, weight)); remaining -= weight
            if n: source.append((last, remaining))
        else:
            source = simple_bone_influences(w0, w1, packed_bones)
        for bone, weight in source:
            if weight < 0 or weight > 32767: raise ValueError('invalid bone influence')
            if not weight: continue
            if bone >= len(states): raise ValueError('invalid bone influence')
            influences.append((states[bone], weight / 32767))
        if abs(sum(w for _, w in influences)-1) > .001: raise ValueError('weights do not sum to one')
        if (vf >> 8) & 15 != 10: raise ValueError('normal encoding unsupported')
        packed = g.unpack('<I', p)[0]; p += 4
        mesh.packed_normals.append(packed)
        mesh.normals.append(unpack_normal(packed))
        mesh.tangents.append(unpack_tangent(packed,mesh.normals[-1]))
        if vf & 0x10:
            mesh.colors.append(g.unpack('<4B', p)); p += 4
        uv_sets = []
        for n in mesh.uv_indices:
            uv_sets.append(g.unpack('<2f', p)); p += 8
        if p - start != stride: raise ValueError(f'unhandled vertex fields: read {p-start} of {stride}')
        if not all(math.isfinite(x) for x in (*position, *(x for uv in uv_sets for x in uv))): raise ValueError('non-finite vertex')
        mesh.positions.append(position); mesh.uvs.append(uv_sets); mesh.weights.append(influences)


def unpack_normals(values):
    """Vectorized XYZ float64 normals."""
    v = values.astype(np.int64)
    major = (v >> 29) & 3
    if (major == 3).any(): raise ValueError('invalid packed normal major axis')
    n = np.zeros((len(v), 3))
    rows = np.arange(len(v))
    n[rows, major] = np.where(v & (1 << 28), -255.0, 255.0)
    n[rows, (0x124 >> (2 * major + 2)) & 3] = ((v >> 19) & 511) - 256
    n[rows, (0x124 >> (2 * major + 4)) & 3] = ((v >> 10) & 511) - 256
    return n / np.sqrt((n * n).sum(axis=1))[:, None]


def unpack_tangents(values, normals):
    """Vectorized XYZW float64 tangents."""
    v = values.astype(np.int64)
    x, y, z = normals[:, 0], normals[:, 1], normals[:, 2]
    flip = z < -0.999899983
    with np.errstate(divide='ignore', invalid='ignore'):
        k = np.where(flip, 0.0, -1 / (1 + z))
    a = np.stack((np.where(flip, 0.0, 1 + k * x * x), np.where(flip, -1.0, k * x * y), np.where(flip, 0.0, -x)), axis=1)
    b = np.stack((np.where(flip, -1.0, k * x * y), np.where(flip, 0.0, 1 + k * y * y), np.where(flip, 0.0, -y)), axis=1)
    angle = (v & 1023) * 0.00614192151
    t = a * np.cos(angle)[:, None] + b * np.sin(angle)[:, None]
    t = t / np.sqrt((t * t).sum(axis=1))[:, None]
    w = np.where(v & 0x80000000, -1.0, 1.0)
    return np.column_stack((t, w))


def decode_vertices(mesh, g, base, vc, stride, vf, flags, states, extra_base, es):
    """Vectorized native vertex decoding."""
    if vc == 0:  # Empty meshes lack vertex format
        mesh.positions, mesh.packed_normals, mesh.normals, mesh.tangents, mesh.uvs, mesh.weights = [], [], [], [], [], []
        return
    if base < 0 or base + vc * stride > len(g.data): raise ValueError('model read outside buffer')
    raw = np.frombuffer(g.data, dtype=np.uint8, count=vc * stride, offset=base).reshape(vc, stride)
    def field(start, size, dtype):
        return np.ascontiguousarray(raw[:, start:start + size]).view(dtype)
    p = 0; fmt = vf & 3
    if fmt == 1:
        positions = field(0, 12, '<f4').reshape(vc, 3).astype(np.float64); p = 12
    elif fmt == 2:
        packed = field(0, 8, '<u8').ravel()
        positions = np.column_stack(((packed & 0x1fffff) / 1024 - 1024, ((packed >> 21) & 0x1fffff) / 1024 - 1024,
                                     ((packed >> 42) & 0x3fffff) / 1024 - 2048)); p = 8
    else: raise ValueError(f'vertex position encoding {fmt} unsupported')
    if (vf >> 12) & 7 != 5: raise ValueError(f'vertex weight encoding {(vf >> 12) & 7} unsupported')
    w0 = field(p, 2, '<u2').ravel().astype(np.int64); w1 = field(p + 2, 2, '<u2').ravel().astype(np.int64)
    packed_bones = field(p + 4, 4, '<u4').ravel().astype(np.int64); p += 8
    state_count = len(states)
    if flags & 0x4000:
        extra_count = max(0, min(es // 4, (len(g.data) - extra_base) // 4))
        extras = np.frombuffer(g.data, dtype='<u2', count=extra_count * 2, offset=extra_base).reshape(-1, 2).tolist() if extra_count else []
        weights = []
        for a, b, pb in zip(w0.tolist(), w1.tolist(), packed_bones.tolist()):
            first, last, n = pb & 1023, (pb >> 10) & 1023, pb >> 24
            if n > 15: raise ValueError('too many extended bone weights')
            source = [(first, a)]; remaining = 32767 - a
            for middle in range(n - 1):
                idx = b + middle
                if idx >= extra_count: raise ValueError('extra weight index outside mesh')
                weight, bone = extras[idx]
                source.append((bone, weight)); remaining -= weight
            if n: source.append((last, remaining))
            influences = []
            for bone, weight in source:
                if weight < 0 or weight > 32767: raise ValueError('invalid bone influence')
                if not weight: continue
                if bone >= state_count: raise ValueError('invalid bone influence')
                influences.append((states[bone], weight / 32767))
            if abs(sum(w for _, w in influences) - 1) > .001: raise ValueError('weights do not sum to one')
            weights.append(influences)
    else:
        count = packed_bones >> 24
        if (count > 2).any(): raise ValueError('invalid packed bone weight count')
        wa = np.where(count >= 1, w0, 0); wb = np.where(count >= 2, w1, 0)
        last = 32767 - wa - wb
        if (last < 0).any(): raise ValueError('invalid bone influence')
        bones = np.stack((packed_bones & 255, (packed_bones >> 8) & 255, (packed_bones >> 16) & 255), axis=1)
        values = np.stack((wa, wb, last), axis=1)
        slot = np.arange(3)[None, :]
        # Remainder follows stored weights
        values = np.where(slot < count[:, None], values, 0)
        values[np.arange(vc), count] = last
        used = (slot <= count[:, None]) & (values > 0)
        if (bones[used] >= state_count).any(): raise ValueError('invalid bone influence')
        # 32767 total weight
        mapped = np.asarray(states, dtype=np.int64)[np.minimum(bones, max(state_count - 1, 0))]
        scaled = values / 32767
        weights = [[(b, w) for b, w, keep in zip(rb, rw, ru) if keep]
                   for rb, rw, ru in zip(mapped.tolist(), scaled.tolist(), used.tolist())]
    if (vf >> 8) & 15 != 10: raise ValueError('normal encoding unsupported')
    packed_normals = field(p, 4, '<u4').ravel(); p += 4
    normals = unpack_normals(packed_normals)
    tangents = unpack_tangents(packed_normals, normals)
    colors = None
    if vf & 0x10:
        colors = raw[:, p:p + 4]; p += 4
    uv_sets = []
    for _ in mesh.uv_indices:
        uv_sets.append(field(p, 8, '<f4').reshape(vc, 2).astype(np.float64)); p += 8
    if p != stride: raise ValueError(f'unhandled vertex fields: read {p} of {stride}')
    if not np.isfinite(positions).all() or any(not np.isfinite(uv).all() for uv in uv_sets): raise ValueError('non-finite vertex')
    mesh.positions = list(map(tuple, positions.tolist()))
    mesh.packed_normals = packed_normals.tolist()
    mesh.normals = list(map(tuple, normals.tolist()))
    mesh.tangents = list(map(tuple, tangents.tolist()))
    if colors is not None: mesh.colors = list(map(tuple, colors.tolist()))
    if uv_sets:
        columns = [list(map(tuple, uv.tolist())) for uv in uv_sets]
        mesh.uvs = list(map(list, zip(*columns)))
    else:
        mesh.uvs = [[] for _ in range(vc)]
    mesh.weights = weights


def decode_skeleton(b):
    count, hdr_off, data_off = b.unpack('<3H', 0x74)
    linear = fix(b.u16(0xda))
    fields = b.unpack('<9H', linear)
    if count != fields[0] or count > 4096: raise ValueError('inconsistent model bone counts')
    bones = []; rotations = []
    for i in range(count):
        bh = fix(hdr_off) + i * 12
        bone_name = b.string(bh + fix(b.u16(bh + 10)))
        parent = b.unpack('<h', fix(data_off) + i * 16)[0]
        if parent < -1 or parent >= i: raise ValueError('invalid/cyclic bone hierarchy')
        pos = b.unpack('<3f', linear + fix(fields[3]) + i * 12)
        quat = b.unpack('<4f', linear + fix(fields[4]) + i * 16)
        scale = b.unpack('<3f', linear + fix(fields[8]) + i * 12)
        pose = b.unpack('<12f', linear + fix(fields[6]) + i * 48)
        if not all(math.isfinite(x) for x in (*pos, *quat, *scale, *pose)):
            raise ValueError('non-finite skeleton transform')
        if abs(sum(x*x for x in quat) - 1) > .01: raise ValueError('invalid bone quaternion')
        rotations.append(b.unpack('<3f',linear + fix(fields[5]) + i * 12))
        bones.append(Bone(bone_name, parent, pos, quat, scale, pose))
    return bones, rotations


def decode_model(archive, asset, family=None, stop=None, allow_unresolved_family=False, first_lod_only=False):
    if asset.type_name != 'mdl_' or asset.version != 20:
        raise ValueError(f'model version {asset.version} is not supported by the v20 decoder')
    reader = PageReader(archive)
    header = reader.header(asset)
    studio = reader.pointer(header, 0xe4)
    # Bound reads to owning page
    page_index = struct.unpack_from('<i', archive.data, header)[0]
    end = reader.offsets[page_index] + archive.pages[page_index].size
    b = Buffer(archive.data[studio:end])
    flags = b.unpack('<I', 0)[0]
    name = reader.string(reader.pointer(header + 8))
    bones, _ = decode_skeleton(b)
    material_count, material_off, refs, family_count, skin_off = b.unpack('<5H', 0x90)
    if refs > material_count or family_count > 1024: raise ValueError('invalid skin table dimensions')
    guids = b.unpack(f'<{material_count}Q', fix(material_off))
    skin_table = b.unpack(f'<{refs*family_count}h', fix(skin_off))
    family_names = ['default']
    names_start = fix(skin_off) + refs * family_count * 2
    for i in range(1, family_count):
        family_names.append(b.string(fix(b.u16(names_start + (i - 1) * 2))))
    chosen = 'default' if not family else family
    family_resolved = chosen in family_names
    if not family_resolved and not allow_unresolved_family:
        raise ValueError(f'material family {chosen!r} absent; available: {family_names}')
    remap = skin_table[family_names.index(chosen)*refs:(family_names.index(chosen)+1)*refs] if family_resolved else []
    if any(x < 0 or x >= material_count for x in remap): raise ValueError('invalid skin material index')
    materials = [f'{guids[x]:016X}' for x in remap]
    mesh_materials = {}
    part_count, part_off = b.unpack('<2H', 0x9a)
    for i in range(part_count):
        part = fix(part_off) + i * 16
        model_off = b.u16(part + 2)
        models = b.unpack('<i', part + 8)[0]
        if models < 0 or models > 1024: raise ValueError('invalid bodypart model count')
        for j in range(models):
            model = part + fix(model_off) + j * 10
            mesh_count, base_count, blend_count, mesh_off = b.unpack('<4H', model + 2)
            for k in range(base_count):
                material, mesh_id = b.unpack('<2H', model + fix(mesh_off) + k * 20)
                if material >= refs: raise ValueError('mesh material outside skin table')
                if mesh_id in mesh_materials and mesh_materials[mesh_id] != material:
                    raise ValueError('ambiguous mesh/bodygroup mapping')
                mesh_materials[mesh_id] = material
    state_off, state_count = b.unpack('<2H', 0xb0)
    states = b.unpack(f'<{state_count}H', 0xb0 + fix(state_off))
    if any(x >= len(bones) for x in states): raise ValueError('invalid bone state remap')
    grp_off, grp_count, threshold_off, lod_count = b.unpack('<4H', 0xc4)
    if grp_count > 8 or lod_count > 8: raise ValueError('invalid LOD group count')
    thresholds = list(b.unpack(f'<{lod_count}f', 0xc8 + fix(threshold_off)))
    streamed = StreamingReader(archive).read(asset)
    lods = {}
    warnings = []
    if not family_resolved: warnings.append(f'Material set unavailable: {chosen}. Export disabled.')
    runtime = OodleRuntime(archive.game_root)
    groups = [b.unpack('<iii4B', 0xc4 + fix(grp_off) + i * 16) for i in range(grp_count)]
    lod_levels = sorted({li + k for (_o, _c, _r, _comp, li, lc, _lm) in groups for k in range(lc)})
    wanted = range(grp_count)
    if first_lod_only and groups:  # Other LODs decode on demand
        wanted = [min(range(grp_count), key=lambda i: groups[i][4])]
    for i in wanted:
        if stop and stop.is_set():
            from .oodle_stream import ScanCancelled
            raise ScanCancelled()
        off, cmp_size, raw_size, comp, li, lc, lm = groups[i]
        if min(off, cmp_size, raw_size) < 0 or off + cmp_size > len(streamed): raise ValueError('invalid VG extent')
        payload = streamed[off:off+cmp_size]
        if comp == 3: payload = decompress_stream(payload, raw_size, runtime, stop)
        elif comp == 0:
            if raw_size > cmp_size: raise ValueError('uncompressed VG size mismatch')
            payload = payload[:raw_size]
        else: raise ValueError(f'VG compression {comp} is unsupported')
        g = Buffer(payload)
        vli, vlc, group, vlm, lod_off = g.unpack('<4BI', 0)
        if (vli, vlc, vlm) != (li, lc, lm): raise ValueError('VG group header disagrees with studio')
        for j in range(vlc):
            lp = 4 + lod_off + j * 8
            mc, mi, level, gi, mo = g.unpack('<4BI', lp)
            if level in lods: raise ValueError('duplicate decoded LOD')
            meshes = []
            for k in range(mc):
                mesh_id = mi + k
                if mesh_id not in mesh_materials: raise ValueError(f'VG mesh {mesh_id} has no studio material')
                mp = lp + 4 + mo + k * 48
                values = g.unpack('<QIHH8I', mp)
                vf, vc, stride, bone_count, io, ic, vo, vs, eo, es, bo, bs = values
                if vc > 10_000_000 or vc * stride != vs: raise ValueError('vertex buffer/stride mismatch')
                if ic >> 28 != 1 or (ic & 0xfffffff) % 3: raise ValueError('non-triangle VG index layout unsupported')
                index_count = ic & 0xfffffff
                if mp + 16 + io < 0 or mp + 16 + io + index_count * 2 > len(g.data): raise ValueError('model read outside buffer')
                index_array = np.frombuffer(g.data, dtype='<u2', count=index_count, offset=mp + 16 + io)
                if index_count and int(index_array.max()) >= vc: raise ValueError('triangle index outside mesh')
                indices = index_array.tolist()
                mesh = Mesh(f'mesh_{mesh_id}', mesh_materials[mesh_id], indices=indices)
                mesh.uv_indices = uv_channel_indices(vf)
                args = (g, mp + 24 + vo, vc, stride, vf, flags, states, mp + 32 + eo, es)
                try:
                    decode_vertices(mesh, *args)
                except Exception as fast_error:
                    # Mismatch uses reference decoder
                    mesh.positions, mesh.packed_normals, mesh.normals, mesh.tangents, mesh.colors, mesh.uvs, mesh.weights = [], [], [], [], [], [], []
                    decode_vertices_reference(mesh, *args)
                    warnings.append(f'{mesh.name} (LOD {level}) used the slow vertex decoder: {fast_error}')
                meshes.append(mesh)
            lods[level] = meshes
    if not any(mesh.positions and mesh.indices for meshes in lods.values() for mesh in meshes):
        raise ValueError('Model has no mesh data')
    rig_count = struct.unpack_from('<I', archive.data, header + 40)[0]
    if rig_count > 4096: raise ValueError('invalid rig count')
    rigs = []
    if rig_count:
        rp = reader.pointer(header + 32, rig_count * 8)
        rigs = [f'{x:016X}' for x in struct.unpack_from(f'<{rig_count}Q', archive.data, rp)]
    partial = len(wanted) < grp_count
    return Model(f'{asset.guid:016X}', name, str(archive.path), chosen, family_names, materials, bones, lods, thresholds, rigs, warnings,
                 family_resolved, lod_levels=lod_levels or sorted(lods), partial=partial)
