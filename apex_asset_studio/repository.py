"""On-demand asset access with a bounded, memory-mapped decoded archive cache."""
import hashlib
import mmap
import os
import json
import re
import sqlite3
import struct
from pathlib import Path
from .rpak.archive import RpakArchive
from .rpak.structures import RpakHeader, compute_layout, parse_segments, parse_pages, parse_assets
from .rpak.patch import reconstruct


def default_cache_dir():
    return Path(os.environ.get('LOCALAPPDATA', Path.home())) / 'ApexAssetStudio' / 'decoded_cache'


# Parsed package tables (pages, assets…) by decoded-cache file. The file name is a hash of the source package's
# path, size and date, so the same name always means the same contents; parsing common.rpak's tables takes a
# noticeable moment, so it happens once per app run instead of once per model load, preview and export.
_TABLES = {}

# The app sets these from the user's Storage settings; every repository uses them unless told otherwise.
SETTINGS = {'cache_dir': None, 'cache_budget': 12 * 1024**3}


def cache_files(folder):
    """Decoded-package cache entries (data files plus their provenance JSON) in a cache folder."""
    folder = Path(folder)
    if not folder.is_dir(): return []
    return [p for p in folder.iterdir() if p.is_file() and (p.suffix in ('.decoded', '.tmp') or p.name.endswith('.patched.json'))]


class AssetRepository:
    def __init__(self, catalog, root, cache=None, stop_event=None, cache_budget=None):
        self.catalog = catalog
        self.root = Path(root).resolve()
        self.cache = Path(cache) if cache else Path(SETTINGS['cache_dir'] or default_cache_dir())
        cache_budget = cache_budget if cache_budget is not None else SETTINGS['cache_budget']
        self.cache.mkdir(parents=True, exist_ok=True)
        self.opened = {}
        self.raw_opened = {}
        self.handles = []
        self.warnings = set()
        self.stop_event = stop_event
        self.cache_budget = cache_budget
        self.used_cache = set()
        self._db = None  # one catalog connection for the repository's lifetime (opening one per lookup is slow)

    def open(self, path):
        path = Path(path).resolve()
        if path in self.opened: return self.opened[path]
        archive = self._open_raw(path)
        if not archive.header.patch_count:
            self.opened[path] = archive
            return archive
        parents = []
        count = archive.header.patch_count
        indices = struct.unpack_from(f'<{count}H',archive.data,archive.header.header_size+8+16*count)
        stem = re.sub(r'\(\d+\)$','',path.stem)
        for i,index in enumerate(indices):
            filename = stem + (f'({index:02})' if index else '') + '.rpak'
            parent_path = path.with_name(filename)
            if parent_path == path: raise ValueError('self-referencing patch source')
            parent = self._open_raw(parent_path)
            cmp_size,dcmp_size = struct.unpack_from('<QQ',archive.data,archive.header.header_size+8+i*16)
            if (parent.header.cmp_size,parent.header.dcmp_size) != (cmp_size,dcmp_size):
                raise ValueError('patch parent sizes do not match the declared source version')
            parents.append(parent)
        identity = '|'.join(f'{p.path}|{p.path.stat().st_size}|{p.path.stat().st_mtime_ns}' for p in [archive,*parents])
        key = hashlib.sha256(identity.encode()).hexdigest()
        cached = self.cache/f'{key}.patched.decoded'
        provenance_path = cached.with_suffix('.json')
        expected = archive.layout.page_data + sum(p.size for p in archive.pages)
        if not cached.exists() or cached.stat().st_size != expected or not provenance_path.exists():
            temp = cached.with_suffix('.tmp')
            provenance = reconstruct(archive,parents,temp,self.stop_event)
            temp.replace(cached)
            provenance_path.write_text(json.dumps(provenance,indent=2),encoding='utf-8')
        expanded = self._map_archive(path,cached)
        expanded.pages_reconstructed = True
        expanded.patch_provenance = json.loads(provenance_path.read_text(encoding='utf-8'))
        self.opened[path] = expanded
        return expanded

    def _open_raw(self,path):
        path = Path(path).resolve()
        if not path.is_relative_to(self.root): raise ValueError('RPak outside selected game installation')
        if path in self.raw_opened: return self.raw_opened[path]
        stat = path.stat()
        key = hashlib.sha256(f'{path}|{stat.st_size}|{stat.st_mtime_ns}'.encode()).hexdigest()
        cached = self.cache / f'{key}.rpak.decoded'
        archive = RpakArchive(path, self.root)
        source_header = archive.read_header()
        valid_cache = cached.exists() and cached.stat().st_size == source_header.dcmp_size
        if valid_cache:
            with path.open('rb') as source, cached.open('rb') as decoded:
                valid_cache = source.read(source_header.header_size) == decoded.read(source_header.header_size)
        if not valid_cache:
            temp = cached.with_suffix('.tmp')
            try:
                archive.materialize_to(temp, self.stop_event)  # streamed to disk, never fully in memory
            except BaseException:
                temp.unlink(missing_ok=True); raise
            temp.replace(cached)
        archive = self._map_archive(path,cached)
        self.raw_opened[path] = archive
        return archive

    def _map_archive(self,path,cached):
        archive = RpakArchive(path,self.root)
        f = cached.open('rb')
        mapping = mmap.mmap(f.fileno(), 0, access=mmap.ACCESS_READ)
        self.used_cache.add(cached)
        cached.touch()
        self.handles.extend([f, mapping])
        archive.data = mapping
        key = (cached.name, len(mapping))
        tables = _TABLES.get(key)
        if tables is None:
            header = RpakHeader.parse(mapping[:128]); layout = compute_layout(mapping, header)
            assets = parse_assets(mapping, header, layout)
            by_guid = {}
            for asset in assets: by_guid.setdefault(asset.guid, []).append(asset)
            tables = (header, layout, parse_segments(mapping, header, layout), parse_pages(mapping, header, layout), assets, by_guid)
            if len(_TABLES) >= 32: _TABLES.pop(next(iter(_TABLES)))
            _TABLES[key] = tables
        archive.header, archive.layout, archive.segments, archive.pages, archive.assets, archive.by_guid = tables
        return archive

    def asset(self, guid, preferred=None):
        guid = guid.upper()
        if self._db is None:
            self._db = sqlite3.connect(self.catalog.db_path, timeout=60, check_same_thread=False); self._db.row_factory = sqlite3.Row
        rows = self._db.execute('''SELECT c.path,c.patch_count,a.type FROM assets a JOIN containers c ON c.id=a.container_id
            WHERE a.guid=? AND c.status='ok' ORDER BY c.patch_count,c.filename''', (guid,)).fetchall()
        paths = list(dict.fromkeys(r['path'] for r in rows))
        # Later numbered packages are preferred only within the same declared chain.
        chains = {}
        for path in paths:
            p = Path(path)
            stem = re.sub(r'\(\d+\)$','',p.stem)
            chains.setdefault((p.parent,stem),[]).append(path)
        chosen = []
        for key,chain in chains.items():
            def generation(p):
                m=re.search(r'\((\d+)\)$',Path(p).stem)
                return int(m.group(1)) if m else 0
            chosen.append(max(chain,key=generation))
        paths = chosen
        if preferred:
            pp=Path(preferred);pref_stem=re.sub(r'\(\d+\)$','',pp.stem)
            preferred = next((p for p in paths if Path(p).parent==pp.parent and re.sub(r'\(\d+\)$','',Path(p).stem)==pref_stem),preferred)
        match = next((p for p in paths if preferred and Path(p) == Path(preferred)),None)
        if match:
            paths.remove(match); paths.insert(0, match)
        if not paths: raise ValueError(f'GUID {guid} has no resolvable base RPak payload')
        # Prefer the caller's dependency package; otherwise refuse competing base copies.
        if len(paths) > 1 and not match:
            raise ValueError(f'GUID {guid} is ambiguous across {len(paths)} base RPaks')
        archive = self.open(paths[0])
        matches = archive.by_guid.get(int(guid, 16), [])
        if len(matches) != 1: raise ValueError(f'GUID {guid} not uniquely present in source RPak')
        return archive, matches[0]

    def close(self):
        if self._db is not None: self._db.close(); self._db = None
        self.opened.clear()
        self.raw_opened.clear()
        for handle in reversed(self.handles): handle.close()
        self.handles.clear()
        # Evict only our decoded cache files, after releasing mmap handles. Another
        # running repository's Windows mapping prevents deletion and is skipped.
        files = list(self.cache.glob('*.decoded'))
        records = []
        for path in files:
            try: records.append((path.stat().st_mtime,path.stat().st_size,path))
            except OSError: pass
        total = sum(size for _,size,_ in records)
        for _,size,path in sorted(records):
            if total <= self.cache_budget: break
            if path in self.used_cache: continue
            try:
                path.unlink()
                path.with_suffix('.json').unlink(missing_ok=True)
                total -= size
            except OSError: pass

    def __enter__(self): return self
    def __exit__(self, *_): self.close()
