"""Native v10 texture extraction."""
import hashlib
import json
import struct
from pathlib import Path
from .pages import PageReader
from .streaming import StreamingReader
from .rtech import OodleRuntime, decompress_rtech_payload
from .oodle_stream import decompress_stream

DXGI = [71,72,74,75,77,78,80,81,83,84,95,96,98,99]
EXPORT_PNG_LEVEL = 4


FORMAT_NAMES = {0: 'BC1', 1: 'BC1 sRGB', 2: 'BC2', 3: 'BC2 sRGB', 4: 'BC3', 5: 'BC3 sRGB', 6: 'BC4', 7: 'BC4 signed',
                8: 'BC5', 9: 'BC5 signed', 10: 'BC6H', 11: 'BC6H signed', 12: 'BC7', 13: 'BC7 sRGB', 31: 'RGBA8', 32: 'RGBA8 sRGB'}


def texture_info(archive, asset):
    """Header metadata without pixel decoding."""
    if asset.type_name != 'txtr' or asset.version != 10:
        raise ValueError(f'texture version {asset.version} unsupported')
    start = PageReader(archive).header(asset)
    header = archive.data[start:start + 56]
    fmt, width, height, _depth = struct.unpack_from('<4H', header, 8)
    perm, stream, opt = header[24:27]
    return {'width': width, 'height': height, 'format': FORMAT_NAMES.get(fmt, f'format {fmt}'),
            'srgb': fmt in (1, 3, 5, 13, 32), 'mips': perm + stream + opt, 'streamed_mips': stream + opt}


def extract_texture(archive, asset, directory, stem, preview_size=None):
    from PIL import Image
    import texture2ddecoder as dec
    if asset.type_name != 'txtr' or asset.version != 10:
        raise ValueError(f'texture version {asset.version} unsupported')
    r = PageReader(archive); p = r.header(asset)
    header = archive.data[p:p+56]
    fmt,width,height,depth = struct.unpack_from('<4H',header,8)
    array,layers = header[16:18]
    perm,stream,opt = header[24:27]; unk,kind = header[28:30]
    packed = struct.unpack_from('<H',header,30)[0]
    cmp_sizes = struct.unpack_from('<7H',header,32)
    if (array not in (0,1)) or layers & 2 or depth not in (0,1) or unk:
        raise ValueError('texture arrays, cube maps, volumes, or unknown mip class unsupported')
    if fmt < 14:
        block = 8 if fmt in (0,1,6,7) else 16
        pitch = lambda w,h: max(1,(w+3)//4)*max(1,(h+3)//4)*block
        dxgi = DXGI[fmt]
    elif fmt in (31,32):
        pitch = lambda w,h:w*h*4
        dxgi = 28 if fmt == 31 else 29
    else: raise ValueError(f'texture pixel format {fmt} unsupported')
    if not width or not height or max(width,height) > 32768 or perm+stream+opt > 32:
        raise ValueError('invalid texture dimensions/mip count')
    total = perm+stream+opt
    if not total: raise ValueError('texture has no mip payload')
    if stream+opt > 7: raise ValueError('streamed mip count exceeds compression table')
    specifications = []
    offsets = {'rpak':0,'stream':0,'optional':0}
    ci = stream+opt-1
    for i in range(total-1,-1,-1):
        w,h = max(1,width>>i),max(1,height>>i)
        raw_size = pitch(w,h)
        group = 'optional' if i < opt else 'stream' if i < opt+stream else 'rpak'
        comp = 0 if group == 'rpak' else (packed>>(2*ci)) & 3
        stored = ((cmp_sizes[ci]+1)<<12) if comp else (raw_size+15)&~15
        if group != 'rpak': ci -= 1
        specifications.append({'level':i,'width':w,'height':h,'raw_size':raw_size,'stored_size':stored,
                               'storage':group,'compression':comp,'offset':offsets[group]})
        offsets[group] += stored
    raw = {}
    level=next((i for i in range(total) if max(width>>i,height>>i)<=preview_size),total-1) if preview_size else 0
    selected=next(s for s in specifications if s['level']==level)
    cpu = r.resolve(asset.data,offsets['rpak']) if offsets['rpak'] else 0
    if not preview_size or selected['storage']=='rpak': raw['rpak'] = archive.data[cpu:cpu+offsets['rpak']]
    sr = StreamingReader(archive)
    for group in ('stream','optional'):
        if offsets[group] and (not preview_size or selected['storage']==group): raw[group] = sr.read(asset, group == 'optional')
    mips = {}
    for spec in specifications:
        if preview_size and spec['level']!=level: continue
        group = spec['storage']; off = spec['offset']; size = spec['stored_size']
        if group != 'rpak': off = offsets[group]-off-size
        spec['offset'] = off
        blob = raw[group][off:off+size]
        if len(blob) != size: raise ValueError('texture mip outside registered payload')
        comp = spec['compression']; expected = spec['raw_size']
        if comp == 3: blob = decompress_stream(blob, expected, OodleRuntime(archive.game_root))
        elif comp == 1: blob = decompress_rtech_payload(blob,0,len(blob),expected)
        elif comp == 2: raise ValueError('Snowflake mip decompression unavailable')
        else: blob = blob[:expected]
        if len(blob) != expected: raise ValueError('texture mip decoded size mismatch')
        mips[spec['level']] = blob
    directory = Path(directory); directory.mkdir(parents=True,exist_ok=True)
    # DDS wraps unchanged mip bytes
    flags = 0x1|0x2|0x4|0x1000|(0x8 if fmt in (31,32) else 0x80000)
    if total > 1: flags |= 0x20000
    caps = 0x1000 | (0x400008 if total > 1 else 0)
    top_pitch = width*4 if fmt in (31,32) else pitch(width,height)
    ddsheader = struct.pack('<7I11I8I5I',124,flags,height,width,top_pitch,0,total,*([0]*11),
                            32,4,0x30315844,0,0,0,0,0,caps,0,0,0,0)
    dds = directory/f'{stem}.dds'
    if not preview_size: dds.write_bytes(b'DDS '+ddsheader+struct.pack('<5I',dxgi,3,0,1,0)+b''.join(mips[i] for i in range(total)))
    width,height=selected['width'],selected['height']
    png = directory/f'{stem}.png'
    if fmt in (31,32): image = Image.frombytes('RGBA',(width,height),mips[level])
    elif fmt in (2,3,7,9,10,11):
        # Preserve unsupported formats as DDS
        image = None
    else:
        function = {0:dec.decode_bc1,1:dec.decode_bc1,
                    4:dec.decode_bc3,5:dec.decode_bc3,6:dec.decode_bc4,8:dec.decode_bc5,
                    12:dec.decode_bc7,13:dec.decode_bc7}[fmt]
        image = Image.frombytes('RGBA',(width,height),function(mips[level],width,height),'raw','BGRA')
    # Preview encoding prioritizes speed
    if image: image.save(png, compress_level=1 if preview_size else EXPORT_PNG_LEVEL)
    if not preview_size:
        source_dir = directory/'original'; source_dir.mkdir(exist_ok=True)
        (source_dir/f'{stem}.header.bin').write_bytes(header)
        for group, blob in raw.items(): (source_dir/f'{stem}.{group}.bin').write_bytes(blob)
    info = {'guid':f'{asset.guid:016X}','source_rpak':str(archive.path),'asset_version':asset.version,
            'width':width,'height':height,'format':fmt,'dxgi_format':dxgi,'srgb':fmt in (1,3,5,13,32),
            'texture_type':kind,'mips':sorted(specifications,key=lambda x:x['level']),
            'dds':dds.name if not preview_size else None,'png':png.name if image else None,
            'preview_mip':level if preview_size else None,'source_files':[str(p) for p in sr.indices],
            'source_fingerprints':[(str(p),p.stat().st_size,p.stat().st_mtime_ns) for p in sr.indices],
            'conversion':'Lossless 8-bit channel decode; channel meaning is unresolved until shader analysis.',
            'payload_sha256':{k:hashlib.sha256(v).hexdigest() for k,v in raw.items()}}
    if getattr(archive,'pages_reconstructed',False): info['patch_provenance'] = archive.patch_provenance
    (directory/f'{stem}.texture.json').write_text(json.dumps(info,indent=2),encoding='utf-8')
    return info
