from __future__ import annotations

import struct
from dataclasses import dataclass
from pathlib import Path

RPAK_MAGIC = 0x6B615052  # 'RPak' little-endian
FLAG_RTECH = 1 << 8
FLAG_OODLE = 1 << 9
FLAG_ZSTD = 1 << 15
FLAG_COMPRESSED = FLAG_RTECH | FLAG_OODLE | FLAG_ZSTD


def fourcc(value: int) -> str:
    return value.to_bytes(4, "little", signed=False).decode("latin1", errors="replace").rstrip("\0")


@dataclass(slots=True)
class RpakHeader:
    magic: int
    version: int
    flags: int
    created_time: int
    crc: int
    cmp_size: int
    dcmp_size: int
    header_size: int
    asset_size: int
    streaming_files_size: int
    opt_streaming_files_size: int
    num_segments: int
    num_pages: int
    patch_count: int
    num_pointers: int
    num_assets: int
    num_guid_refs: int
    num_dependencies: int
    num_external_refs: int
    external_refs_size: int
    unk_74: int = 0
    unk_78: int = 0

    @property
    def compressed(self) -> bool:
        return bool(self.flags & FLAG_COMPRESSED)

    @property
    def compression(self) -> str:
        if self.flags & FLAG_RTECH:
            return "RTech"
        if self.flags & FLAG_OODLE:
            return "Oodle"
        if self.flags & FLAG_ZSTD:
            return "ZSTD"
        return "None"

    @classmethod
    def parse(cls, data: bytes) -> "RpakHeader":
        if len(data) < 8:
            raise ValueError("file too small for RPak header")
        magic, version, flags = struct.unpack_from("<Ihh", data, 0)
        if magic != RPAK_MAGIC:
            got = magic.to_bytes(4, "little", signed=False)
            raise ValueError(f"invalid RPak magic: {got!r}")
        if version == 8:
            if len(data) < 0x80:
                raise ValueError("truncated v8 RPak header")
            created, crc, cmp_size = struct.unpack_from("<QQq", data, 0x08)
            dcmp_size = struct.unpack_from("<q", data, 0x30)[0]
            streaming, opt_streaming, num_segments, num_pages, patch_count = struct.unpack_from("<hhHHh", data, 0x48)
            num_pointers, num_assets, num_guid_refs, num_deps, num_external, external_size = struct.unpack_from("<iiiiii", data, 0x54)
            unk_74, unk_78 = struct.unpack_from("<II", data, 0x74)
            return cls(magic, version, flags, created, crc, cmp_size, dcmp_size, 0x80, 0x50,
                       streaming, opt_streaming, num_segments, num_pages, patch_count,
                       num_pointers, num_assets, num_guid_refs, num_deps,
                       num_external, external_size, unk_74, unk_78)
        if version == 7:
            if len(data) < 0x58:
                raise ValueError("truncated v7 RPak header")
            created, crc, cmp_size = struct.unpack_from("<QQq", data, 0x08)
            dcmp_size = struct.unpack_from("<q", data, 0x28)[0]
            streaming, num_segments, num_pages, patch_count = struct.unpack_from("<hHHh", data, 0x38)
            num_pointers, num_assets, num_guid_refs, num_deps, num_external, external_size = struct.unpack_from("<iiiiii", data, 0x40)
            return cls(magic, version, flags, created, crc, cmp_size, dcmp_size, 0x58, 0x48,
                       streaming, 0, num_segments, num_pages, patch_count,
                       num_pointers, num_assets, num_guid_refs, num_deps,
                       num_external, external_size)
        if version == 6:
            if len(data) < 0x58:
                raise ValueError("truncated v6 RPak header")
            created, crc, size = struct.unpack_from("<QQq", data, 0x08)
            streaming = struct.unpack_from("<i", data, 0x30)[0]
            num_segments, num_pages, num_pointers, num_assets, num_guid_refs, num_deps, num_external, external_size = struct.unpack_from("<iiiiiiii", data, 0x34)
            return cls(magic, version, flags, created, crc, size, size, 0x58, 0x48,
                       streaming, 0, num_segments, num_pages, 0,
                       num_pointers, num_assets, num_guid_refs, num_deps,
                       num_external, external_size)
        raise ValueError(f"unsupported RPak version {version}")


@dataclass(slots=True)
class SegmentHeader:
    flags: int
    align: int
    size: int


@dataclass(slots=True)
class PageHeader:
    segment: int
    align: int
    size: int


@dataclass(slots=True)
class PagePtr:
    index: int
    offset: int


@dataclass(slots=True)
class PakAsset:
    guid: int
    head: PagePtr
    data: PagePtr
    starpak_offset: int
    opt_starpak_offset: int
    page_end: int
    remaining_dependencies: int
    dependents_index: int
    dependencies_index: int
    dependents_count: int
    dependencies_count: int
    header_struct_size: int
    version: int
    type_value: int
    ordinal: int

    @property
    def type_name(self) -> str:
        return fourcc(self.type_value)

    @property
    def starpak_index(self) -> int | None:
        if self.starpak_offset == -1:
            return None
        return self.starpak_offset & 0xFFF

    @property
    def starpak_data_offset(self) -> int | None:
        if self.starpak_offset == -1:
            return None
        return self.starpak_offset & 0xFFFFFFFFFFFFF000


@dataclass(slots=True)
class LayoutOffsets:
    header_end: int
    segment_headers: int
    page_headers: int
    pointer_headers: int
    assets: int
    guid_refs: int
    dependencies: int
    external_ref_offsets: int
    external_refs: int
    unknown_data: int
    patch_stream: int
    page_data: int


def compute_layout(data: bytes, header: RpakHeader) -> LayoutOffsets:
    off = header.header_size
    if header.patch_count:
        if len(data) < off + 8:
            raise ValueError("truncated patch metadata")
        patch_stream_size, patch_page_count = struct.unpack_from("<ii", data, off)
        off += 8
        off += 16 * header.patch_count
        off += 2 * header.patch_count
    else:
        patch_stream_size = 0
    header_end = off
    off += header.streaming_files_size + header.opt_streaming_files_size
    seg = off
    off += 0x10 * header.num_segments
    pages = off
    off += 0x0C * header.num_pages
    ptrs = off
    off += 0x08 * header.num_pointers
    assets = off
    off += header.asset_size * header.num_assets
    guid_refs = off
    off += 0x08 * header.num_guid_refs
    deps = off
    off += 4 * header.num_dependencies
    ext_offsets = off
    off += 4 * header.num_external_refs
    ext_refs = off
    off += header.external_refs_size
    unknown = off
    off += header.unk_74 + header.unk_78
    patch_stream = off
    off += patch_stream_size
    return LayoutOffsets(header_end, seg, pages, ptrs, assets, guid_refs, deps,
                         ext_offsets, ext_refs, unknown, patch_stream, off)


def parse_segments(data: bytes, header: RpakHeader, layout: LayoutOffsets) -> list[SegmentHeader]:
    out: list[SegmentHeader] = []
    for i in range(header.num_segments):
        flags, align, size = struct.unpack_from("<IIq", data, layout.segment_headers + i * 0x10)
        out.append(SegmentHeader(flags, align, size))
    return out


def parse_pages(data: bytes, header: RpakHeader, layout: LayoutOffsets) -> list[PageHeader]:
    out: list[PageHeader] = []
    for i in range(header.num_pages):
        segment, align, size = struct.unpack_from("<iiI", data, layout.page_headers + i * 0x0C)
        out.append(PageHeader(segment, align, size))
    return out


def parse_assets(data: bytes, header: RpakHeader, layout: LayoutOffsets) -> list[PakAsset]:
    out: list[PakAsset] = []
    for i in range(header.num_assets):
        off = layout.assets + i * header.asset_size
        if header.version >= 8:
            guid = struct.unpack_from("<Q", data, off)[0]
            head_i, head_o, data_i, data_o = struct.unpack_from("<iiii", data, off + 0x10)
            star, opt_star = struct.unpack_from("<qq", data, off + 0x20)
            page_end, remaining = struct.unpack_from("<HH", data, off + 0x30)
            dependents_index, dependencies_index, dependents_count = struct.unpack_from("<IIi", data, off + 0x34)
            dependencies_count = struct.unpack_from("<H", data, off + 0x40)[0]
            header_struct_size = struct.unpack_from("<I", data, off + 0x44)[0]
            version = data[off + 0x48]
            type_value = struct.unpack_from("<I", data, off + 0x4C)[0]
        else:
            guid = struct.unpack_from("<Q", data, off)[0]
            head_i, head_o, data_i, data_o = struct.unpack_from("<iiii", data, off + 0x10)
            star = struct.unpack_from("<q", data, off + 0x20)[0]
            opt_star = -1
            page_end, remaining = struct.unpack_from("<HH", data, off + 0x28)
            dependents_index, dependencies_index, dependents_count, dependencies_count = struct.unpack_from("<IIii", data, off + 0x2C)
            header_struct_size, version, type_value = struct.unpack_from("<IiI", data, off + 0x3C)
        out.append(PakAsset(guid, PagePtr(head_i, head_o), PagePtr(data_i, data_o), star, opt_star,
                            page_end, remaining, dependents_index, dependencies_index,
                            dependents_count, int(dependencies_count), header_struct_size,
                            int(version), type_value, i))
    return out
