from __future__ import annotations

import os
import re
from pathlib import Path


def _existing(paths):
    seen = set()
    out = []
    for p in paths:
        if not p:
            continue
        path = Path(p)
        try:
            path = path.resolve()
        except Exception:
            pass
        key = str(path).lower()
        if key in seen:
            continue
        seen.add(key)
        if path.exists():
            out.append(path)
    return out


def _steam_libraries() -> list[Path]:
    roots = []
    pf86 = os.environ.get("PROGRAMFILES(X86)")
    pf = os.environ.get("PROGRAMFILES")
    if pf86:
        roots.append(Path(pf86) / "Steam")
    if pf:
        roots.append(Path(pf) / "Steam")
    roots += [Path("C:/Steam"), Path("D:/Steam"), Path("E:/Steam")]
    libs = []
    for root in _existing(roots):
        libs.append(root)
        vdf = root / "steamapps" / "libraryfolders.vdf"
        if not vdf.exists():
            continue
        try:
            text = vdf.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        for match in re.finditer(r'"path"\s+"([^"]+)"', text):
            libs.append(Path(match.group(1).replace("\\\\", "\\")))
    return _existing(libs)


def find_apex_installations() -> list[Path]:
    candidates: list[Path] = []
    for lib in _steam_libraries():
        candidates.append(lib / "steamapps" / "common" / "Apex Legends")

    for drive in "CDEFGHIJ":
        candidates.extend([
            Path(f"{drive}:/Program Files/EA Games/Apex"),
            Path(f"{drive}:/Program Files/EA Games/Apex Legends"),
            Path(f"{drive}:/EA Games/Apex"),
            Path(f"{drive}:/EA Games/Apex Legends"),
            Path(f"{drive}:/Games/Apex"),
            Path(f"{drive}:/Games/Apex Legends"),
        ])
    env_hint = os.environ.get("APEX_LEGENDS_DIR")
    if env_hint:
        candidates.insert(0, Path(env_hint))

    valid = []
    for p in _existing(candidates):
        if (p / "r5apex.exe").exists() or (p / "paks" / "Win64").exists():
            valid.append(p)
    return valid


def find_pak_root(game_root: str | os.PathLike[str]) -> Path:
    root = Path(game_root)
    for rel in (Path("paks/Win64"), Path("paks"), Path("game/r2/paks/Win64")):
        candidate = root / rel
        if candidate.exists():
            return candidate
    return root
