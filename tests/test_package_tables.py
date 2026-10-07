import struct
import tempfile
import unittest
from pathlib import Path

from apex_asset_studio.rpak import starpak


class StarPakIndexTest(unittest.TestCase):
    """Cached table matches reference reads."""
    def test_index_and_cache(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'test.starpak'
            blocks = [(0, 4096), (4096, 8192), (12288, 0), (12288, 4096)]
            body = bytes(16384)
            table = b''.join(struct.pack('<QQ', off, size) for off, size in blocks)
            path.write_bytes(body + table + struct.pack('<Q', len(blocks)))
            first = starpak.StarPakIndex(path).parse()
            self.assertEqual(sorted(first.entries), [0, 4096, 12288])
            self.assertEqual(first.entries[4096].size, 8192)
            again = starpak.StarPakIndex(path).parse()
            self.assertIs(again.entries, first.entries)
            self.assertEqual(len(again.read(4096)), 8192)

    def test_rejects_overlapping_table(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'bad.starpak'
            table = struct.pack('<QQ', 0, 999999)
            path.write_bytes(bytes(64) + table + struct.pack('<Q', 1))
            with self.assertRaises(ValueError):
                starpak.StarPakIndex(path).parse()


if __name__ == '__main__':
    unittest.main()
