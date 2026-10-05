import sys
import tempfile
import types
import unittest
from pathlib import Path

from apex_asset_studio.rpak.rtech import OodleRuntime


class OodleBackendTests(unittest.TestCase):
    def test_prefers_pyooz_module(self):
        previous = sys.modules.get("ooz")
        fake = types.SimpleNamespace(decompress=lambda data, size: b"X" * size)
        sys.modules["ooz"] = fake
        try:
            with tempfile.TemporaryDirectory() as td:
                runtime = OodleRuntime(Path(td))
                self.assertTrue(runtime.available)
                self.assertEqual(runtime.description, "Open-source ooz (pyooz)")
                self.assertEqual(runtime.decompress(b"abc", 4), b"XXXX")
        finally:
            if previous is None:
                sys.modules.pop("ooz", None)
            else:
                sys.modules["ooz"] = previous


if __name__ == "__main__":
    unittest.main()
