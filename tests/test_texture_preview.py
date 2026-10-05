import struct,tempfile,unittest
from pathlib import Path
from types import SimpleNamespace as Data
from PIL import Image
from apex_asset_studio.rpak.structures import PagePtr
from apex_asset_studio.rpak.texture import extract_texture


class TexturePreviewTests(unittest.TestCase):
    def test_preview_uses_native_mip_without_writing_export_payloads(self):
        data=bytearray(256)
        struct.pack_into('<4H',data,8,31,4,4,1)
        data[16]=1;data[24]=2
        data[128:144]=bytes((0,255,0,255))*4
        data[144:208]=bytes((255,0,0,255))*16
        asset=Data(type_name='txtr',version=10,head=PagePtr(0,0),data=PagePtr(0,128),header_struct_size=56,guid=1)
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            archive=Data(data=data,header=Data(patch_count=0),layout=Data(page_data=0),
                         pages=[Data(size=256)],path=root/'fixture.rpak',game_root=root)
            preview=extract_texture(archive,asset,root/'preview','Texture',preview_size=2)
            self.assertEqual(preview['preview_mip'],1)
            with Image.open(root/'preview/Texture.png') as image:
                self.assertEqual(image.size,(2,2));self.assertEqual(image.getpixel((0,0)),(0,255,0,255))
            self.assertFalse((root/'preview/Texture.dds').exists())
            self.assertFalse((root/'preview/original').exists())
            extract_texture(archive,asset,root/'export','Texture')
            with Image.open(root/'export/Texture.png') as image:
                self.assertEqual(image.size,(4,4));self.assertEqual(image.getpixel((0,0)),(255,0,0,255))
            self.assertEqual((root/'export/Texture.dds').read_bytes()[148:],bytes((255,0,0,255))*16+bytes((0,255,0,255))*4)
