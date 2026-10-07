"""Declared animation links."""
import struct
from .pages import PageReader


def decode_animation_header(reader,asset):
    p = reader.header(asset); data = reader.data
    name = reader.string(reader.pointer(p+8))
    details = {'track_status':'not_decoded'}
    if asset.type_name == 'arig' and asset.header_struct_size == 40 and asset.version in (4,5,6,7):
        count = struct.unpack_from('<i' if asset.version == 4 else '<h',data,p+(20 if asset.version==4 else 18))[0]
        pointer = p+24; key = 'declared_sequences'
    elif asset.type_name == 'aseq' and asset.header_struct_size == 64 and 8 <= asset.version <= 14:
        count = struct.unpack_from('<H',data,p+24)[0]
        pointer = p+32; key = 'declared_models'
    else: raise ValueError(f'animation header {asset.type_name}/{asset.version}/{asset.header_struct_size} unsupported')
    if count < 0 or count > 65536: raise ValueError('invalid declared animation association count')
    ptr = reader.pointer(pointer,count*8,nullable=True)
    if ptr is None and count: raise ValueError('null animation association array')
    details[key] = [f'{x:016X}' for x in struct.unpack_from(f'<{count}Q',data,ptr)] if count else []
    return name,details
