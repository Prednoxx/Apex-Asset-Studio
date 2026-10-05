"""Typed STGS/STLT and LOCL decoding. Unknown schemas fail visibly."""
from __future__ import annotations
import struct
from dataclasses import dataclass
from .pages import PageReader


@dataclass
class SettingsLayout:
    name: str | None
    stride: int
    count: int
    fields: list[dict]
    children: dict[int, "SettingsLayout"]


class SettingsDecoder:
    def __init__(self, reader: PageReader):
        self.reader = reader
        self.data = reader.data
        self.layouts = {}
        self.errors = {}

    def layout(self, pos: int, depth: int = 0) -> SettingsLayout:
        if depth > 16:
            raise ValueError("settings layout recursion limit")
        r, b = self.reader, self.data
        name = r.string(r.pointer(pos, nullable=True))
        bucket_count, field_count = struct.unpack_from("<II", b, pos + 24)
        count, stride = struct.unpack_from("<iI", b, pos + 44)
        if bucket_count > 65536 or field_count > bucket_count or stride > 16 * 1024 * 1024:
            raise ValueError("invalid settings layout dimensions")
        fields_pos = r.pointer(pos + 8, bucket_count * 8)
        strings = r.pointer(pos + 56)
        children_pos = r.pointer(pos + 64, nullable=True)
        fields = []
        child_indexes = set()
        for i in range(bucket_count):
            kind, name_offset, packed = struct.unpack_from("<HHI", b, fields_pos + i * 8)
            if not name_offset:
                continue
            if kind > 9:
                raise ValueError(f"unsupported settings field type {kind}")
            offset, child_index = packed & 0xFFFFFF, packed >> 24
            fields.append({"name": r.string(strings + name_offset), "kind": kind,
                           "offset": offset, "child": child_index})
            if kind in (8, 9):
                child_indexes.add(child_index)
        if len(fields) != field_count:
            raise ValueError("settings layout field count mismatch")
        children = {}
        for i in child_indexes:
            if children_pos is None:
                raise ValueError("array field has no sublayout")
            children[i] = self.layout(children_pos + i * 72, depth + 1)
        return SettingsLayout(name, stride, count, sorted(fields, key=lambda f: f["offset"]), children)

    def register_layouts(self, assets):
        for asset in assets:
            if asset.type_name != "stlt":
                continue
            try:
                if asset.version != 0 or asset.header_struct_size != 72:
                    raise ValueError(f"unsupported settings layout version {asset.version}")
                self.layouts[asset.guid] = self.layout(self.reader.header(asset))
            except (ValueError, struct.error, UnicodeError) as exc:
                self.errors[asset.guid] = str(exc)

    def values(self, layout: SettingsLayout, pos: int, end: int, depth: int = 0) -> dict:
        if depth > 16:
            raise ValueError("settings value recursion limit")
        result = {}
        b = self.data
        widths = (1, 4, 4, 8, 12, 8, 8, 8, 0, 8)
        for field in layout.fields:
            at = pos + field["offset"]
            kind = field["kind"]
            if at < pos or at + widths[kind] > end:
                raise ValueError(f"settings field {field['name']} outside value buffer")
            if kind == 0:
                value = bool(b[at])
            elif kind in (1, 2, 3, 4):
                fmt = {1: "<i", 2: "<f", 3: "<2f", 4: "<3f"}[kind]
                value = struct.unpack_from(fmt, b, at)
                value = value[0] if len(value) == 1 else list(value)
            elif kind in (5, 6, 7):
                value = self.reader.string(self.reader.pointer(at, nullable=True)) or ""
            else:
                child = layout.children[field["child"]]
                count, array_pos = child.count, at
                if kind == 9:
                    count, delta = struct.unpack_from("<ii", b, at)
                    array_pos = pos + delta
                if count < 0 or count > 100000 or array_pos < pos or array_pos + count * child.stride > end:
                    raise ValueError(f"invalid array {field['name']}")
                value = [self.values(child, array_pos + i * child.stride, end, depth + 1) for i in range(count)]
            result[field["name"]] = value
        return result

    def decode(self, asset) -> dict:
        if (asset.version, asset.header_struct_size) not in ((1, 72), (2, 80)):
            raise ValueError(f"unsupported settings version {asset.version}/{asset.header_struct_size}")
        pos = self.reader.header(asset)
        layout_guid = struct.unpack_from("<Q", self.data, pos)[0]
        layout = self.layouts.get(layout_guid)
        if layout is None:
            raise ValueError(f"settings layout {layout_guid:016X} unresolved: {self.errors.get(layout_guid, 'not in this package')}")
        size = struct.unpack_from("<I", self.data, pos + (64 if asset.version == 2 else 56))[0]
        value_pos = self.reader.pointer(pos + 8, size)
        return {"layout_guid": f"{layout_guid:016X}", "layout_name": layout.name,
                "unique_id": struct.unpack_from("<I", self.data, pos + (40 if asset.version == 2 else 32))[0],
                "values": self.values(layout, value_pos, value_pos + size)}


def decode_localization(reader: PageReader, asset) -> dict:
    if asset.version != 1 or asset.header_struct_size != 56:
        raise ValueError("unsupported localization schema")
    pos = reader.header(asset)
    count = struct.unpack_from("<Q", reader.data, pos + 16)[0]
    if count > 1000000:
        raise ValueError("invalid localization entry count")
    entries = reader.pointer(pos + 24, count * 16)
    strings = reader.pointer(pos + 32)
    result = {}
    for i in range(count):
        guid, index = struct.unpack_from("<Qi", reader.data, entries + i * 16)
        if not guid:
            continue
        if index < 0:
            raise ValueError("negative localization string index")
        result[f"{guid:016X}"] = reader.string(strings + index * 2, 32768, utf16=True)
    return {"name": reader.string(reader.pointer(pos)), "entries": result}
