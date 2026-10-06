from __future__ import annotations

import os
import json
import sqlite3
import threading
import time
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from .game_locator import find_pak_root
from .rpak.archive import RpakArchive
from .rpak.metadata import decode_archive_metadata
from .rpak.oodle_stream import ScanCancelled
from .cosmetics import rebuild_cosmetics
from .repository import AssetRepository


INDEX_VERSION = "3"
PAYLOAD_VERSION = 2

SCHEMA = """
PRAGMA journal_mode=WAL;
CREATE TABLE IF NOT EXISTS meta (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS containers (
    id INTEGER PRIMARY KEY,
    path TEXT UNIQUE NOT NULL,
    filename TEXT NOT NULL,
    version INTEGER,
    flags INTEGER,
    compression TEXT,
    crc TEXT,
    cmp_size INTEGER,
    dcmp_size INTEGER,
    patch_count INTEGER,
    asset_count INTEGER,
    status TEXT,
    error TEXT,
    mtime REAL
);
CREATE TABLE IF NOT EXISTS assets (
    id INTEGER PRIMARY KEY,
    container_id INTEGER NOT NULL,
    ordinal INTEGER NOT NULL,
    guid TEXT NOT NULL,
    type TEXT NOT NULL,
    version INTEGER,
    header_size INTEGER,
    starpak_offset TEXT,
    starpak_index INTEGER,
    opt_starpak_offset TEXT,
    UNIQUE(container_id, ordinal)
);
CREATE INDEX IF NOT EXISTS idx_assets_type ON assets(type);
CREATE INDEX IF NOT EXISTS idx_assets_guid ON assets(guid);
CREATE TABLE IF NOT EXISTS strings (
    id INTEGER PRIMARY KEY,
    container_id INTEGER NOT NULL,
    value TEXT NOT NULL,
    value_lc TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_strings_lc ON strings(value_lc);
CREATE TABLE IF NOT EXISTS asset_details (
    asset_id INTEGER PRIMARY KEY, name TEXT, status TEXT NOT NULL, error TEXT, details TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_asset_names ON asset_details(name);
CREATE TABLE IF NOT EXISTS asset_dependencies (
    asset_id INTEGER NOT NULL, guid TEXT NOT NULL, page INTEGER, offset INTEGER, reference_index INTEGER
);
CREATE INDEX IF NOT EXISTS idx_dependencies_asset ON asset_dependencies(asset_id);
CREATE INDEX IF NOT EXISTS idx_dependencies_guid ON asset_dependencies(guid);
CREATE TABLE IF NOT EXISTS cosmetics (
    id INTEGER PRIMARY KEY, category TEXT NOT NULL, owner_guid TEXT NOT NULL, owner_name TEXT NOT NULL,
    skin_guid TEXT NOT NULL, name TEXT NOT NULL, quality TEXT, details TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_cosmetics_owner ON cosmetics(owner_guid);
CREATE TABLE IF NOT EXISTS animation_links (
    sequence_guid TEXT NOT NULL, target_guid TEXT NOT NULL, kind TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_animation_links_target ON animation_links(target_guid, kind);
"""


# These are raw asset-type groupings only. Human-readable character/skin groupings are
# deliberately *not* inferred from filenames. They should only appear after a real
# itemflav/localization resolver can substantiate them.
SIMPLE_TYPE_GROUPS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("Models", ("mdl_",)),
    ("Animations", ("aseq", "arig")),
    ("Materials", ("matl",)),
    ("Textures", ("txtr",)),
    ("UI Images", ("uiia",)),
)


def _purge_container(db, cid):
    """Remove every indexed row that belongs to one container (the container row itself is kept)."""
    db.execute("DELETE FROM asset_details WHERE asset_id IN (SELECT id FROM assets WHERE container_id=?)", (cid,))
    db.execute("DELETE FROM asset_dependencies WHERE asset_id IN (SELECT id FROM assets WHERE container_id=?)", (cid,))
    db.execute("DELETE FROM assets WHERE container_id=?", (cid,))
    db.execute("DELETE FROM strings WHERE container_id=?", (cid,))


@dataclass(slots=True)
class ScanStats:
    containers_seen: int = 0
    containers_ok: int = 0
    containers_failed: int = 0
    containers_skipped: int = 0
    assets: int = 0
    strings: int = 0
    stopped: bool = False


class Catalog:
    def __init__(self, db_path: str | os.PathLike[str]):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        with self.connect() as db:
            db.executescript(SCHEMA)
            if 'payload_version' not in {r[1] for r in db.execute('PRAGMA table_info(containers)')}:
                db.execute('ALTER TABLE containers ADD COLUMN payload_version INTEGER NOT NULL DEFAULT 0')
            row = db.execute("SELECT value FROM meta WHERE key='index_version'").fetchone()
            self._index_outdated = row is None or row[0] != INDEX_VERSION

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.db_path, timeout=60)
        db.row_factory = sqlite3.Row
        try:
            with db:
                yield db
        finally:
            db.close()

    @property
    def index_outdated(self) -> bool:
        return self._index_outdated

    def clear(self):
        with self.connect() as db:
            db.execute("DELETE FROM cosmetics")
            db.execute("DELETE FROM asset_details")
            db.execute("DELETE FROM asset_dependencies")
            db.execute("DELETE FROM assets")
            db.execute("DELETE FROM strings")
            db.execute("DELETE FROM containers")
            db.execute("DELETE FROM meta WHERE key='index_version'")
        self._index_outdated = True

    def scan_game(
        self,
        game_root: str | os.PathLike[str],
        progress: Callable[[str, int, int], None] | None = None,
        stop_event: threading.Event | None = None,
    ) -> ScanStats:
        """Update the index from the installed game.

        Successful unchanged RPaks are skipped. Failed RPaks are always retried so a decoder
        fix immediately repairs the index without forcing users through a destructive rebuild.
        """
        pak_root = find_pak_root(game_root)
        rpaks = sorted(pak_root.rglob("*.rpak"))
        stats = ScanStats()
        total = len(rpaks)

        with self.connect() as db:
            existing = {} if self._index_outdated else {
                row["path"]: (row["mtime"], row["status"],row['payload_version'])
                for row in db.execute("SELECT path,mtime,status,payload_version FROM containers")
            }

            for idx, path in enumerate(rpaks, 1):
                if stop_event and stop_event.is_set():
                    stats.stopped = True
                    break

                stats.containers_seen += 1
                try:
                    mtime = path.stat().st_mtime
                except OSError:
                    mtime = 0

                prior = existing.get(str(path))
                payload_only = bool(prior and prior[1] == 'ok' and prior[0] == mtime)
                if prior and prior[1] == "ok" and prior[0] == mtime and prior[2] == PAYLOAD_VERSION:
                    stats.containers_skipped += 1
                    if progress:
                        progress(f"Up to date: {path.name}", idx, total)
                    continue

                if progress:
                    progress(f"Scanning {path.name}", idx, total)

                try:
                    if prior and prior[1] == 'ok' and prior[0] == mtime:
                        with AssetRepository(self,game_root,stop_event=stop_event) as repository:
                            archive = repository.open(path)
                            decoded = decode_archive_metadata(archive,stop_event)
                            cid = db.execute('SELECT id FROM containers WHERE path=?',(str(path),)).fetchone()[0]
                            old_rows = db.execute('SELECT id,ordinal,guid FROM assets WHERE container_id=?',(cid,)).fetchall()
                            by_ordinal = {r['ordinal']:r for r in old_rows}
                            if len(old_rows) != len(archive.assets): raise ValueError('cached raw index no longer matches RPak asset count')
                            db.execute('DELETE FROM asset_dependencies WHERE asset_id IN (SELECT id FROM assets WHERE container_id=?)',(cid,))
                            for asset,detail in zip(archive.assets,decoded):
                                old = by_ordinal.get(asset.ordinal)
                                if old is None or old['guid'] != f'{asset.guid:016X}': raise ValueError('cached GUID table differs from RPak')
                                aid = old['id']
                                db.execute('''INSERT INTO asset_details(asset_id,name,status,error,details) VALUES(?,?,?,?,?)
                                    ON CONFLICT(asset_id) DO UPDATE SET name=excluded.name,status=excluded.status,error=excluded.error,details=excluded.details''',
                                    (aid,detail['name'],detail['status'],detail['error'],json.dumps(detail['details'],ensure_ascii=False)))
                                db.executemany('INSERT INTO asset_dependencies(asset_id,guid,page,offset,reference_index) VALUES(?,?,?,?,?)',
                                    [(aid,d['guid'],d['page'],d['offset'],d['reference_index']) for d in detail['dependencies']])
                            db.execute('UPDATE containers SET payload_version=?,error=NULL WHERE id=?',(PAYLOAD_VERSION,cid))
                        stats.containers_ok += 1
                        if idx % 8 == 0: db.commit()
                        continue
                    archive = RpakArchive(path, game_root)
                    index = archive.index(mine_strings=True, stop_event=stop_event)
                    if index.error is None and archive.header.patch_count:
                        with AssetRepository(self,game_root,stop_event=stop_event) as repository:
                            expanded = repository.open(path)
                            decoded = decode_archive_metadata(expanded,stop_event)
                    else:
                        decoded = decode_archive_metadata(archive, stop_event) if index.error is None else []
                    hdr = index.header
                    if hdr is None:
                        raise RuntimeError(index.error or "unable to read RPak header")

                    status = "ok" if index.error is None else "error"
                    db.execute(
                        """INSERT INTO containers(path,filename,version,flags,compression,crc,cmp_size,dcmp_size,patch_count,asset_count,status,error,mtime)
                           VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)
                           ON CONFLICT(path) DO UPDATE SET filename=excluded.filename,version=excluded.version,flags=excluded.flags,
                           compression=excluded.compression,crc=excluded.crc,cmp_size=excluded.cmp_size,dcmp_size=excluded.dcmp_size,
                           patch_count=excluded.patch_count,asset_count=excluded.asset_count,status=excluded.status,error=excluded.error,mtime=excluded.mtime
                        """,
                        (
                            str(path), path.name, hdr.version, hdr.flags, hdr.compression,
                            f"{hdr.crc:016X}", hdr.cmp_size, hdr.dcmp_size, hdr.patch_count,
                            hdr.num_assets, status, index.error, mtime,
                        ),
                    )
                    row = db.execute("SELECT id FROM containers WHERE path=?", (str(path),)).fetchone()
                    cid = row[0]
                    db.execute('UPDATE containers SET payload_version=? WHERE id=?',(PAYLOAD_VERSION if index.error is None else 0,cid))
                    _purge_container(db, cid)

                    if index.error is None:
                        for a, detail in zip(index.assets, decoded):
                            cursor = db.execute(
                                """INSERT INTO assets(container_id,ordinal,guid,type,version,header_size,starpak_offset,starpak_index,opt_starpak_offset)
                                   VALUES(?,?,?,?,?,?,?,?,?)""",
                                (
                                    cid, a.ordinal, f"{a.guid:016X}", a.type_name,
                                    a.version, a.header_struct_size,
                                    None if a.starpak_offset == -1 else f"{a.starpak_offset & 0xFFFFFFFFFFFFFFFF:016X}",
                                    a.starpak_index,
                                    None if a.opt_starpak_offset == -1 else f"{a.opt_starpak_offset & 0xFFFFFFFFFFFFFFFF:016X}",
                                ),
                            )
                            aid = cursor.lastrowid
                            db.execute("INSERT INTO asset_details(asset_id,name,status,error,details) VALUES(?,?,?,?,?)",
                                       (aid, detail['name'], detail['status'], detail['error'], json.dumps(detail['details'], ensure_ascii=False)))
                            db.executemany("INSERT INTO asset_dependencies(asset_id,guid,page,offset,reference_index) VALUES(?,?,?,?,?)",
                                           [(aid, dep['guid'], dep['page'], dep['offset'], dep['reference_index']) for dep in detail['dependencies']])
                        for s in index.strings:
                            db.execute(
                                "INSERT INTO strings(container_id,value,value_lc) VALUES(?,?,?)",
                                (cid, s, s.lower()),
                            )
                        stats.containers_ok += 1
                        stats.assets += len(index.assets)
                        stats.strings += len(index.strings)
                    else:
                        stats.containers_failed += 1

                    if idx % 8 == 0:
                        db.commit()

                except ScanCancelled:
                    stats.stopped = True
                    break
                except Exception as exc:
                    stats.containers_failed += 1
                    if payload_only:
                        message = f'Typed payload refresh failed: {type(exc).__name__}: {exc}'
                        cid = db.execute('SELECT id FROM containers WHERE path=?',(str(path),)).fetchone()[0]
                        db.execute('DELETE FROM asset_dependencies WHERE asset_id IN (SELECT id FROM assets WHERE container_id=?)',(cid,))
                        db.execute("UPDATE asset_details SET name=NULL,status='unresolved',error=?,details='{}' WHERE asset_id IN (SELECT id FROM assets WHERE container_id=?)",(message,cid))
                        db.execute('UPDATE containers SET payload_version=0,error=? WHERE id=?',(message,cid))
                        continue
                    old = db.execute("SELECT id FROM containers WHERE path=?", (str(path),)).fetchone()
                    if old:
                        cid = old[0]
                        _purge_container(db, cid)
                    db.execute(
                        """INSERT INTO containers(path,filename,status,error,mtime)
                           VALUES(?,?,?,?,?)
                           ON CONFLICT(path) DO UPDATE SET status=excluded.status,error=excluded.error,mtime=excluded.mtime""",
                        (
                            str(path), path.name, "error", f"{type(exc).__name__}: {exc}",
                            mtime,
                        ),
                    )

            if not stats.stopped:
                # Never leave vanished packages or assets from a different install in the current library.
                present = {str(p) for p in rpaks}
                for old in db.execute("SELECT id,path FROM containers").fetchall():
                    if old['path'] not in present:
                        cid = old['id']
                        _purge_container(db, cid)
                        db.execute("DELETE FROM containers WHERE id=?", (cid,))
                if progress:
                    progress("Resolving cosmetic names and on-demand model packages…", total, total)
                rebuild_cosmetics(db)
                if progress:
                    progress("Linking animations to models…", total, total)
                db.execute("INSERT INTO meta(key,value) VALUES('index_stamp',?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                           (str(time.time()),))
                self._rebuild_animation_links(db)
                db.execute(
                    "INSERT INTO meta(key,value) VALUES('index_version',?) "
                    "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                    (INDEX_VERSION,),
                )
                self._index_outdated = False
            db.commit()

        return stats

    def summary(self) -> dict:
        with self.connect() as db:
            c = db.execute(
                "SELECT COUNT(*), SUM(CASE WHEN status='ok' THEN 1 ELSE 0 END), "
                "SUM(CASE WHEN status='error' THEN 1 ELSE 0 END) FROM containers"
            ).fetchone()
            a = db.execute("SELECT COUNT(*) FROM assets").fetchone()[0]
            s = db.execute("SELECT COUNT(*) FROM strings").fetchone()[0]
            cosmetics = db.execute("SELECT COUNT(*) FROM cosmetics").fetchone()[0]
            dependencies = db.execute("SELECT COUNT(*) FROM asset_dependencies").fetchone()[0]
            unresolved = db.execute("SELECT COUNT(*) FROM asset_details WHERE status='unresolved'").fetchone()[0]
            payload_pending = db.execute('SELECT COUNT(*) FROM containers WHERE payload_version<>?',(PAYLOAD_VERSION,)).fetchone()[0]
            types = db.execute(
                "SELECT type,COUNT(*) n FROM assets GROUP BY type ORDER BY n DESC LIMIT 50"
            ).fetchall()
        return {
            "containers": c[0] or 0,
            "ok": c[1] or 0,
            "failed": c[2] or 0,
            "assets": a,
            "strings": s,
            "cosmetics": cosmetics, "dependencies": dependencies, "unresolved": unresolved,
            "payload_pending": payload_pending,
            "types": [(r[0], r[1]) for r in types],
        }

    def simple_sections(self) -> list[dict]:
        """Return only sections supported by real indexed asset rows."""
        with self.connect() as db:
            counts = {r["type"]: r["n"] for r in db.execute(
                "SELECT type,COUNT(*) n FROM assets GROUP BY type"
            )}
        sections = []
        for label, types in SIMPLE_TYPE_GROUPS:
            count = sum(counts.get(t, 0) for t in types)
            if count:
                sections.append({"label": label, "types": types, "count": count})
        return sections

    # ---- search ---------------------------------------------------------------------------------
    # Searches stream rows and stop at the page size, and counts stop at COUNT_CAP, so common terms return
    # instantly and rare ones cost one pass over the table. The UI runs them off the main thread.
    # (A trigram full-text index was measured: it added ~250 MB per million assets and was slower for common
    # terms, so it isn't used.)
    COUNT_CAP = 10000

    @staticmethod
    def _asset_filter(text, asset_type):
        clauses, args = [], []
        text = (text or '').strip().lower()
        if text:
            clauses.append("instr(lower(a.guid || ' ' || a.type || ' ' || c.filename || ' ' || coalesce(d.name, '')), ?) > 0")
            args.append(text)
        if asset_type:
            clauses.append("a.type=?"); args.append(asset_type)
        return ("WHERE " + " AND ".join(clauses)) if clauses else "", args

    def search_assets(self, text: str = "", asset_type: str | None = None, limit: int = 1000, offset: int = 0):
        where, args = self._asset_filter(text, asset_type)
        sql = f"""SELECT a.id,a.container_id,a.guid,a.type,a.version,a.header_size,a.starpak_offset,a.starpak_index,
                         a.opt_starpak_offset,a.ordinal,c.filename,c.path,c.patch_count,c.compression,c.status,
                         d.name,d.status decode_status,d.error decode_error
                  FROM assets a JOIN containers c ON c.id=a.container_id LEFT JOIN asset_details d ON d.asset_id=a.id {where}
                  ORDER BY a.id LIMIT ? OFFSET ?"""
        with self.connect() as db:
            return db.execute(sql, [*args, limit, offset]).fetchall()

    def count_assets(self, text: str = "", asset_type: str | None = None) -> int:
        """Number of matches, stopping at COUNT_CAP + 1 (show as "10,000+")."""
        where, args = self._asset_filter(text, asset_type)
        with self.connect() as db:
            return db.execute(f"""SELECT COUNT(*) FROM (SELECT 1 FROM assets a JOIN containers c ON c.id=a.container_id
                                  LEFT JOIN asset_details d ON d.asset_id=a.id {where} LIMIT ?)""", [*args, self.COUNT_CAP + 1]).fetchone()[0]

    def get_asset(self, asset_id: int):
        with self.connect() as db:
            return db.execute(
                """SELECT a.id,a.container_id,a.guid,a.type,a.version,a.header_size,a.starpak_offset,a.starpak_index,
                          a.opt_starpak_offset,a.ordinal,c.filename,c.path,c.patch_count,c.compression,c.status,c.error,
                          d.name,d.status decode_status,d.error decode_error,d.details
                   FROM assets a JOIN containers c ON c.id=a.container_id LEFT JOIN asset_details d ON d.asset_id=a.id WHERE a.id=?""",
                (asset_id,),
            ).fetchone()

    def cosmetic_owners(self):
        with self.connect() as db:
            return db.execute("SELECT category,owner_guid,owner_name,COUNT(*) count FROM cosmetics GROUP BY category,owner_guid,owner_name ORDER BY category,owner_name").fetchall()

    def search_cosmetics(self, text='', owner_guid=None, limit=3000):
        with self.connect() as db:
            return db.execute("""SELECT * FROM cosmetics WHERE (name LIKE ? OR owner_name LIKE ?)
                AND (? IS NULL OR owner_guid=?) ORDER BY owner_name,name LIMIT ?""",
                (f'%{text}%', f'%{text}%', owner_guid, owner_guid, limit)).fetchall()

    def settings_values(self, guid):
        """Decoded settings values of one settings asset (an item flavor), or {}."""
        with self.connect() as db:
            row = db.execute("""SELECT d.details FROM assets a JOIN asset_details d ON d.asset_id=a.id
                WHERE a.guid=? AND d.status='settings_decoded' LIMIT 1""", (guid,)).fetchone()
        try: return json.loads(row['details']).get('values', {}) if row else {}
        except (ValueError, TypeError): return {}

    def get_cosmetic(self, cosmetic_id):
        with self.connect() as db:
            return db.execute("SELECT * FROM cosmetics WHERE id=?", (cosmetic_id,)).fetchone()

    def dependencies(self, asset_id):
        with self.connect() as db:
            return db.execute("""SELECT e.*,a.id target_id,a.type,d.name,c.filename FROM asset_dependencies e
                LEFT JOIN assets a ON a.guid=e.guid LEFT JOIN asset_details d ON d.asset_id=a.id
                LEFT JOIN containers c ON c.id=a.container_id WHERE e.asset_id=? ORDER BY e.reference_index,c.filename""", (asset_id,)).fetchall()

    def _rebuild_animation_links(self, db):
        """Store which sequences each rig and model declares, so the Animations window doesn't have to parse
        every sequence header each time it opens."""
        db.execute('DELETE FROM animation_links')
        links = []
        for row in db.execute('''SELECT a.guid,a.type,d.details FROM assets a JOIN asset_details d ON d.asset_id=a.id
                WHERE a.type IN ('arig','aseq') AND d.status='animation_header_decoded' '''):
            details = json.loads(row['details'])
            if row['type'] == 'arig':
                links.extend((sequence, row['guid'], 'rig') for sequence in details.get('declared_sequences', []))
            else:
                links.extend((row['guid'], model, 'model') for model in details.get('declared_models', []))
        db.executemany('INSERT INTO animation_links(sequence_guid,target_guid,kind) VALUES(?,?,?)', links)
        stamp = db.execute("SELECT value FROM meta WHERE key='index_stamp'").fetchone()
        db.execute("INSERT INTO meta(key,value) VALUES('links_stamp',?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                   (stamp[0] if stamp else 'built',))

    def ensure_animation_links(self):
        """Build the animation link table once for libraries scanned before it existed (a few seconds, one time)."""
        with self._lock, self.connect() as db:
            built = db.execute("SELECT value FROM meta WHERE key='links_stamp'").fetchone()
            stamp = db.execute("SELECT value FROM meta WHERE key='index_stamp'").fetchone()
            if built is None or (stamp is not None and built[0] != stamp[0]):
                self._rebuild_animation_links(db)

    def declared_animations(self, model_guid, rig_guids):
        """Return exact typed links; this does not assert decoded tracks or retargetability."""
        self.ensure_animation_links()
        rig_guids = list(rig_guids)
        with self.connect() as db:
            sequence_rigs = {}
            if rig_guids:
                marks = ','.join('?' for _ in rig_guids)
                for row in db.execute(f"SELECT sequence_guid,target_guid FROM animation_links WHERE kind='rig' AND target_guid IN ({marks})", rig_guids):
                    sequence_rigs.setdefault(row['sequence_guid'], set()).add(row['target_guid'])
            direct = {r[0] for r in db.execute("SELECT sequence_guid FROM animation_links WHERE kind='model' AND target_guid=?", (model_guid,))}
            wanted = sorted(direct | set(sequence_rigs))
            rows = []
            for chunk in range(0, len(wanted), 500):
                part = wanted[chunk:chunk + 500]; marks = ','.join('?' for _ in part)
                rows += db.execute(f'''SELECT a.guid,d.name,d.details,c.filename,c.path FROM assets a
                    JOIN asset_details d ON d.asset_id=a.id JOIN containers c ON c.id=a.container_id
                    WHERE a.type='aseq' AND d.status='animation_header_decoded' AND a.guid IN ({marks})''', part).fetchall()
        rows.sort(key=lambda r: (r['name'] or '', r['filename']))
        return [dict(row, declared_model_link=row['guid'] in direct, declared_rig_links=sorted(sequence_rigs.get(row['guid'], [])),
                     track_status='not_decoded') for row in rows]

    def asset_types(self) -> list[str]:
        with self.connect() as db:
            return [r[0] for r in db.execute("SELECT DISTINCT type FROM assets ORDER BY type")]

    def search_strings(self, query: str, limit: int = 1000, offset: int = 0):
        q = query.strip().lower()
        if not q:
            return []
        with self.connect() as db:
            return db.execute(
                """SELECT s.id,s.value,c.filename,c.path,c.compression
                   FROM strings s JOIN containers c ON c.id=s.container_id
                   WHERE instr(s.value_lc, ?) > 0 ORDER BY s.id LIMIT ? OFFSET ?""",
                (q, limit, offset),
            ).fetchall()

    def failure_groups(self) -> list[sqlite3.Row]:
        with self.connect() as db:
            return db.execute(
                """SELECT COALESCE(compression,'Unknown') compression,
                          COALESCE(error,'Unknown error') error,
                          COUNT(*) n
                   FROM containers WHERE status='error' OR error IS NOT NULL
                   GROUP BY compression,error ORDER BY n DESC,error"""
            ).fetchall()

    def failed_containers(self, limit: int = 1000):
        with self.connect() as db:
            return db.execute(
                "SELECT filename,path,compression,patch_count,error FROM containers "
                "WHERE status='error' OR error IS NOT NULL ORDER BY filename LIMIT ?",
                (limit,),
            ).fetchall()
