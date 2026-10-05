import bisect
import math
import struct
from pathlib import Path
import numpy as np
from .model import Buffer, decode_skeleton, fix
from .pages import PageReader
from .streaming import StreamingReader


def quaternion_product(a,b):
    x,y,z,w=a; X,Y,Z,W=b
    return np.array((w*X+x*W+y*Z-z*Y,w*Y-x*Z+y*W+z*X,w*Z+x*Y-y*X+z*W,w*W-x*X-y*Y-z*Z))


def euler_quaternion(angles):
    x,y,z=(v/2 for v in angles)
    sx,cx=math.sin(x),math.cos(x); sy,cy=math.sin(y),math.cos(y); sz,cz=math.sin(z),math.cos(z)
    return (sx*cy*cz-cx*sy*sz,cx*sy*cz+sx*cy*sz,cx*cy*sz-sx*sy*cz,cx*cy*cz+sx*sy*sz)


def curve_value(buffer,offset,frame,scale):
    seek=((1,15,16),(2,7,8),(2,15,0),(3,15,0),(4,15,0),(5,15,0),(6,15,0),(7,15,0),
          (2,15,2),(3,15,2),(4,15,2),(5,15,2),(6,15,2),(7,15,2),
          (2,15,4),(3,15,4),(4,15,4),(5,15,4),(6,15,4),(7,15,4))
    while True:
        valid,total=buffer.unpack('<2B',offset)
        if not total or valid>=len(seek): raise ValueError('Invalid animation curve block')
        if frame<total: break
        frame-=total
        a,b,c=seek[valid]; offset+=2*(a+((b+total*c)>>4))
    if valid==0: value=buffer.unpack('<h',offset+2+frame*2)[0]
    elif valid==1:
        value=buffer.unpack('<h',offset+2)[0]
        if frame: value+=buffer.unpack('<b',offset+3+frame)[0]
    else:
        bits=(0,2,4)[(valid-2)//6]; coefficients=(valid-2)%6
        values=buffer.unpack(f'<{coefficients+1}h',offset+2)
        cycle=frame/(total-1) if total>1 else 0.
        value=sum(v*cycle**i for i,v in enumerate(values))
        if bits:
            packed=buffer.unpack('<H',offset+4+coefficients*2+(frame*bits//16)*2)[0]
            value-=(1<<bits)-1; value+=2*((packed>>(frame*bits%16))&((1<<bits)-1))
    return value*scale


def axis_values(buffer,offset,frame,scale,base):
    packed,axis1,axis2=buffer.unpack('<H2B',offset)
    flags=packed>>13; pointer=offset+(packed&8191)
    shifts=(0,axis1*2,axis2*2)
    return [curve_value(buffer,pointer+shifts[i],frame,scale) if flags&(4>>i) else base[i] for i in range(3)]


def decode_animation(repository,model,guid,rig_guid,blend=0):
    archive,asset=repository.asset(guid)
    if asset.type_name!='aseq' or asset.version not in (13,14):
        raise ValueError(f'Animation version {asset.version} is not supported')
    reader=PageReader(archive); header=reader.header(asset); sequence=reader.pointer(header)
    page=bisect.bisect_right(reader.offsets,sequence)-1
    buffer=Buffer(archive.data[sequence:reader.offsets[page]+archive.pages[page].size])
    blends=buffer.unpack('<H',40)[0]
    if not 0<=blend<blends: raise ValueError('Animation blend index is outside sequence')
    table=fix(buffer.u16(42)); offset=fix(buffer.u16(table+blend*2))
    fps,flags,frames=buffer.unpack('<fII',offset)
    if not 0<fps<=240 or not 0<frames<=18000: raise ValueError('Invalid animation duration')
    if flags&0x200000: raise ValueError('Datapoint animation compression is not supported')
    if not flags&0x20000: raise ValueError('Sequence has no animation track data')
    data_guid=f'{buffer.unpack("<Q",offset+24)[0]:016X}'
    data_archive,data_asset=repository.asset(data_guid)
    if data_asset.type_name!='asqd': raise ValueError('Animation track GUID is not sequence data')
    dr=PageReader(data_archive); data_start=dr.pointer(dr.header(data_asset))
    dp=bisect.bisect_right(dr.offsets,data_start)-1
    data=Buffer(data_archive.data[data_start:dr.offsets[dp]+data_archive.pages[dp].size])
    ra,rig=repository.asset(rig_guid)
    if rig.type_name!='arig' or rig.version!=7: raise ValueError('Animation rig layout is not supported')
    rr=PageReader(ra); rs=rr.pointer(rr.header(rig)); rp=bisect.bisect_right(rr.offsets,rs)-1
    bones,angles=decode_skeleton(Buffer(ra.data[rs:rr.offsets[rp]+ra.pages[rp].size]))
    target={b.name:i for i,b in enumerate(model.bones)}
    matched={i:target[b.name] for i,b in enumerate(bones) if b.name in target}
    if not matched: raise ValueError('Animation rig has no matching model bones')
    for source,index in matched.items():
        parent=bones[source].parent; target_parent=model.bones[index].parent
        if parent>=0 and (target_parent<0 or bones[parent].name!=model.bones[target_parent].name):
            raise ValueError('Animation bone hierarchy does not match model: '+bones[source].name)
    positions=np.tile([b.translation for b in model.bones],(frames,1,1))
    rotations=np.tile([b.rotation for b in model.bones],(frames,1,1))
    scales=np.tile([b.scale for b in model.bones],(frames,1,1))
    section_offset,stall,section_frames=buffer.unpack('<3H',offset+42)
    external=None
    if section_frames:
        extra_size=struct.unpack_from('<I',archive.data,header+28)[0]
        if extra_size:
            if asset.starpak_offset!=-1: external=Buffer(StreamingReader(archive).read(asset))
            else:
                extra=reader.pointer(header+56,extra_size)
                external=Buffer(bytes(archive.data[extra:extra+extra_size]))
    section_count=(frames-stall-1)//section_frames+1+(stall>0) if section_frames else 0
    sections=buffer.unpack(f'<{section_count}i',offset+fix(section_offset)) if section_frames else []
    for frame in range(frames):
        local=frame; current=data; start=0
        if section_frames and frame>=stall:
            section=(frame-stall)//section_frames; local=(frame-stall)%section_frames
            value=sections[section]
            if value<0:
                if external is None: raise ValueError('Animation streaming section is missing')
                current=external; start=~value
            else: start=value
        count=len(bones); flag_bytes=((count*6+7)//8+1)&~1
        packed_flags=int.from_bytes(current.data[start:start+flag_bytes],'little')
        record=start+flag_bytes
        for source,bone in enumerate(bones):
            bone_flags=(packed_flags>>(source*6))&63
            if bone_flags&0x38: raise ValueError(f'Animation bone flags {bone_flags:#x} are not supported')
            delta=bool(flags&4)
            pos=(0,0,0) if delta else bone.translation
            rot=(0,0,0,1) if delta else bone.rotation
            scale=(1,1,1) if delta else bone.scale
            if bone_flags:
                packed=current.u16(record); size=packed&8191; varying=packed>>13; p=record+2
                if size<2: raise ValueError('Invalid animation bone record size')
                if bone_flags&1:
                    if varying&4:
                        factor=current.unpack('<f',p)[0]
                        values=axis_values(current,p+4,local,factor,(0,0,0))
                        pos=tuple(a+b for a,b in zip(pos,values)); p+=8
                    else: pos=current.unpack('<3e',p); p+=6
                if bone_flags&2:
                    if varying&2:
                        rot=euler_quaternion(axis_values(current,p,local,.00019175345,(0,0,0) if delta else angles[source])); p+=4
                    else:
                        q=current.unpack('<Q',p)[0]; p+=8
                        xyz=[(((q>>(21*i))&2097151)-1048576)/1048576.5 for i in range(3)]
                        remainder=1-sum(v*v for v in xyz)
                        if remainder<-.00001: raise ValueError('Invalid animation quaternion')
                        rot=(*xyz,math.sqrt(max(remainder,0))*(-1 if q>>63 else 1))
                if bone_flags&4:
                    if varying&1:
                        values=axis_values(current,p,local,.0030518509,(0,0,0))
                        scale=tuple(a+b for a,b in zip(scale,values)); p+=4
                    else: scale=current.unpack('<3e',p); p+=6
                if p>record+size: raise ValueError('Animation fields exceed bone record')
                record+=size
            if source not in matched: continue
            index=matched[source]; dest=model.bones[index]
            if delta:
                positions[frame,index]=np.asarray(dest.translation)+pos
                rotations[frame,index]=quaternion_product(dest.rotation,rot)
                scales[frame,index]=np.asarray(dest.scale)*scale
            else:
                inverse=np.asarray(bone.rotation)*(-1,-1,-1,1)
                correction=quaternion_product(dest.rotation,inverse)
                if bone_flags&1:
                    positions[frame,index]=quaternion_product(quaternion_product(correction,(*pos,0)),correction*(-1,-1,-1,1))[:3]
                rotations[frame,index]=quaternion_product(correction,rot)
                scales[frame,index]=np.asarray(dest.scale)*np.asarray(scale)/bone.scale
        movement=buffer.u16(offset+14)
        if flags&0x40000 and movement:
            mp=offset+fix(movement); factors=buffer.unpack('<4f',mp); interval=buffer.unpack('<I',mp+16)[0]
            if not interval: raise ValueError('Invalid root movement section size')
            section=mp+fix(buffer.u16(mp+20+2*(frame//interval)))
            values=[curve_value(buffer,section+buffer.u16(section+i*2),frame%interval,factors[i]) if buffer.u16(section+i*2) else 0. for i in range(4)]
            root_index=matched.get(0)
            if root_index is not None:
                positions[frame,root_index]+=values[:3]
                rotations[frame,root_index]=quaternion_product(rotations[frame,root_index],euler_quaternion((0,0,math.radians(values[3]))))
        if not flags&4 and 0 in matched:
            root_index=matched[0]
            # Animation origins use the authoring basis; convert -90 Z, then Z-up to model Y-up.
            basis=(-.5,-.5,-.5,.5)
            rotations[frame,root_index]=quaternion_product(basis,rotations[frame,root_index])
            positions[frame,root_index]=quaternion_product(quaternion_product(basis,(*positions[frame,root_index],0)),(.5,.5,.5,.5))[:3]
    if not all(np.isfinite(a).all() for a in (positions,rotations,scales)): raise ValueError('Non-finite animation transforms')
    lengths=np.linalg.norm(rotations,axis=2)
    if np.any(abs(lengths-1)>.01): raise ValueError('Animation quaternion length is invalid')
    rotations/=lengths[:,:,None]
    source_name=buffer.string(offset+fix(buffer.u16(offset+12))).lstrip('@')
    sequence_name=buffer.string(fix(buffer.u16(0))) if buffer.u16(0) else source_name
    activity=buffer.string(fix(buffer.u16(2))) if buffer.u16(2) else None
    name=Path(sequence_name).stem.replace('_',' ').strip().title()
    return {'guid':guid,'name':name,'fps':fps,'frames':frames,'loop':bool(flags&1),'blend':blend,'blends':blends,
            'rig_guid':rig_guid,'data_guid':data_guid,'mapped_bones':len(matched),
            'source_name':source_name,'sequence_name':sequence_name,'activity':activity,
            'ik_rules':buffer.u16(offset+16),'autolayers':buffer.u16(78),
            'positions':positions,'rotations':rotations,'scales':scales}
