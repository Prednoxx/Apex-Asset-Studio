"""Pictures next to skins in the Library list.

Two sources, best first:
1. Skin images you provide: any PNG/JPG/WebP in the "Skin images" folder named "<Legend or weapon> - <Skin>"
   (e.g. "Wraith - Airship Assassin.png") or "<Skin>" or the skin's GUID. Store cards and renders both work;
   they are cropped to the list's portrait shape.
2. Renders the app saves automatically the first time you open a skin (the textured model on a transparent
   background), so the list fills in as you browse.

Only rows that are on screen load their picture, so long lists stay fast. Mixed into the app."""
import re
from pathlib import Path

from PIL import Image, ImageTk

THUMB = (44, 55)  # list picture size (4:5 portrait, like store cards)
IMAGE_TYPES = ('.png', '.jpg', '.jpeg', '.webp')


def _key(text):
    return re.sub(r'[^0-9a-z]+', ' ', str(text).casefold()).strip()


class ThumbnailStore:
    def __init__(self, images_folder, rendered_folder):
        self.images_folder = Path(images_folder); self.rendered_folder = Path(rendered_folder)
        self._index = None; self._stamp = None

    def _scan(self):
        try: stamp = self.images_folder.stat().st_mtime_ns
        except OSError: stamp = None
        if self._index is not None and stamp == self._stamp: return self._index
        index = {}
        if stamp is not None:
            for path in self.images_folder.iterdir():
                if path.suffix.lower() in IMAGE_TYPES: index.setdefault(_key(path.stem), path)
        self._index, self._stamp = index, stamp
        return index

    def find(self, owner, name, skin_guid):
        index = self._scan()
        for key in (f'{owner} - {name}', f'{owner} {name}', skin_guid, name):
            path = index.get(_key(key))
            if path: return path, 'image'
        rendered = self.rendered_folder / f'{skin_guid}.png'
        return (rendered, 'render') if rendered.exists() else (None, None)

    def save_render(self, skin_guid, image):
        self.rendered_folder.mkdir(parents=True, exist_ok=True)
        image.save(self.rendered_folder / f'{skin_guid}.png')


def thumbnail(path, size=THUMB):
    """Cover-crop to the list's portrait shape, keeping the top (faces are at the top of store cards)."""
    with Image.open(path) as source:
        image = source.convert('RGBA')
    w, h = size; scale = max(w / image.width, h / image.height)
    image = image.resize((max(w, round(image.width * scale)), max(h, round(image.height * scale))), Image.Resampling.LANCZOS)
    left = (image.width - w) // 2
    return image.crop((left, 0, left + w, h))


class Thumbnails:
    def _init_thumbnails(self):
        base = self.appearance_path.parent
        folder = self.session.get('skin_images') or str(base / 'Skin images')
        self.thumbs = ThumbnailStore(folder, base / 'thumbnails')
        Path(folder).mkdir(parents=True, exist_ok=True)
        self._thumb_photos = {}; self._thumb_rows = {}; self._thumb_job = None

    def _thumbs_enabled(self):
        return bool(getattr(self, 'thumbs_var', None) and self.thumbs_var.get())

    def _apply_thumbnail_mode(self):
        """Show or hide the picture column (the tree column #0) and switch the row height."""
        on = self._thumbs_enabled(); tree = self.simple_assets
        self.session['thumbnails'] = on
        tree.configure(show='tree headings' if on else 'headings', style='Thumbs.Treeview' if on else 'Treeview')
        tree.column('#0', width=THUMB[0] + 14 if on else 0, minwidth=THUMB[0] + 14 if on else 0, stretch=False)
        self._schedule_thumbnails()

    def _remember_thumb_row(self, iid, cosmetic_row):
        self._thumb_rows[iid] = (cosmetic_row['owner_name'], cosmetic_row['name'], cosmetic_row['skin_guid'])

    def _schedule_thumbnails(self, *_):
        if self._thumb_job is None: self._thumb_job = self.after(60, self._load_visible_thumbnails)

    def _load_visible_thumbnails(self):
        """Give on-screen rows their picture (and drop pictures of rows far off screen)."""
        self._thumb_job = None
        tree = self.simple_assets
        if not self._thumbs_enabled(): return
        if not tree.winfo_ismapped():  # window not shown yet: try again shortly
            self._thumb_job = self.after(300, self._load_visible_thumbnails); return
        kids = tree.get_children('')
        if not kids: return
        start = max(0, int(tree.yview()[0] * len(kids)) - 1)
        visible = []
        for item in kids[start:start + 80]:
            box = tree.bbox(item)
            if box: visible.append(item)
            elif visible: break
        for iid in visible:
            if iid in self._thumb_photos or iid not in self._thumb_rows: continue
            path, _kind = self.thumbs.find(*self._thumb_rows[iid])
            if path is None: continue
            try:
                photo = ImageTk.PhotoImage(thumbnail(path), master=tree)
            except (OSError, ValueError):
                continue
            self._thumb_photos[iid] = photo
            if tree.exists(iid): tree.item(iid, image=photo)
        if len(self._thumb_photos) > 400:  # keep memory bounded on huge lists
            keep = set(visible)
            for iid in [i for i in self._thumb_photos if i not in keep][:len(self._thumb_photos) - 300]:
                if tree.exists(iid): tree.item(iid, image='')
                del self._thumb_photos[iid]

    def _clear_thumbnails(self):
        self._thumb_photos.clear(); self._thumb_rows.clear()

    def _capture_thumbnail(self, serial):
        """After a skin's textures are in, save a rendered picture if it has none yet."""
        cosmetic = self._cosmetic
        if serial != self._selection_serial or not cosmetic or not self._model: return
        path, _kind = self.thumbs.find(cosmetic['owner_name'], cosmetic['name'], cosmetic['skin_guid'])
        if path is not None: return
        image = self.preview.capture()
        if image is None: return
        try: self.thumbs.save_render(cosmetic['skin_guid'], image)
        except OSError: return
        iid = f"cosmetic:{cosmetic['id']}"
        self._thumb_photos.pop(iid, None); self._schedule_thumbnails()
