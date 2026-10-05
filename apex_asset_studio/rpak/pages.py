"""Bounded reads of unrelocated RPak pages and registered GUID references."""
from __future__ import annotations
import struct
from .structures import PagePtr


class PageReader:
    def __init__(self, archive):
        self.archive = archive
        self.data = archive.data
        if archive.header.patch_count and not getattr(archive,'pages_reconstructed',False):
            raise ValueError("patch page reconstruction is not implemented; payload resolution withheld")
        self.offsets = []
        pos = archive.layout.page_data
        for page in archive.pages:
            self.offsets.append(pos)
            pos += page.size
        if pos > len(self.data):
            raise ValueError(f"page data truncated: {pos} > {len(self.data)}")

    def resolve(self, ptr: PagePtr, size: int = 1) -> int:
        if ptr.index < 0 or ptr.index >= len(self.offsets):
            raise ValueError(f"invalid page index {ptr.index}")
        page = self.archive.pages[ptr.index]
        if size < 0 or ptr.offset < 0 or ptr.offset + size > page.size:
            raise ValueError(f"read outside page {ptr.index}: {ptr.offset}+{size} > {page.size}")
        return self.offsets[ptr.index] + ptr.offset

    def pointer(self, pos: int, size: int = 1, nullable: bool = False) -> int | None:
        index, offset = struct.unpack_from("<ii", self.data, pos)
        if index == 0 and offset == 0 and nullable:
            return None
        return self.resolve(PagePtr(index, offset), size)

    def string(self, pos: int | None, limit: int = 4096, utf16: bool = False) -> str | None:
        if pos is None:
            return None
        # A terminated string may not cross its owning page.
        import bisect
        page_index = bisect.bisect_right(self.offsets, pos) - 1
        if page_index < 0:
            raise ValueError("string outside page data")
        end = min(self.offsets[page_index] + self.archive.pages[page_index].size, pos + limit)
        if utf16:
            for i in range(pos, end - 1, 2):
                if self.data[i:i + 2] == b"\0\0":
                    return self.data[pos:i].decode("utf-16-le")
        else:
            i = self.data.find(b"\0", pos, end)
            if i != -1:
                return self.data[pos:i].decode("utf-8")
        raise ValueError("unterminated string")

    def header(self, asset) -> int:
        return self.resolve(asset.head, asset.header_struct_size)

    def dependencies(self, asset) -> list[dict]:
        first = asset.dependencies_index
        count = asset.dependencies_count
        if first + count > self.archive.header.num_guid_refs:
            raise ValueError("asset dependency range exceeds GUID reference table")
        refs = []
        for i in range(first, first + count):
            index, offset = struct.unpack_from("<ii", self.data, self.archive.layout.guid_refs + i * 8)
            pos = self.resolve(PagePtr(index, offset), 8)
            guid = struct.unpack_from("<Q", self.data, pos)[0]
            if guid:
                refs.append({"guid": f"{guid:016X}", "page": index, "offset": offset, "reference_index": i})
        return refs
