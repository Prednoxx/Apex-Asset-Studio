from __future__ import annotations

import mmap
import os
import re
from dataclasses import dataclass
from pathlib import Path
from threading import Event

from .rtech import OodleRuntime, decompress_rtech_payload
from .oodle_stream import decompress_stream, frame_stream, ScanCancelled
from .structures import (
    FLAG_OODLE, FLAG_RTECH, FLAG_ZSTD, LayoutOffsets, PakAsset, PageHeader,
    RpakHeader, compute_layout, parse_assets, parse_pages, parse_segments,
)


@dataclass(slots=True)
class ArchiveIndex:
    path: Path
    header: RpakHeader
    layout: LayoutOffsets | None
    assets: list[PakAsset]
    pages: list[PageHeader]
    strings: list[str]
    error: str | None = None


class RpakArchive:
    def __init__(self, path: str | os.PathLike[str], game_root: str | os.PathLike[str] | None = None):
        self.path = Path(path)
        self.game_root = Path(game_root) if game_root else self.path.parent
        self.raw: bytes | None = None
        self.data: bytes | None = None
        self.header: RpakHeader | None = None
        self.layout: LayoutOffsets | None = None
        self.assets: list[PakAsset] = []
        self.pages: list[PageHeader] = []
        self.segments = []

    def read_header(self) -> RpakHeader:
        with self.path.open("rb") as f:
            raw = f.read(0x80)
        self.header = RpakHeader.parse(raw)
        return self.header

    def materialize(self, stop_event: Event | None = None) -> bytes:
        raw = self.path.read_bytes()
        self.raw = raw
        header = RpakHeader.parse(raw[:0x80])
        self.header = header
        if not header.compressed:
            if len(raw) < header.dcmp_size:
                raise ValueError('truncated uncompressed RPak')
            # Signatures outside declared extent
            data = raw[:header.dcmp_size]
        elif header.flags & FLAG_RTECH:
            data = decompress_rtech_payload(raw, header.header_size, header.cmp_size, header.dcmp_size)
        elif header.flags & FLAG_OODLE:
            runtime = OodleRuntime(self.game_root)
            if not runtime.available:
                raise RuntimeError(f"RPak uses Oodle but no compatible decoder is available: {runtime.description}")
            if header.cmp_size < header.header_size or header.cmp_size > len(raw):
                raise ValueError("invalid compressed RPak extent")
            # Zero-copy compressed input view
            compressed = memoryview(raw)[header.header_size:header.cmp_size]
            data = decompress_stream(compressed, header.dcmp_size - header.header_size, runtime, stop_event,
                                     prefix=raw[:header.header_size])
            compressed.release()
        elif header.flags & FLAG_ZSTD:
            raise RuntimeError("ZSTD-compressed RPaks are detected but not implemented in this test build")
        else:
            raise RuntimeError(f"unknown RPak compression flags {header.flags:#x}")
        if len(data) != header.dcmp_size:
            raise ValueError(f"RPak decoded size mismatch: {len(data)} != {header.dcmp_size}")
        self.data = data
        self.raw = None
        self.layout = compute_layout(data, header)
        self.segments = parse_segments(data, header, self.layout)
        self.pages = parse_pages(data, header, self.layout)
        self.assets = parse_assets(data, header, self.layout)
        return data

    def materialize_to(self, destination, stop_event: Event | None = None) -> RpakHeader:
        """Stream decompressed package to disk."""
        header = self.read_header()
        if not header.compressed or header.flags & FLAG_RTECH or not header.flags & FLAG_OODLE:
            data = self.materialize(stop_event)
            Path(destination).write_bytes(data)
            self.data = None
            return header
        runtime = OodleRuntime(self.game_root)
        if not runtime.available:
            raise RuntimeError(f"RPak uses Oodle but no compatible decoder is available: {runtime.description}")
        raw_size = header.dcmp_size - header.header_size
        with self.path.open('rb') as source, mmap.mmap(source.fileno(), 0, access=mmap.ACCESS_READ) as raw:
            if header.cmp_size < header.header_size or header.cmp_size > len(raw):
                raise ValueError("invalid compressed RPak extent")
            view = memoryview(raw)[header.header_size:header.cmp_size]
            try:
                spans = frame_stream(view, raw_size)
                written = 0
                with open(destination, 'wb') as out:
                    out.write(raw[:header.header_size])
                    for span in spans:
                        if stop_event is not None and stop_event.is_set():
                            raise ScanCancelled()
                        decoded = runtime.decompress(bytes(view[span.start:span.end]), span.raw_size)
                        if len(decoded) != span.raw_size:
                            raise ValueError("Oodle restart span returned an incorrect size")
                        out.write(decoded); written += len(decoded)
            finally:
                view.release()
        if written != raw_size:
            raise ValueError(f"RPak decoded size mismatch: {written + header.header_size} != {header.dcmp_size}")
        return header

    def index(self, mine_strings: bool = True, stop_event: Event | None = None) -> ArchiveIndex:
        try:
            data = self.materialize(stop_event)
            strings = self.mine_asset_strings(data) if mine_strings else []
            return ArchiveIndex(self.path, self.header, self.layout, self.assets, self.pages, strings)
        except ScanCancelled:
            raise
        except Exception as exc:
            if self.header is None:
                try:
                    self.read_header()
                except Exception:
                    pass
            return ArchiveIndex(self.path, self.header, None, [], [], [], f"{type(exc).__name__}: {exc}")

    @staticmethod
    def mine_asset_strings(data: bytes, limit: int = 20000) -> list[str]:
        pattern = re.compile(rb"[A-Za-z0-9_./\\()\-]{8,260}\x00")
        prefixes = (
            b"mdl/", b"model/", b"material/", b"texture/", b"settings/", b"ui/",
            b"anim/", b"weapons/", b"characters/", b"paks/", b"scripts/", b"shaders/",
        )
        suffixes = (b".rpak", b".starpak", b".rmdl", b".rseq", b".dds", b".png")
        out: list[str] = []
        seen = set()
        for match in pattern.finditer(data):
            raw = match.group(0)[:-1]
            low = raw.lower().replace(b"\\", b"/")
            if not (low.startswith(prefixes) or low.endswith(suffixes)):
                continue
            try:
                text = raw.decode("utf-8", errors="strict").replace("\\", "/")
            except UnicodeDecodeError:
                continue
            if text in seen:
                continue
            seen.add(text)
            out.append(text)
            if len(out) >= limit:
                break
        return out
