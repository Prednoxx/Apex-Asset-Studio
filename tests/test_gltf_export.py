import json
import struct
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace as Data
from PIL import Image
from apex_asset_studio.export.gltf import write_gltf
from apex_asset_studio.export.package import export_package


class GltfExportTests(unittest.TestCase):
    def test_unresolved_material_family_cannot_export_a_substitute(self):
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp)/'exports'
            model = Data(material_family_resolved=False, family='missing_skin')
            with self.assertRaisesRegex(ValueError, 'Material set unavailable'):
                export_package(model, None, None, output, 'missing_skin')
            self.assertFalse(output.exists())
    def test_glb_embeds_images_and_converts_geometry_and_bind_matrices_to_metres(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);(root/'textures').mkdir()
            texture=root/'textures/color.png';Image.new('RGB',(2,2),'red').save(texture)
            bone=Data(name='root',parent=-1,translation=(1,0,0),rotation=(0,0,0,1),scale=(1,1,1),
                      inverse_bind=(1,0,0,-1,0,1,0,0,0,0,1,0))
            mesh=Data(name='triangle',positions=[(0,0,0),(1,0,0),(0,1,0)],normals=[(0,0,1)]*3,
                      tangents=[],uvs=[[(0,0)],[(1,0)],[(0,1)]],colors=[],
                      weights=[[(0,1)]]*3,indices=[0,2,1],material=0)
            model=Data(name='test.rmdl',guid='1',family='base',warnings=[],materials=['2'],bones=[bone],lods={0:[mesh]})
            output=root/'test.glb'
            write_gltf(model,[{'name':'material','textures':[{'role':'basecolor','path':'textures/color.png'}]}],output)
            raw=output.read_bytes();self.assertEqual(struct.unpack_from('<4sII',raw),(b'glTF',2,len(raw)))
            length=struct.unpack_from('<I',raw,12)[0];doc=json.loads(raw[20:20+length])
            blob=raw[20+length+8:]
            self.assertNotIn('uri',doc['images'][0])
            view=doc['bufferViews'][doc['images'][0]['bufferView']]
            self.assertEqual(blob[view['byteOffset']:view['byteOffset']+view['byteLength']],texture.read_bytes())
            self.assertAlmostEqual(doc['nodes'][1]['translation'][0],.0254)
            position=doc['accessors'][doc['meshes'][0]['primitives'][0]['attributes']['POSITION']]
            view=doc['bufferViews'][position['bufferView']]
            self.assertAlmostEqual(struct.unpack_from('<3f',blob,view['byteOffset']+12)[0],.0254,places=6)
            ib=doc['bufferViews'][doc['accessors'][doc['skins'][0]['inverseBindMatrices']]['bufferView']]
            self.assertAlmostEqual(struct.unpack_from('<16f',blob,ib['byteOffset'])[12],-.0254,places=6)
            index_view = doc['bufferViews'][doc['accessors'][doc['meshes'][0]['primitives'][0]['indices']]['bufferView']]
            self.assertEqual(struct.unpack_from('<3H', blob, index_view['byteOffset']), (0,1,2))
