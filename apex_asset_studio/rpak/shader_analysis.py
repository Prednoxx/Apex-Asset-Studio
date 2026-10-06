"""Recognize a bounded subset of shader arithmetic; unknown expressions stay unknown."""
import re
import struct
import math


def sampled_channel_contract(text, resource_id):
    instructions={v:e.strip() for v,e in re.findall(r'^\s*(%\d+) = (.+)$',text,re.MULTILINE)}
    handles=[v for v,e in instructions.items() if re.search(r'@dx.op.createHandle\(i32 57, i8 0, i32 '+str(resource_id)+r',',e)]
    samples=[v for v,e in instructions.items() if '@dx.op.sample.f32(' in e and any('%dx.types.Handle '+h+',' in e for h in handles)]
    channels=set();inverse=set()
    for expression in instructions.values():
        if '@dx.op.textureGather.f32(' in expression and any('%dx.types.Handle '+h+',' in expression for h in handles):
            match=re.search(r', i32 ([0-3])\)\s*; TextureGather',expression)
            if match: channels.add('RGBA'[int(match[1])])
    for variable,expression in instructions.items():
        for sample in samples:
            match=re.fullmatch(r'extractvalue %dx.types.ResRet.f32 '+re.escape(sample)+r', ([0-3])',expression)
            if not match: continue
            channel='RGBA'[int(match[1])];channels.add(channel)
            if any(e==f'fsub fast float 1.000000e+00, {variable}' for e in instructions.values()): inverse.add(channel)
    return {'sampled_components':sorted(channels),'one_minus_components':sorted(inverse)}


def anisotropy_direction_contract(text, resource_id):
    instructions={v:e.strip() for v,e in re.findall(r'^\s*(%\d+) = (.+)$',text,re.MULTILINE)}
    handles=[v for v,e in instructions.items() if re.search(r'@dx.op.createHandle\(i32 57, i8 0, i32 '+str(resource_id)+r',',e)]
    gathers={v for v,e in instructions.items() if '@dx.op.textureGather.f32(' in e and ', i32 0)  ; TextureGather' in e
               and any('%dx.types.Handle '+h+',' in e for h in handles)}
    if not gathers: return None
    for angle,expression in instructions.items():
        match=re.fullmatch(r'fmul fast float (%\d+), (0x[0-9A-Fa-f]{16}|\d+\.\d+e[+-]\d+)',expression)
        if not match: continue
        scale=struct.unpack('>d',bytes.fromhex(match[2][2:]))[0] if match[2].startswith('0x') else float(match[2])
        if abs(scale-math.tau)>1e-5: continue
        pending=[match[1]];ancestors=set()
        while pending:
            value=pending.pop()
            if value in ancestors: continue
            ancestors.add(value);pending.extend(re.findall(r'%\d+',instructions.get(value,'')))
        if not ancestors.intersection(gathers): continue
        cosine={v for v,e in instructions.items() if '@dx.op.unary.f32(i32 12, float '+angle+')' in e}
        comparisons={v for v,e in instructions.items() if e==f'fcmp fast ogt float {match[1]}, 5.000000e-01'}
        signs={v for v,e in instructions.items() if any(e==f'select i1 {c}, float 1.000000e+00, float -1.000000e+00' for c in comparisons)}
        squares={v for v,e in instructions.items() if any(e==f'fmul fast float {c}, {c}' for c in cosine)}
        remainders={v for v,e in instructions.items() if any(e==f'fsub fast float 1.000000e+00, {s}' for s in squares)}
        roots={v for v,e in instructions.items() if any('@dx.op.unary.f32(i32 24, float '+r+')' in e for r in remainders)}
        if not any(e in (f'fmul fast float {s}, {r}',f'fmul fast float {r}, {s}')
                   for e in instructions.values() for s in signs for r in roots): continue
        return {'encoding':'wrapped_tangent_angle','channel':'R','angle_scale':scale,'sine_sign':-1,
                'sampling':'circular bilinear','evidence':'R texture gather, wrap correction, turns-to-radians and tangent sine/cosine'}


def convert_anisotropy_direction(source,destination,contract):
    from PIL import Image
    import numpy as np
    lookup=np.array([(round((math.cos(i/255*contract['angle_scale'])*.5+.5)*255),
                      round((contract['sine_sign']*math.sin(i/255*contract['angle_scale'])*.5+.5)*255),128) for i in range(256)],dtype=np.uint8)
    with Image.open(source) as image:
        channel=np.asarray(image.getchannel(contract['channel']))
        Image.fromarray(lookup[channel],'RGB').save(destination)


def derivative_normal_contract(text, resource_id):
    instructions={v:e.strip() for v,e in re.findall(r'^\s*(%\d+) = (.+)$',text,re.MULTILINE)}
    signatures={name:int(index) for index,name in re.findall(r'!\d+ = !\{i32 (\d+), !"(NORMAL|TANGENT|BINORMAL)"',text)}
    if set(signatures)!= {'NORMAL','TANGENT','BINORMAL'}: return None
    inputs={}
    for var,expression in instructions.items():
        m=re.search(r'@dx.op.loadInput.f32\(i32 4, i32 (\d+), i32 0, i8 (\d+),',expression)
        if m: inputs[(int(m[1]),int(m[2]))]=var
    def binary(op,a,b):
        for var,expression in instructions.items():
            if expression in (f'{op} fast float {a}, {b}',f'{op} fast float {b}, {a}'):
                return var
    def affine(var):
        literal=r'(0x[0-9A-Fa-f]{16}|-?\d+\.\d+e[+-]\d+)'
        for product,expr in instructions.items():
            m=re.fullmatch(r'fmul fast float '+re.escape(var)+r', '+literal,expr)
            if not m: continue
            for shifted,expr2 in instructions.items():
                n=re.fullmatch(r'fadd fast float '+re.escape(product)+r', '+literal,expr2)
                if n:
                    def number(value):
                        return struct.unpack('>d',bytes.fromhex(value[2:]))[0] if value.startswith('0x') else float(value)
                    return shifted,number(m[1]),number(n[1])
    handles=[v for v,e in instructions.items() if re.search(r'@dx.op.createHandle\(i32 57, i8 0, i32 '+str(resource_id)+r',',e)]
    for sample,expr in instructions.items():
        if '@dx.op.sample.f32(' not in expr or not any('%dx.types.Handle '+h+',' in expr for h in handles): continue
        components={}
        for var,e in instructions.items():
            m=re.fullmatch(r'extractvalue %dx.types.ResRet.f32 '+re.escape(sample)+r', ([01])',e)
            if m: components[int(m[1])]=var
        if set(components)!={0,1}: continue
        x,y=affine(components[0]),affine(components[1])
        if not x or not y: continue
        world=[]
        for i in range(3):
            t=inputs.get((signatures['TANGENT'],i));b=inputs.get((signatures['BINORMAL'],i));n=inputs.get((signatures['NORMAL'],i))
            if not all((t,b,n)): break
            tx=binary('fmul',x[0],t);by=binary('fmul',y[0],b)
            add=binary('fadd',by,n) if by else None
            value=binary('fadd',tx,add) if tx and add else None
            if not value: break
            world.append(value)
        if len(world)!=3: continue
        arguments=', '.join('float '+v for v in world+world)
        dots=[v for v,e in instructions.items() if '@dx.op.dot3.f32(i32 55, '+arguments+')' in e]
        inverse=[v for v,e in instructions.items() if any('@dx.op.unary.f32(i32 25, float '+d+')' in e for d in dots)]
        if not any(all(binary('fmul',w,inv) for w in world) for inv in inverse): continue
        return {'encoding':'derivative_tangent_normal','x_scale':x[1],'x_bias':x[2],
                'y_scale':y[1],'y_bias':y[2],'z':1.0,
                'formula':'normalize(T*(R*x_scale+x_bias) + B*(G*y_scale+y_bias) + N)',
                'evidence':'Reflected normal resource, signature semantics, sample channels, affine arithmetic and final vector normalization'}
    return None


def convert_derivative_normal(source, destination, contract):
    """Make an explicitly derived Blender RGB map, preserving the original XY PNG."""
    from PIL import Image
    import numpy as np
    # 256x256 lookup (R, G) -> RGB, then one table lookup per pixel with numpy instead of a Python loop.
    steps=np.arange(256,dtype=np.float64)/255
    x=np.repeat(steps*contract['x_scale']+contract['x_bias'],256)  # r major, g minor (index r*256+g)
    y=np.tile(steps*contract['y_scale']+contract['y_bias'],256)
    length=np.sqrt(x*x+y*y+1)
    lookup=np.round((np.stack((x,y,np.ones_like(x)),axis=1)/length[:,None]*.5+.5)*255).astype(np.uint8)
    with Image.open(source) as image:
        pixels=np.asarray(image.convert('RGBA'))
        index=pixels[...,0].astype(np.int32)*256+pixels[...,1]
        Image.fromarray(lookup[index],'RGB').save(destination)
