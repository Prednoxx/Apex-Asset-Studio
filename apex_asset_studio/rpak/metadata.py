from __future__ import annotations
import struct
from .pages import PageReader
from .settings import SettingsDecoder, decode_localization
from .animation_metadata import decode_animation_header


def decode_archive_metadata(archive, stop_event=None):
    try:
        reader = PageReader(archive)
    except ValueError as exc:
        return [{"name": None, "status": "unresolved", "error": str(exc), "details": {}, "dependencies": []}
                for _ in archive.assets]
    decoder = SettingsDecoder(reader)
    decoder.register_layouts(archive.assets)
    result = []
    for i, asset in enumerate(archive.assets):
        if stop_event is not None and i % 256 == 0 and stop_event.is_set():
            from .oodle_stream import ScanCancelled
            raise ScanCancelled()
        item = {"name": None, "status": "header_only", "error": None, "details": {}, "dependencies": []}
        try:
            p = reader.header(asset)
            b = reader.data
            item["dependencies"] = reader.dependencies(asset)
            kind = asset.type_name
            if kind == "stgs":
                item["name"] = reader.string(reader.pointer(p + 16))
                item["details"] = decoder.decode(asset)
                item["status"] = "settings_decoded"
            elif kind == "stlt":
                item["name"] = reader.string(reader.pointer(p))
                if asset.guid in decoder.errors:
                    raise ValueError(decoder.errors[asset.guid])
                item["status"] = "layout_decoded"
            elif kind == "locl":
                item["details"] = decode_localization(reader, asset)
                item["name"] = item["details"]["name"]
                item["status"] = "localization_decoded"
            elif kind == "odlp" and (asset.version, asset.header_struct_size) == (1, 24):
                item["name"] = reader.string(reader.pointer(p))
                item["details"] = {"pak_name": item["name"]}
                item["status"] = "on_demand_package_decoded"
            elif kind == "odla" and (asset.version, asset.header_struct_size) == (2, 40):
                item["name"] = reader.string(reader.pointer(p + 8))
                item["details"] = {"pak_guid": f"{struct.unpack_from('<Q', b, p)[0]:016X}",
                                   "original_guid": f"{struct.unpack_from('<Q', b, p + 24)[0]:016X}",
                                   "placeholder_guid": f"{struct.unpack_from('<Q', b, p + 32)[0]:016X}"}
                item["status"] = "on_demand_asset_decoded"
            elif kind == "mdl_" and asset.version in (16, 17, 18, 19, 20) and asset.header_struct_size == 96:
                item["name"] = reader.string(reader.pointer(p + 8))
                count = struct.unpack_from("<I", b, p + 40)[0]
                rigs = reader.pointer(p + 32, count * 8, nullable=True)
                item["details"] = {"animation_rigs": [f"{struct.unpack_from('<Q', b, rigs + j * 8)[0]:016X}" for j in range(count)] if rigs is not None else [],
                                   "geometry_status": "not_decoded"}
                item["status"] = "model_header_decoded"
            elif kind == "matl" and asset.version == 23 and asset.header_struct_size in (192, 200, 256):
                item["name"] = reader.string(reader.pointer(p + 24))
                item["status"] = "material_header_decoded"
            elif kind in ('arig','aseq'):
                item['name'],item['details'] = decode_animation_header(reader,asset)
                item['status'] = 'animation_header_decoded'
        except (ValueError, struct.error, UnicodeError) as exc:
            item["error"] = str(exc)
            item["status"] = "unresolved"
        result.append(item)
    return result
