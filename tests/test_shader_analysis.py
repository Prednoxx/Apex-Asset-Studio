import unittest
from apex_asset_studio.rpak.shader import parse_dxc_resources
from apex_asset_studio.rpak.shader_analysis import derivative_normal_contract, sampled_channel_contract, anisotropy_direction_contract


class ShaderAnalysisTests(unittest.TestCase):
    def test_gather_components_are_neighbours_of_one_channel(self):
        text='''%1 = call %dx.types.Handle @dx.op.createHandle(i32 57, i8 0, i32 12, i32 6, i1 false)
%2 = call %dx.types.ResRet.f32 @dx.op.textureGather.f32(i32 73, %dx.types.Handle %1, %dx.types.Handle %90, float %20, float %21, float undef, float undef, i32 0, i32 0, i32 0)  ; TextureGather(srv,sampler,coord0,coord1,coord2,coord3,offset0,offset1,channel)
%3 = extractvalue %dx.types.ResRet.f32 %2, 3
%4 = call float @dx.op.unary.f32(i32 22, float %3)
%5 = fmul fast float %4, 0x401921FB60000000
%6 = call float @dx.op.unary.f32(i32 12, float %5)
%7 = fcmp fast ogt float %4, 5.000000e-01
%8 = select i1 %7, float 1.000000e+00, float -1.000000e+00
%9 = fmul fast float %6, %6
%10 = fsub fast float 1.000000e+00, %9
%11 = call float @dx.op.unary.f32(i32 24, float %10)
%12 = fmul fast float %8, %11
'''
        self.assertEqual(sampled_channel_contract(text,12)['sampled_components'],['R'])
        self.assertEqual(anisotropy_direction_contract(text,12)['channel'],'R')
        self.assertIsNone(anisotropy_direction_contract(text.replace('fmul fast float %4','fmul fast float %77'),12))
        self.assertIsNone(anisotropy_direction_contract(text,11))
        self.assertIsNone(anisotropy_direction_contract(text.replace('float -1.000000e+00','float 1.000000e+00'),12))

    def test_register_spaces_and_scalar_use_come_from_reflection(self):
        text='''; Resource Bindings:
; albedoTexture texture f32 2d T0 t0 1
; Bindless3d texture f32 3d T1 t0,space3unbounded
; glossTexture texture f32 2d T2 t2 1
; ViewId state:
%1 = call %dx.types.Handle @dx.op.createHandle(i32 57, i8 0, i32 2, i32 2, i1 false)
%2 = call %dx.types.ResRet.f32 @dx.op.sample.f32(i32 60, %dx.types.Handle %1, %dx.types.Handle %99)
%3 = extractvalue %dx.types.ResRet.f32 %2, 0
%4 = fsub fast float 1.000000e+00, %3
'''
        resources=parse_dxc_resources(text)
        self.assertEqual(resources[1]['space'],3)
        self.assertIsNone(resources[1]['count'])
        self.assertEqual(sampled_channel_contract(text,2),{'sampled_components':['R'],'one_minus_components':['R']})
        self.assertEqual(sampled_channel_contract(text.replace('\n','\r\n'),2),sampled_channel_contract(text,2))
        self.assertIsNone(derivative_normal_contract(text,2))

    def test_normal_recipe_requires_basis_and_final_normalization(self):
        lines=['!1 = !{i32 0, !"NORMAL"}', '!2 = !{i32 1, !"TANGENT"}', '!3 = !{i32 2, !"BINORMAL"}']
        for signature in range(3):
            for component in range(3):
                lines.append(f'%{10+signature*3+component} = call float @dx.op.loadInput.f32(i32 4, i32 {signature}, i32 0, i8 {component}, i32 undef)')
        lines += ['%1 = call %dx.types.Handle @dx.op.createHandle(i32 57, i8 0, i32 7, i32 1, i1 false)',
                  '%2 = call %dx.types.ResRet.f32 @dx.op.sample.f32(i32 60, %dx.types.Handle %1, %dx.types.Handle %99)',
                  '%3 = extractvalue %dx.types.ResRet.f32 %2, 0', '%4 = extractvalue %dx.types.ResRet.f32 %2, 1',
                  '%5 = fmul fast float %3, 2.000000e+00', '%6 = fmul fast float %4, 2.000000e+00',
                  '%7 = fadd fast float %5, -1.000000e+00', '%8 = fadd fast float %6, -1.000000e+00']
        world=[]
        for i in range(3):
            a,b,c,d=[f'%{30+i*4+j}' for j in range(4)]
            lines += [f'{a} = fmul fast float %7, %{13+i}',f'{b} = fmul fast float %8, %{16+i}',
                      f'{c} = fadd fast float {b}, %{10+i}',f'{d} = fadd fast float {c}, {a}']
            world.append(d)
        args=', '.join('float '+v for v in world+world)
        lines += [f'%60 = call float @dx.op.dot3.f32(i32 55, {args})','%61 = call float @dx.op.unary.f32(i32 25, float %60)']
        lines += [f'%{70+i} = fmul fast float {v}, %61' for i,v in enumerate(world)]
        contract=derivative_normal_contract('\n'.join(lines),7)
        self.assertEqual(contract['x_scale'],2)
        self.assertEqual(contract['y_bias'],-1)
        self.assertEqual(derivative_normal_contract('\r\n'.join(lines),7),contract)
        self.assertIsNone(derivative_normal_contract('\n'.join(lines[:-1]),7))
