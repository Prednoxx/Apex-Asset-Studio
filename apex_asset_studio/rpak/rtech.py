from __future__ import annotations

import base64
import ctypes
import glob
import importlib
import os
import struct
import sys
from dataclasses import dataclass
from pathlib import Path

# The RTech container decoder table is derived from the public RSX implementation.
# RSX is AGPL-3.0; this project is distributed under AGPL-3.0 as well.
_LUT_B64 = (
"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"
)
_LUT = base64.b64decode(_LUT_B64)
if len(_LUT) != 0x720:
    raise RuntimeError(f"Invalid embedded RTech LUT size: {len(_LUT)}")

MASK64 = (1 << 64) - 1


def _u64(v: int) -> int:
    return v & MASK64


def _u32(v: int) -> int:
    return v & 0xFFFFFFFF


def _s8(v: int) -> int:
    return v - 256 if v & 0x80 else v


def _read_u64(buf: bytes | bytearray | memoryview, pos: int) -> int:
    # The native decoder performs unaligned qword reads. Pad short tail reads.
    if pos < 0:
        raise ValueError("negative read position")
    end = pos + 8
    if end <= len(buf):
        return int.from_bytes(buf[pos:end], "little")
    tail = bytes(buf[pos:]) + b"\0" * max(0, end - len(buf))
    return int.from_bytes(tail[:8], "little")


def _read_u32_lut(byte_offset: int) -> int:
    return int.from_bytes(_LUT[byte_offset: byte_offset + 4], "little")


@dataclass(slots=True)
class PakDecoderContext:
    input_buf: bytes
    file_size: int = 0
    decomp_size: int = 0
    input_inv_mask: int = MASK64
    output_inv_mask: int = MASK64
    header_offset: int = 0
    file_byte_position: int = 0
    decomp_byte_position: int = 0
    buffer_size_needed: int = 0
    current_byte: int = 0
    current_byte_bit: int = 0
    qword70: int = 0
    compressed_stream_size: int = 0
    decomp_stream_size: int = 0


def init_pak_decoder(data: bytes, data_size: int, data_offset: int, header_size: int) -> PakDecoderContext:
    """Initialize Respawn/RTech's RPak LZ decoder for a full in-memory input buffer."""
    ctx = PakDecoderContext(input_buf=data)
    ctx.file_size = data_offset + data_size

    v7 = _read_u64(data, data_offset + header_size)
    unk_pos = data_offset + header_size + 8
    ctx.file_byte_position = unk_pos

    v8 = v7 & 0x3F
    v7 >>= 6
    ctx.decomp_byte_position = header_size
    ctx.decomp_size = (v7 & ((1 << v8) - 1)) | (1 << v8)

    shift = (v8 + 6) & 0xFF
    next_q = _read_u64(data, unk_pos)
    v9 = _u64((v7 >> v8) | _u64(next_q << ((64 - shift) & 63))) if shift else (v7 >> v8)
    v10 = unk_pos + ((v8 + 6) >> 3)
    v8 = (v8 + 6) & 7
    ctx.file_byte_position = v10

    v11 = v8 + 13
    v12 = (MASK64 >> v8) & v9
    v13 = (((v12 & 0xFF) - 1) & 0x3F) + 1
    v14 = MASK64 >> (64 - v13)
    ctx.input_inv_mask = v14

    v15 = v10 + (v11 >> 3)
    output_bits = (((v12 >> 6) - 1) & 0x3F)
    ctx.output_inv_mask = MASK64 >> (63 - output_bits)

    next_q2 = _read_u64(data, v10)
    shift2 = v11 & 0xFF
    v16 = _u64((v12 >> 13) | _u64(next_q2 << ((64 - shift2) & 63))) if shift2 else (v12 >> 13)
    ctx.file_byte_position = v15
    v17 = v11 & 7
    v18 = (MASK64 >> v17) & v16

    if v14 == MASK64:
        ctx.header_offset = 0
        v21 = data_size
    else:
        v19 = v13 >> 3
        ctx.header_offset = v19 + 1
        v20 = _read_u64(data, v15)
        ctx.file_byte_position = v15 + v19 + 1
        bits = 8 * (v19 + 1)
        v21 = v20 & ((1 << bits) - 1)

    result = ctx.decomp_size
    v23 = ctx.output_inv_mask
    ctx.qword70 = _u64(ctx.input_inv_mask + data_offset - 6)
    ctx.buffer_size_needed = v21 + data_offset
    ctx.current_byte = v18
    ctx.current_byte_bit = v17
    ctx.compressed_stream_size = v21 + data_offset
    ctx.decomp_stream_size = result

    if result - 1 > v23:
        v24 = v21 + data_offset - ctx.header_offset
        ctx.decomp_stream_size = v23 + 1
        ctx.compressed_stream_size = v24

    return ctx


def _overlap_copy(out: bytearray, dst: int, src: int, count: int) -> None:
    if src < 0:
        raise ValueError(f"invalid back-reference: src={src}, dst={dst}, count={count}")
    # LZ copies are allowed to overlap; copy byte-wise to preserve that behavior.
    for i in range(count):
        if src + i >= len(out):
            raise ValueError("back-reference exceeded output buffer")
        out[dst + i] = out[src + i]


def decompress_rtech_payload(file_data: bytes, header_size: int, compressed_size: int, expected_decompressed_size: int | None = None) -> bytes:
    """Decode an RTech-compressed RPak into a complete decompressed RPak buffer.

    The returned buffer includes the original RPak header at the front, matching the
    layout expected by the archive parser.
    """
    ctx = init_pak_decoder(file_data, compressed_size, 0, header_size)
    total_size = expected_decompressed_size or ctx.decomp_size
    if total_size < header_size:
        raise ValueError(f"invalid decompressed size {total_size}")

    out = bytearray(total_size)
    out[:header_size] = file_data[:header_size]

    v5 = ctx.decomp_byte_position
    v7 = ctx.current_byte_bit
    v8 = ctx.current_byte
    v9 = ctx.file_byte_position
    v11_data = file_data
    v12 = 0
    decomp_size = min(ctx.decomp_size, total_size)
    compressed_limit = min(ctx.compressed_stream_size, len(file_data))

    # This is the full-buffer path used by the application. RSX's native decoder also
    # supports circular streaming buffers; Apex Asset Studio materializes the whole file.
    # Native decoder performs one accumulator normalization before entering its
    # command loop, then normalizes again at the tail of each iteration.
    if v7:
        q = _read_u64(v11_data, v9)
        v13 = _u64(_u64(q << ((64 - v7) & 63)) | v8)
        old_v7 = v7
        v7 &= 7
        v9 += old_v7 >> 3
        v8 = (MASK64 >> v7) & v13

    iteration_guard = 0
    while v5 < decomp_size:
        iteration_guard += 1
        if iteration_guard > max(10_000_000, decomp_size * 4):
            raise RuntimeError("RTech decoder iteration guard tripped")

        v15 = _u64(v12 << 8)
        lut_i = (v8 & 0xFF) + v15
        if lut_i + 512 >= len(_LUT):
            raise ValueError(f"RTech LUT index out of range: {lut_i}")
        v17 = _LUT[lut_i + 512]
        v18 = (v8 & 0xFF) + v15
        v7 += v17
        v19 = v8 >> v17
        v20 = _s8(_LUT[v18])

        if v20 < 0:
            v56 = -v20
            v12 = 1
            expected_fast = _LUT[(v15 >> 8) + 1248]
            if v56 == expected_fast:
                if decomp_size - v5 < 0x10:
                    v56 = 1
                v59 = v19 & 0xFF
                v60 = v19 >> 3
                v61 = v59 & 7
                v62 = v60
                if v61:
                    v63 = _LUT[1232 + v61]
                    v64 = _LUT[1240 + v61]
                else:
                    v62 = v60 >> 4
                    v65 = v60 & 0xF
                    v7 += 4
                    v63 = _read_u32_lut(1152 + 4 * v65)
                    v64 = _LUT[1216 + v65]
                v7 += v64 + 3
                v19 = v62 >> v64
                mask = (1 << v64) - 1 if v64 else 0
                v66 = v63 + (v62 & mask) + v56
                if v9 + v66 > len(file_data) or v5 + v66 > len(out):
                    raise ValueError("RTech literal run exceeds buffer")
                out[v5:v5 + v66] = file_data[v9:v9 + v66]
                v9 += v66
                v5 += v66
            else:
                if v9 + v56 > len(file_data) or v5 + v56 > len(out):
                    raise ValueError("RTech literal copy exceeds buffer")
                out[v5:v5 + v56] = file_data[v9:v9 + v56]
                v9 += v56
                v5 += v56
        else:
            v21 = v19 & 0xF
            v12 = 0
            shift_a = (((v21 - 31) & 0xFFFFFFFF) >> 3) & 6
            v22 = (_u32(v19) >> shift_a) & 0x3F
            branch = (24 * (shift_a & 2)) >> 4
            extra = (v19 >> 4) & branch
            v23 = 1 << (v21 + extra)
            lut_shift = _LUT[1088 + v22]
            distance_shift = shift_a + lut_shift
            total_shift = distance_shift + v21 + extra
            v7 += total_shift
            v25 = 16 * (v23 + ((v23 - 1) & (v19 >> distance_shift)))
            v19 >>= total_shift
            v26 = v25 + _LUT[1024 + v22] - 16
            src = v5 - v26

            if v20 == 17:
                v40 = v19 & 0xFF
                v41 = v19 >> 3
                v42 = v40 & 7
                v43 = v41
                if v42:
                    v44 = _LUT[1232 + v42]
                    v45 = _LUT[1240 + v42]
                else:
                    v7 += 4
                    v46 = v41 & 0xF
                    v43 = v41 >> 4
                    v44 = _read_u32_lut(1152 + 4 * v46)
                    v45 = _LUT[1216 + v46]
                    # Native code may pull one extra byte when its bit accumulator crosses
                    # a 64-bit boundary. Refill on the next loop is sufficient for the
                    # full-buffer path except for this explicit crossing case.
                    if v7 + v45 >= 61 and v9 < len(file_data):
                        v43 |= file_data[v9] << (61 - v7)
                        v9 += 1
                        v7 -= 8
                v7 += v45 + 3
                v19 = v43 >> v45
                mask = (1 << v45) - 1 if v45 else 0
                v48 = (v43 & mask) + v44 + 17
                if v5 + v48 > len(out):
                    raise ValueError("RTech match exceeds output buffer")
                if v26 < 8:
                    v50 = v48 - 13
                    # The native implementation accounts for its initial 16-byte speculative
                    # copy by reducing the committed output count by 13 here. The equivalent
                    # byte-wise path copies the actual match length directly.
                    actual = max(0, v50)
                    if v26 == 1:
                        if src < 0 or src >= len(out):
                            raise ValueError("invalid RTech repeat source")
                        out[v5:v5 + actual] = bytes([out[src]]) * actual
                    else:
                        _overlap_copy(out, v5, src, actual)
                    v5 += actual
                else:
                    _overlap_copy(out, v5, src, v48)
                    v5 += v48
            else:
                count = v20
                if count <= 0:
                    raise ValueError(f"invalid RTech match length {count}")
                if v5 + count > len(out):
                    raise ValueError("RTech fixed match exceeds output buffer")
                _overlap_copy(out, v5, src, count)
                v5 += count

        if v5 >= decomp_size:
            break
        if v9 >= compressed_limit:
            raise ValueError(
                f"RTech compressed stream ended early at input {v9:#x}; output {v5:#x}/{decomp_size:#x}"
            )

        # Refill the native bit accumulator for the next command.
        q = _read_u64(v11_data, v9)
        v13 = _u64(_u64(q << ((64 - v7) & 63)) | v19) if v7 else v19
        old_v7 = v7
        v7 &= 7
        v9 += old_v7 >> 3
        v8 = (MASK64 >> v7) & v13

    if v5 != decomp_size:
        raise ValueError(f"RTech decode size mismatch: {v5} != {decomp_size}")
    return bytes(out[:decomp_size])


class OodleRuntime:
    """Oodle-compatible decompression backend.

    Preferred backend is the open-source ``pyooz`` package (GPL-3.0-or-later), which
    exposes the ooz Kraken/Mermaid/Selkie/Leviathan decoder directly to Python. A
    locally installed Oodle DLL is retained only as a fallback. No proprietary Oodle
    binary is bundled by Apex Asset Studio.
    """

    def __init__(self, game_root: str | os.PathLike[str]):
        self.game_root = Path(game_root)
        self.path: Path | None = None
        self.dll = None
        self._decompress = None
        self._pyooz = None
        self.backend = "Unavailable"
        self._find_and_load()

    def _find_and_load(self) -> None:
        # First use the redistributable/open-source decoder installed with AAS.
        try:
            module = importlib.import_module("ooz")
            if callable(getattr(module, "decompress", None)):
                self._pyooz = module
                self.backend = "Open-source ooz (pyooz)"
                return
        except Exception:
            pass

        # Fallback for developers/users who already have a compatible local Oodle DLL.
        patterns: list[Path] = []
        env_hint = os.environ.get("APEX_ASSET_STUDIO_OODLE_DLL")
        if env_hint:
            patterns.append(Path(env_hint))

        search_roots = [self.game_root]
        try:
            search_roots.append(Path(sys.executable).resolve().parent)
        except Exception:
            pass

        candidates: list[Path] = []
        candidates.extend(p for p in patterns if p.exists())
        for root in search_roots:
            for pattern in ("oo2core_*.dll", "**/oo2core_*.dll"):
                candidates.extend(Path(p) for p in glob.glob(str(root / pattern), recursive=True))

        candidates = sorted(set(candidates), key=lambda p: (len(p.parts), str(p).lower()))
        for candidate in candidates:
            try:
                dll = ctypes.WinDLL(str(candidate)) if os.name == "nt" else None
                if dll is None:
                    continue
                fn = getattr(dll, "OodleLZ_Decompress", None)
                if fn is None:
                    continue
                fn.restype = ctypes.c_longlong
                fn.argtypes = [
                    ctypes.c_void_p, ctypes.c_longlong,
                    ctypes.c_void_p, ctypes.c_longlong,
                    ctypes.c_int, ctypes.c_int, ctypes.c_int,
                    ctypes.c_void_p, ctypes.c_size_t,
                    ctypes.c_void_p, ctypes.c_void_p,
                    ctypes.c_void_p, ctypes.c_size_t,
                    ctypes.c_int,
                ]
                self.path = candidate
                self.dll = dll
                self._decompress = fn
                self.backend = f"Local Oodle DLL ({candidate.name})"
                return
            except Exception:
                continue

    @property
    def available(self) -> bool:
        return self._pyooz is not None or self._decompress is not None

    @property
    def description(self) -> str:
        if self._pyooz is not None:
            return self.backend
        if self.path is not None:
            return f"{self.backend}: {self.path}"
        return "Unavailable — install the pyooz dependency or provide a compatible local Oodle DLL"

    def decompress(self, compressed: bytes, raw_size: int) -> bytes:
        if self._pyooz is not None:
            data = self._pyooz.decompress(compressed, raw_size)
            if len(data) != raw_size:
                raise RuntimeError(f"ooz decompressed {len(data)} bytes; expected {raw_size}")
            return data

        if self._decompress is None:
            raise RuntimeError(
                "No Oodle decoder available. Install the pyooz package."
            )

        src = ctypes.create_string_buffer(compressed)
        dst = ctypes.create_string_buffer(raw_size)
        result = self._decompress(
            ctypes.byref(src), len(compressed),
            ctypes.byref(dst), raw_size,
            1, 0, 0,
            None, 0,
            None, None,
            None, 0,
            3,
        )
        if result <= 0:
            raise RuntimeError(f"OodleLZ_Decompress failed: {result}")
        return dst.raw[:raw_size]

