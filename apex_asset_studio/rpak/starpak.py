from __future__ import annotations

import os
import struct
from dataclasses import dataclass
from pathlib import Path


@dataclass(slots=True)
class StarPakEntry:
    offset: int
    size: int


class StarPakIndex:
    def __init__(self, path: str | os.PathLike[str]):
        self.path = Path(path)
        self.entries: dict[int, StarPakEntry] = {}

    def parse(self) -> "StarPakIndex":
        size = self.path.stat().st_size
        if size < 8:
            raise ValueError("StarPak too small")
        with self.path.open("rb") as f:
            f.seek(size - 8)
            count = struct.unpack("<Q", f.read(8))[0]
            table_bytes = count * 16
            if table_bytes + 8 > size:
                raise ValueError("invalid StarPak footer table")
            f.seek(size - 8 - table_bytes)
            table_start = size - 8 - table_bytes
            for _ in range(count):
                off, block_size = struct.unpack("<QQ", f.read(16))
                if block_size:
                    if off + block_size > table_start or off in self.entries:
                        raise ValueError("invalid or duplicate StarPak block extent")
                    self.entries[off] = StarPakEntry(off, block_size)
        return self

    def read(self, offset: int, size: int | None = None) -> bytes:
        entry = self.entries.get(offset)
        if entry is None:
            raise KeyError(f"StarPak offset {offset:#x} not indexed")
        read_size = size if size is not None else entry.size
        if read_size < 0 or read_size > entry.size:
            raise ValueError("read exceeds registered StarPak block")
        with self.path.open("rb") as f:
            f.seek(offset)
            result = f.read(read_size)
            if len(result) != read_size:
                raise ValueError("truncated StarPak block")
            return result
