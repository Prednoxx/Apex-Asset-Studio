"""Bounded DXBC reflection."""
import struct
import re
import sys
import hashlib
import subprocess
import tempfile
from pathlib import Path
from .model import Buffer
from .pages import PageReader
from .shader_analysis import derivative_normal_contract, sampled_channel_contract, anisotropy_direction_contract


def reflect_dxbc(data):
    b = Buffer(data)
    if data[:4] != b'DXBC': raise ValueError('shader is not a DXBC container')
    size, count = b.unpack('<2I', 24)
    if size > len(data) or count > 128: raise ValueError('invalid DXBC extent')
    result = []
    for off in b.unpack(f'<{count}I', 32):
        tag, size = b.unpack('<4sI', off)
        if off + 8 + size > len(data): raise ValueError('DXBC chunk outside container')
        if tag != b'RDEF': continue
        r = Buffer(data[off+8:off+8+size])
        n, table = r.unpack('<2I', 8)
        if n > 4096: raise ValueError('invalid shader resource count')
        for i in range(n):
            name, kind, ret, dim, samples, slot, slots, flags = r.unpack('<8I', table+i*32)
            result.append({'name':r.string(name),'type':kind,'slot':slot,'count':slots,'dimension':dim,'flags':flags})
    if not result: raise ValueError('shader reflection unavailable')
    return result


def material_bindings(repository, shader_guid):
    cache = getattr(repository,'shader_reflections',None)
    if cache is None: repository.shader_reflections = cache = {}
    if shader_guid in cache: return cache[shader_guid]
    archive, asset = repository.asset(shader_guid)
    r = PageReader(archive); h = r.header(asset)
    if asset.type_name != 'shds': raise ValueError('material shader GUID is not a shader set')
    pixel_offsets = {8:80,11:56,12:72,13:104,14:56,15:72}
    if asset.version not in pixel_offsets: raise ValueError(f'shader set version {asset.version} unsupported')
    pixel_guid = struct.unpack_from('<Q',archive.data,h+pixel_offsets[asset.version])[0]
    sa, sh = repository.asset(f'{pixel_guid:016X}')
    sr = PageReader(sa)
    # Relocated pointer followed by length
    cpu = sr.resolve(sh.data, 12)
    length = struct.unpack_from('<i',sa.data,cpu+8)[0]
    if length <= 0: raise ValueError('first shader bytecode variant unavailable')
    pos = sr.pointer(cpu, length)
    bytecode = bytes(sa.data[pos:pos+length])
    try:
        resources = reflect_dxbc(bytecode); method='native DXBC RDEF'; disassembly=None
    except ValueError:
        resources,disassembly = reflect_dxil(bytecode); method='DXC DXIL resource reflection'
    if disassembly:
        for resource in resources:
            resource['channel_contract']=sampled_channel_contract(disassembly,resource['resource_id'])
            if resource['name'].casefold()=='normaltexture':
                contract=derivative_normal_contract(disassembly,resource['resource_id'])
                if contract: resource['normal_contract']=contract
            if resource['name'].casefold()=='anisospecdirtexture':
                contract=anisotropy_direction_contract(disassembly,resource['resource_id'])
                if contract: resource['anisotropy_contract']=contract
    result = {'shader_set':shader_guid,'pixel_shader':f'{pixel_guid:016X}',
              'resources':resources,'variant':0,'method':method,
              'bytecode_sha256':hashlib.sha256(bytecode).hexdigest(),
              '_bytecode':bytecode,'_disassembly':disassembly}
    cache[shader_guid] = result
    return result


def parse_dxc_resources(text):
    """Reflected bindings and register spaces."""
    section = text.split('; Resource Bindings:',1)
    if len(section)!=2: raise ValueError('DXIL resource reflection unavailable')
    section=section[1].split('; ViewId state:',1)[0]
    result=[]
    pattern=r'^;\s*(\S+)\s+texture\s+(\S+)\s+(\S+)\s+T(\d+)\s+t(\d+)(?:,space(\d+))?\s*(\d+|unbounded)\s*$'
    for match in re.finditer(pattern,section,re.MULTILINE):
        name,fmt,dim,resource,slot,space,count=match.groups()
        result.append({'name':name,'type':2,'slot':int(slot),'space':int(space or 0),
                       'count':int(count) if count!='unbounded' else None,
                       'dimension':dim,'resource_id':int(resource)})
    if not result: raise ValueError('DXIL has no named reflected texture bindings')
    return result


def reflect_dxil(data):
    base=Path(getattr(sys,'_MEIPASS',Path(__file__).resolve().parents[2]))
    executable=base/'third_party'/'dxc'/'dxc.exe'
    if not executable.exists(): raise ValueError('bundled DXIL reflection backend unavailable')
    with tempfile.TemporaryDirectory(prefix='aas-shader-') as tmp:
        path=Path(tmp)/'shader.dxbc';path.write_bytes(data)
        run=subprocess.run([str(executable),'-dumpbin',str(path)],capture_output=True,
                           timeout=30,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
    if run.returncode: raise ValueError('DXIL reflection failed: '+run.stderr.decode('utf-8','replace')[:300])
    text=run.stdout.decode('utf-8','replace').replace('\r\n','\n')
    return parse_dxc_resources(text),text
