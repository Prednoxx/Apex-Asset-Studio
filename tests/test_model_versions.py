"""Synthetic model data: no game content is embedded in these tests."""
import struct
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from apex_asset_studio.rpak.metadata import decode_archive_metadata
from apex_asset_studio.rpak.model import decode_model
from apex_asset_studio.rpak.structures import PagePtr


def model_fixture(version):
    studio = bytearray(768)
    struct.pack_into('<3H', studio, 0x74, 1, 0x100, 0x110)
    struct.pack_into('<H', studio, 0xda, 0x140)
    struct.pack_into('<9H', studio, 0x140, 1, 0, 0, 20, 32, 48, 60, 0, 108)
    struct.pack_into('<H', studio, 0x10a, 0x20)
    struct.pack_into('<h', studio, 0x110, -1)
    studio[0x120:0x125] = b'root\0'
    struct.pack_into('<4f', studio, 0x160, 0, 0, 0, 1)
    struct.pack_into('<12f', studio, 0x17c, 1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0)
    struct.pack_into('<3f', studio, 0x1ac, 1, 1, 1)
    struct.pack_into('<5H', studio, 0x90, 1, 0x200, 1, 1, 0x208)
    struct.pack_into('<Q', studio, 0x200, 123)
    struct.pack_into('<2H', studio, 0x9a, 1, 0x210)
    struct.pack_into('<H', studio, 0x212, 16)
    struct.pack_into('<i', studio, 0x218, 1)
    struct.pack_into('<4H', studio, 0x222, 1, 1, 0, 16)
    struct.pack_into('<2H', studio, 0xb0, 0x250 - 0xb0, 1)
    struct.pack_into('<4H', studio, 0xc4, 0x260 - 0xc4, 1, 0x270 - 0xc8, 1)
    vg = bytearray(168)
    struct.pack_into('<4BI', vg, 0, 0, 1, 0, 1, 4)
    struct.pack_into('<4BI', vg, 8, 1, 0, 0, 0, 4)
    vf = 1 | (10 << 8) | (5 << 12) | (2 << 24)
    struct.pack_into('<QIHH8I', vg, 16, vf, 3, 32, 1, 32, 0x10000003, 32, 96, 0, 0, 0, 0)
    struct.pack_into('<3H', vg, 64, 0, 1, 2)
    normal = (2 << 29) | (256 << 19) | (256 << 10)
    for i, position in enumerate(((0, 0, 0), (1, 0, 0), (0, 1, 0))):
        struct.pack_into('<3fHHII2f', vg, 72 + i * 32, *position, 0, 0, 0, normal, 0, 0)
    struct.pack_into('<iii4B', studio, 0x260, 0, len(vg), len(vg), 0, 0, 1, 1)
    data = bytearray(128) + studio
    struct.pack_into('<4i', data, 0, 0, 128, 0, 96)
    name = b'mdl/test.rmdl\0'
    data[96:96 + len(name)] = name
    asset = SimpleNamespace(type_name='mdl_', version=version, header_struct_size=96,
                            head=PagePtr(0, 0), guid=1, dependencies_count=0, dependencies_index=0)
    archive = SimpleNamespace(data=data, path=Path('test.rpak'), game_root=Path('.'),
                              header=SimpleNamespace(patch_count=0, num_guid_refs=0),
                              layout=SimpleNamespace(page_data=0),
                              pages=[SimpleNamespace(size=len(data))], assets=[asset])
    return archive, asset, bytes(vg)


class ModelVersionTests(unittest.TestCase):
    def test_v20_and_v21_decode_same_triangle_and_skeleton(self):
        for version in (20, 21):
            with self.subTest(version=version):
                archive, asset, vg = model_fixture(version)
                with patch('apex_asset_studio.rpak.model.StreamingReader') as streaming, \
                     patch('apex_asset_studio.rpak.model.OodleRuntime'):
                    streaming.return_value.read.return_value = vg
                    model = decode_model(archive, asset)
                self.assertEqual(model.name, 'mdl/test.rmdl')
                self.assertEqual(model.bones[0].name, 'root')
                self.assertEqual(model.materials, ['000000000000007B'])
                self.assertEqual(model.lods[0][0].indices, [0, 1, 2])
                self.assertEqual(model.lods[0][0].positions, [(0, 0, 0), (1, 0, 0), (0, 1, 0)])
                self.assertEqual(model.lods[0][0].weights, [[(0, 1.0)]] * 3)

    def test_metadata_recognizes_v21_model(self):
        archive, _, _ = model_fixture(21)
        detail = decode_archive_metadata(archive)[0]
        self.assertEqual(detail['status'], 'model_header_decoded')
        self.assertEqual(detail['name'], 'mdl/test.rmdl')
        self.assertEqual(detail['details']['animation_rigs'], [])

    def test_unknown_versions_remain_rejected(self):
        for version in (19, 22):
            archive, asset, _ = model_fixture(version)
            with self.assertRaisesRegex(ValueError, 'model version .*not supported'):
                decode_model(archive, asset)
