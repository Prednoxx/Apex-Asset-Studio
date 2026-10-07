"""Restart-aware Oodle framing."""
from __future__ import annotations

from dataclasses import dataclass
from threading import Event


class ScanCancelled(Exception):
    pass


@dataclass(frozen=True)
class OodleSpan:
    start: int
    end: int
    raw_size: int


def frame_stream(data: bytes, raw_size: int) -> list[OodleSpan]:
    if raw_size <= 0:
        raise ValueError("invalid Oodle output size")
    spans = []
    pos = done = start = span_size = 0
    while done < raw_size:
        if pos + 2 > len(data):
            raise ValueError("truncated Oodle block header")
        flags, codec = data[pos:pos + 2]
        if flags & 0x3F != 0x0C or codec & 0x7F not in (6, 10, 12):
            raise ValueError(f"unsupported Oodle block at {pos:#x}: {flags:#x}, {codec:#x}")
        if flags & 0x80 and span_size:
            spans.append(OodleSpan(start, pos, span_size))
            start, span_size = pos, 0
        pos += 2
        block_size = min(0x40000, raw_size - done)
        if flags & 0x40:
            pos += block_size
        else:
            if pos + 3 > len(data):
                raise ValueError("truncated Oodle quantum header")
            quantum = int.from_bytes(data[pos:pos + 3], "big")
            pos += 3
            encoded_size = quantum & 0x3FFFF
            if encoded_size == 0x3FFFF:
                if quantum >> 18 != 1:
                    raise ValueError("unsupported Oodle special quantum")
                pos += 1  # Repeated byte
            else:
                if encoded_size + 1 > block_size:
                    raise ValueError("Oodle quantum exceeds decoded block size")
                pos += encoded_size + 1 + (3 if codec & 0x80 else 0)
        if pos > len(data):
            raise ValueError("truncated Oodle block payload")
        done += block_size
        span_size += block_size
    spans.append(OodleSpan(start, pos, span_size))
    return spans


def decompress_stream(data: bytes, raw_size: int, runtime, stop: Event | None = None, prefix: bytes = b'') -> bytes:
    """Decode stream after supplied prefix."""
    spans = frame_stream(data, raw_size)
    out = bytearray(len(prefix) + raw_size)
    out[:len(prefix)] = prefix
    offset = len(prefix)
    for span in spans:
        if stop is not None and stop.is_set():
            raise ScanCancelled()
        decoded = runtime.decompress(bytes(data[span.start:span.end]), span.raw_size)
        if len(decoded) != span.raw_size:
            raise ValueError("Oodle restart span returned an incorrect size")
        out[offset:offset + span.raw_size] = decoded
        offset += span.raw_size
    return bytes(out)
