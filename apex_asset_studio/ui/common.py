"""Small helpers shared by the app's pages: names, error wording, folder helpers and sortable tables."""
import os
import re
import subprocess
from pathlib import Path

from .. import __version__ as APP_VERSION

APP_NAME = 'Apex Asset Studio'
LOG_HINT = 'Details are in Advanced › Diagnostics.'

FRIENDLY_ERRORS = (
    ('is not supported', "This uses a game format the app can't read yet."),
    ('unsupported', "This uses a game format the app can't read yet."),
    ('ambiguous across', 'This item exists in more than one game package, so the right one is unclear.'),
    ('no resolvable base RPak', "This item's game package wasn't found. Try scanning the library again."),
    ('Material set unavailable', "This skin's materials can't be read yet, so it can't be exported."),
    ('Permission', 'Windows blocked access to a file. Close anything using the export folder and try again.'),
    ('No space', 'The drive is full.'),
    ('FileExistsError', 'An export with this name already exists.'),
)


def friendly_error(text):
    """Plain-language summary for the status bar; the technical text still goes to the diagnostics log."""
    for needle, message in FRIENDLY_ERRORS:
        if needle.lower() in text.lower(): return message
    return f'Something went wrong. {LOG_HINT}'


SHORTCUTS = (('Ctrl+F', 'Search the library'), ('Ctrl+1 … 3', 'Switch page'), ('Space', 'Play / pause animation'),
             ('R', 'Reset 3D view'), ('Ctrl+E', 'Export model'), ('Ctrl+Shift+E', 'Export animation'),
             ('F5', 'Scan library'), ('Ctrl + / − / 0', 'Text size bigger / smaller / normal'))

RARITY_ORDER = {'common': 0, 'rare': 1, 'epic': 2, 'legendary': 3, 'mythic': 4, 'iconic': 4, 'heirloom': 5}


def _sort_key(column, value):
    text = str(value)
    if column == 'quality' and text.lower() in RARITY_ORDER: return (0, RARITY_ORDER[text.lower()], '')
    season = re.fullmatch(r'S(\d+)', text)
    if season: return (0, int(season.group(1)), '')
    try: return (0, float(text.replace(',', '')), '')
    except ValueError: return (1, 0, text.casefold())


def sort_tree(tree, column, reverse=False):
    """Sort a table by one column. Empty cells ('' or '—') always go last, whichever direction."""
    rows = [(tree.set(iid, column), iid) for iid in tree.get_children('')]
    filled = sorted([(_sort_key(column, v), iid) for v, iid in rows if v not in ('', '—')], reverse=reverse)
    blank = [(None, iid) for v, iid in rows if v in ('', '—')]
    for index, (_k, iid) in enumerate(filled + blank): tree.move(iid, '', index)
    tree._sort = (column, reverse)
    titles = getattr(tree, '_titles', None)
    if titles is None:  # sorted before make_sortable ran: take the headings as they are, minus any arrow
        titles = tree._titles = {col: str(tree.heading(col, 'text')).removesuffix(' ▲').removesuffix(' ▼') for col in tree['columns']}
    for col in tree['columns']:
        tree.heading(col, text=titles.get(col, col) + ((' ▼' if reverse else ' ▲') if col == column else ''))


def make_sortable(tree):
    """Click a column heading to sort by it; click again to reverse. Numbers, seasons and rarities sort naturally."""
    tree._sort = getattr(tree, '_sort', None)
    if getattr(tree, '_titles', None) is None: tree._titles = {col: tree.heading(col, 'text') for col in tree['columns']}
    def click(column):
        sort_tree(tree, column, reverse=tree._sort == (column, False))
        if hasattr(tree, 'on_sort'): tree.on_sort(column, tree._sort[1])
    for col in tree['columns']: tree.heading(col, command=lambda c=col: click(c))


def open_folder(folder):
    folder = Path(folder); folder.mkdir(parents=True, exist_ok=True)
    if os.name == 'nt': os.startfile(folder)
    else: subprocess.Popen(['xdg-open', str(folder)])


def folder_size(folder):
    total = 0
    for root, _dirs, files in os.walk(folder):
        for name in files:
            try: total += os.path.getsize(os.path.join(root, name))
            except OSError: pass
    return total


def gb(size):
    return f'{size / 1024**3:.1f} GB' if size >= 1024**3 else f'{size / 1024**2:.0f} MB'


def asset_lines(row):
    """Technical metadata lines for one indexed asset."""
    return [
        f"Type:              {row['type']}",
        f"GUID:              {row['guid']}",
        f"Asset version:     {row['version']}",
        f"Header size:       {row['header_size']}",
        f"Container:         {row['filename']}",
        f"Container path:    {row['path']}",
        f"Compression:       {row['compression']}",
        f"Patch count:       {row['patch_count']}",
        f"StarPak offset:    {row['starpak_offset'] or '(none)'}",
        f"StarPak index:     {row['starpak_index'] if row['starpak_index'] is not None else '(none)'}",
        f"Opt StarPak:       {row['opt_starpak_offset'] or '(none)'}",
    ]


class ScanEta:
    """Time-left estimate for the library scan. Uses the pace of the last few dozen packages (skipped, unchanged
    packages are fast, new ones slow, so a whole-run average would be wrong) and smooths the result so the text
    doesn't jump around. Returns None until there is enough to go on."""
    WINDOW = 40

    def __init__(self, clock=None):
        import time
        self.clock = clock or time.monotonic
        self.started = self.clock(); self.samples = []; self.smoothed = None

    def update(self, current, total):
        now = self.clock()
        self.samples.append((now, current)); self.samples = self.samples[-self.WINDOW:]
        if now - self.started < 10 or len(self.samples) < 8 or current >= total: return None
        (t0, c0), (t1, c1) = self.samples[0], self.samples[-1]
        if c1 <= c0 or t1 <= t0: return None
        remaining = (total - current) * (t1 - t0) / (c1 - c0)
        self.smoothed = remaining if self.smoothed is None else self.smoothed * .8 + remaining * .2
        return self.smoothed

    @staticmethod
    def describe(seconds):
        if seconds is None: return ''
        minutes = round(seconds / 60)
        if seconds < 50: return 'less than a minute left'
        if minutes < 60: return f'about {max(1, minutes)} min left'
        hours, minutes = divmod(minutes, 60)
        return f'about {hours} h {minutes} min left' if minutes else f'about {hours} h left'
