"""The numpy vertex decoder must match the original per-vertex decoder exactly."""
import random
import struct
import unittest

from apex_asset_studio.rpak.model import Buffer, Mesh, decode_vertices, decode_vertices_reference, uv_channel_indices


def _normal(rng):
    while True:
        value = rng.getrandbits(32)
        if (value >> 29) & 3 != 3: return value


def _buffer(rng, count, packed_position, extended, color, uv_count):
    vf = (2 if packed_position else 1) | (10 << 8) | (5 << 12) | (0x10 if color else 0)
    for channel in range(uv_count): vf |= 2 << (24 + channel * 4)
    extras = bytearray(); vertices = bytearray()
    for _ in range(count):
        if packed_position: vertices += struct.pack('<Q', rng.getrandbits(64) & ((1 << 64) - 1))
        else: vertices += struct.pack('<3f', *(rng.uniform(-100, 100) for _ in range(3)))
        if extended:
            n = rng.randint(0, 4)
            if n == 0:
                vertices += struct.pack('<HHI', 32767, 0, rng.randint(0, 9))
            else:
                w0 = rng.randint(1, 8000); start = len(extras) // 4; left = 32767 - w0
                for _m in range(n - 1):
                    w = rng.randint(0, 5000); left -= w; extras += struct.pack('<HH', w, rng.randint(0, 9))
                vertices += struct.pack('<HHI', w0, start, rng.randint(0, 9) | (rng.randint(0, 9) << 10) | (n << 24))
        else:
            count_w = rng.randint(0, 2); a = rng.randint(0, 16000); b = rng.randint(0, 16000)
            bones = rng.randint(0, 9) | (rng.randint(0, 9) << 8) | (rng.randint(0, 9) << 16) | (count_w << 24)
            vertices += struct.pack('<HHI', a, b, bones)
        vertices += struct.pack('<I', _normal(rng))
        if color: vertices += bytes(rng.getrandbits(8) for _ in range(4))
        for _c in range(uv_count): vertices += struct.pack('<2f', rng.uniform(-2, 2), rng.uniform(-2, 2))
    stride = len(vertices) // count
    data = bytes(16) + vertices + extras
    return Buffer(data), vf, stride, 16, 16 + len(vertices), len(extras)


class VertexDecoderTests(unittest.TestCase):
    def test_fast_decoder_matches_reference(self):
        rng = random.Random(1234)
        states = list(range(20, 30))
        for packed_position in (False, True):
            for extended in (False, True):
                for color in (False, True):
                    for uv_count in (0, 1, 2):
                        g, vf, stride, base, extra_base, es = _buffer(rng, 64, packed_position, extended, color, uv_count)
                        flags = 0x4000 if extended else 0
                        meshes = []
                        for decoder in (decode_vertices_reference, decode_vertices):
                            mesh = Mesh('m', 0); mesh.uv_indices = uv_channel_indices(vf)
                            decoder(mesh, g, base, 64, stride, vf, flags, states, extra_base, es)
                            meshes.append(mesh)
                        ref, fast = meshes
                        with self.subTest(packed=packed_position, extended=extended, color=color, uvs=uv_count):
                            self.assertEqual(ref.packed_normals, fast.packed_normals)
                            self.assertEqual([tuple(map(float, p)) for p in ref.positions], fast.positions)
                            self.assertEqual(ref.weights, fast.weights)
                            self.assertEqual([tuple(c) for c in ref.colors], fast.colors)
                            self.assertEqual([[tuple(u) for u in s] for s in ref.uvs], [[tuple(u) for u in s] for s in fast.uvs])
                            for a, b in zip(ref.normals, fast.normals):
                                for x, y in zip(a, b): self.assertAlmostEqual(x, y, places=12)
                            for a, b in zip(ref.tangents, fast.tangents):
                                for x, y in zip(a, b): self.assertAlmostEqual(x, y, places=12)

    def test_empty_mesh_without_vertex_format(self):
        # lower LODs can hold empty meshes whose vertex flags are all zero; the reference decoder accepts them
        g = Buffer(b'\0' * 64)
        for decoder in (decode_vertices_reference, decode_vertices):
            mesh = Mesh('m', 0)
            decoder(mesh, g, 0, 0, 0, 0, 0, [], 0, 0)
            self.assertEqual((mesh.positions, mesh.weights, mesh.uvs), ([], [], []))

    def test_speed(self):
        import time
        rng = random.Random(7)
        g, vf, stride, base, extra_base, es = _buffer(rng, 20000, True, False, False, 1)
        timings = []
        for decoder in (decode_vertices_reference, decode_vertices):
            mesh = Mesh('m', 0); mesh.uv_indices = uv_channel_indices(vf)
            start = time.perf_counter(); decoder(mesh, g, base, 20000, stride, vf, 0, list(range(10)), extra_base, es)
            timings.append(time.perf_counter() - start)
        print(f'\nreference {timings[0]*1000:.0f} ms, fast {timings[1]*1000:.0f} ms for 20,000 vertices')
        self.assertLess(timings[1], timings[0])


if __name__ == '__main__': unittest.main()
