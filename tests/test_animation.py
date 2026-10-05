import json
import struct
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace as Data
import numpy as np
from apex_asset_studio.rpak.animation import curve_value,axis_values
from apex_asset_studio.rpak.model import Buffer
from apex_asset_studio.export.gltf import write_gltf


class AnimationTests(unittest.TestCase):
    def test_curve_seeks_across_blocks_and_decodes_signed_delta(self):
        data=Buffer(struct.pack('<BB2hBBh2b',0,2,100,-100,1,3,200,-5,8))
        self.assertEqual([curve_value(data,0,f,.5) for f in range(5)],[50.,-50.,100.,97.5,104.])

    def test_polynomial_residual_and_missing_axis(self):
        data=Buffer(struct.pack('<H2BBBhH',4|(4<<13),0,0,8,4,10,0b11100100))
        self.assertEqual(axis_values(data,0,2,1,(20,30,40)),[11.,30,40])

    def test_invalid_curve_block_fails(self):
        for header in ((0,0),(20,1)):
            with self.assertRaises(ValueError): curve_value(Buffer(bytes(header)),0,0,1)

    def test_animation_exports_seconds_metres_and_joint_targets(self):
        bone=Data(name='root',parent=-1,translation=(0,0,0),rotation=(0,0,0,1),scale=(1,1,1),
                  inverse_bind=(1,0,0,0,0,1,0,0,0,0,1,0))
        model=Data(name='model',guid='1',family='base',warnings=[],materials=[],bones=[bone],lods={0:[]})
        clip={'name':'clip','frames':2,'fps':30.,'guid':'2','loop':False,'rig_guid':'3','data_guid':'4','blend':0,
              'positions':np.array([[[0,0,0]],[[1,2,3]]]),'rotations':np.array([[[0,0,0,1]],[[0,0,1,0]]]),
              'scales':np.ones((2,1,3))}
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'clip.glb';write_gltf(model,[],path,animation=clip)
            raw=path.read_bytes();length=struct.unpack_from('<I',raw,12)[0]
            doc=json.loads(raw[20:20+length]);binary=raw[28+length:]
            animation=doc['animations'][0]
            self.assertEqual([c['target'] for c in animation['channels']],
                             [{'node':1,'path':p} for p in ('translation','rotation','scale')])
            sampler=animation['samplers'][0]
            time_view=doc['bufferViews'][doc['accessors'][sampler['input']]['bufferView']]
            self.assertAlmostEqual(struct.unpack_from('<2f',binary,time_view['byteOffset'])[1],1/30)
            values=doc['bufferViews'][doc['accessors'][sampler['output']]['bufferView']]
            for value,expected in zip(struct.unpack_from('<6f',binary,values['byteOffset'])[3:],(.0254,.0508,.0762)):
                self.assertAlmostEqual(value,expected)
