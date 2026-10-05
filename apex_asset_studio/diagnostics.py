from __future__ import annotations

import argparse
import json
from pathlib import Path

from .game_locator import find_apex_installations
from .rpak.archive import RpakArchive
from .rpak.rtech import OodleRuntime


def diagnose_rpak(path: Path, game_root: Path | None = None) -> dict:
    root = game_root or path.parent
    arc = RpakArchive(path, root)
    idx = arc.index(mine_strings=True)
    hdr = idx.header
    return {
        "path": str(path),
        "error": idx.error,
        "oodle_backend": OodleRuntime(root).description,
        "header": None if hdr is None else {
            "version": hdr.version,
            "flags": hdr.flags,
            "compression": hdr.compression,
            "cmp_size": hdr.cmp_size,
            "dcmp_size": hdr.dcmp_size,
            "patch_count": hdr.patch_count,
            "num_assets": hdr.num_assets,
            "num_pages": hdr.num_pages,
        },
        "parsed_assets": len(idx.assets),
        "mined_strings": idx.strings[:100],
        "asset_types": _type_counts(idx.assets),
    }


def _type_counts(assets):
    out = {}
    for a in assets:
        out[a.type_name] = out.get(a.type_name, 0) + 1
    return dict(sorted(out.items(), key=lambda kv: (-kv[1], kv[0])))


def main(argv=None):
    p = argparse.ArgumentParser(prog="ApexAssetStudio Diagnostics")
    p.add_argument("rpak", nargs="?", help="specific .rpak to test")
    p.add_argument("--game", help="Apex installation root")
    p.add_argument("--out", default="ApexAssetStudio_Diagnostics.json")
    args = p.parse_args(argv)

    root = Path(args.game) if args.game else None
    if root is None:
        installs = find_apex_installations()
        root = installs[0] if installs else None

    if args.rpak:
        report = diagnose_rpak(Path(args.rpak), root)
    elif root:
        paks = sorted((root / "paks" / "Win64").glob("*.rpak"))
        sample = paks[0] if paks else None
        report = {
            "game": str(root),
            "oodle_backend": OodleRuntime(root).description,
            "sample": diagnose_rpak(sample, root) if sample else None,
        }
    else:
        report = {"error": "Apex installation not detected and no RPak supplied"}

    Path(args.out).write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
