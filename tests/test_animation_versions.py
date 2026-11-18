"""Synthetic headers: no game content is embedded in these tests."""
import struct
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from apex_asset_studio.rpak.animation import decode_animation
from apex_asset_studio.rpak.animation_metadata import decode_animation_header


class FakeReader:
    def __init__(self, models):
        self.data = bytearray(128)
        struct.pack_into('<H', self.data, 24, len(models))
        struct.pack_into(f'<{len(models)}Q', self.data, 64, *models)

    def header(self, asset): return 0
    def string(self, pointer): return 'animseq/test.rseq'
    def pointer(self, offset, size=None, nullable=False): return 8 if offset == 8 else 64


class AnimationVersionTests(unittest.TestCase):
    def test_sequence_metadata_accepts_v16(self):
        for version in (14, 16):
            with self.subTest(version=version):
                asset = SimpleNamespace(type_name='aseq', version=version, header_struct_size=64)
                name, details = decode_animation_header(FakeReader([0xABC]), asset)
                self.assertEqual(name, 'animseq/test.rseq')
                self.assertEqual(details['declared_models'], ['0000000000000ABC'])

    def test_unknown_sequence_versions_remain_rejected(self):
        for version in (15, 17):
            asset = SimpleNamespace(type_name='aseq', version=version, header_struct_size=64)
            with self.assertRaisesRegex(ValueError, 'unsupported'):
                decode_animation_header(FakeReader([]), asset)
            repository = SimpleNamespace(asset=lambda guid: (None, asset))
            with self.assertRaisesRegex(ValueError, f'Animation version {version} is not supported'):
                decode_animation(repository, None, '1', '2')

    def test_v16_passes_version_gate(self):
        asset = SimpleNamespace(type_name='aseq', version=16, header_struct_size=64)
        repository = SimpleNamespace(asset=lambda guid: (None, asset))
        with patch('apex_asset_studio.rpak.animation.PageReader', side_effect=RuntimeError('past gate')):
            with self.assertRaisesRegex(RuntimeError, 'past gate'):
                decode_animation(repository, None, '1', '2')


if __name__ == '__main__':
    unittest.main()
