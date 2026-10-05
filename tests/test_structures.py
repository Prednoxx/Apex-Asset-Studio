import struct
import unittest
from apex_asset_studio.rpak.structures import RpakHeader, RPAK_MAGIC, compute_layout

class StructuresTests(unittest.TestCase):
    def test_v8_header(self):
        b = bytearray(0x80)
        struct.pack_into('<Ihh', b, 0, RPAK_MAGIC, 8, 0)
        struct.pack_into('<QQq', b, 0x08, 123, 456, 1000)
        struct.pack_into('<q', b, 0x30, 2000)
        struct.pack_into('<hhHHh', b, 0x48, 0, 0, 1, 2, 0)
        struct.pack_into('<iiiiii', b, 0x54, 3, 4, 5, 6, 0, 0)
        h = RpakHeader.parse(bytes(b))
        self.assertEqual(h.version, 8)
        self.assertEqual(h.num_assets, 4)
        self.assertEqual(h.num_pages, 2)
        self.assertEqual(h.dcmp_size, 2000)

if __name__ == '__main__':
    unittest.main()
