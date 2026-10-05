"""Resolve registered streaming files beneath the selected game installation."""
from pathlib import Path
from .starpak import StarPakIndex


class StreamingReader:
    def __init__(self, archive):
        self.archive = archive
        self.indices = {}

    def read(self, asset, optional=False):
        a = self.archive
        value = asset.opt_starpak_offset if optional else asset.starpak_offset
        if value == -1:
            raise ValueError('asset has no registered streaming block')
        start = a.layout.header_end
        if optional:
            start += a.header.streaming_files_size
            size = a.header.opt_streaming_files_size
        else:
            size = a.header.streaming_files_size
        paths = [x.decode('utf-8').replace('\\', '/') for x in a.data[start:start + size].split(b'\0') if x]
        index = value & 0xfff
        if index >= len(paths):
            raise ValueError('streaming file index outside RPak file list')
        root = a.game_root.resolve()
        path = (root / paths[index]).resolve()
        if not path.is_relative_to(root):
            raise ValueError('streaming path escapes game installation')
        if path not in self.indices:
            self.indices[path] = StarPakIndex(path).parse()
        return self.indices[path].read(value & 0xfffffffffffff000)
