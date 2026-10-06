"""Startup splash: the theme's backdrop art, the mascot, and one frosted glass card with the app name, the current
step and a progress bar. Nothing else."""
import time
import tkinter as tk
import tkinter.font
from pathlib import Path
from PIL import Image, ImageFilter, ImageTk

from . import appearance, gloss

STAGES = 5  # number of stage() calls made during startup


def _art(path, size):
    with Image.open(path) as image:
        art = image.convert('RGBA'); art.thumbnail(size, Image.Resampling.LANCZOS)
    return art


class StartupSplash(tk.Toplevel):
    def __init__(self, app, colors=None, logo_path=None, version=''):
        super().__init__(app)
        self.started = time.monotonic(); self._closed = False; self._step = 0
        t = self.t = appearance.tokens(colors or appearance.style()['colors'])
        f = appearance.fonts(app); m = appearance.fx()
        self.overrideredirect(True)
        width, height = 820, 460
        self.geometry(f'{width}x{height}+{max(0,(self.winfo_screenwidth()-width)//2)}+{max(0,(self.winfo_screenheight()-height)//2)}')
        self.configure(background=t['border'])
        W, H = width - 2, height - 2
        c = self.canvas = tk.Canvas(self, width=W, height=H, background=t['background'], highlightthickness=0)
        c.place(x=1, y=1)
        light = t['light']
        bg = gloss.backdrop(m['backdrop'], (W, H), t, base=t['background'], energy=1.0)
        path = Path(logo_path) if logo_path else Path(__file__).resolve().parents[1]/'resources'/'asuka.webp'
        try:
            art = _art(path, (int(W * .48), H))
            halo = Image.new('RGBA', art.size, gloss.rgb('#ffffff' if light else t['accent'], 0))
            halo.putalpha(art.getchannel('A').point(lambda v: int(v * .55)))
            ax = W - art.width - 10; ay = H - art.height + 6
            bg.alpha_composite(halo.filter(ImageFilter.GaussianBlur(18)), (ax, ay)); bg.alpha_composite(art, (ax, ay))
        except (OSError, ValueError):
            pass
        title_font = (f['display'][0], max(22, f['display'][1] - 6))
        card = (34, H - 176, 34 + max(380, tk.font.Font(font=title_font).measure('Apex Asset Studio') + 52), H - 34)
        bg = gloss.glass(bg, card, '#ffffff' if light else t['background'], radius=18, tint_alpha=120 if light else 110)
        self._bgimg = ImageTk.PhotoImage(bg)
        c.create_image(0, 0, image=self._bgimg, anchor='nw')
        x0, y0, x1, y1 = card
        c.create_text(x0 + 24, y0 + 30, text='Apex Asset Studio', anchor='w', fill=t['text'], font=title_font)
        c.create_text(x1 - 24, y0 + 74, text=f'v{version}', anchor='e', fill=t['muted'], font=f['small'])
        self.status = c.create_text(x0 + 24, y0 + 74, text='Starting…', anchor='w', fill=t['muted'], font=f['body'])
        self._bar = (x0 + 24, y0 + 98, x1 - 24, 14)
        self._radius = 7 if m['radius'] is None or m['radius'] >= 4 else 2
        self._bar_track = ImageTk.PhotoImage(gloss.pill(self._bar[2] - self._bar[0], self._bar[3], t['raised'], 'pressed',
                                                        radius=self._radius, dark=not light, shine=m['shine']))
        c.create_image(self._bar[0], self._bar[1], image=self._bar_track, anchor='nw')
        self._bar_item = None
        self.lift(); self.update()

    def _progress(self, fraction):
        x0, y, x1, h = self._bar
        width = max(h, int((x1 - x0) * fraction))
        self._bar_fill = ImageTk.PhotoImage(gloss.pill(width, h, self.t['accent'], 'normal', radius=self._radius,
                                                       dark=not self.t['light'], shine=appearance.fx()['shine']))
        if self._bar_item: self.canvas.delete(self._bar_item)
        self._bar_item = self.canvas.create_image(x0, y, image=self._bar_fill, anchor='nw')

    def stage(self, message):
        if self._closed: return
        self._step += 1
        self._progress(min(1, self._step / STAGES))
        self.canvas.itemconfigure(self.status, text=message)
        self.update()

    def finish(self, app):
        self.stage('Ready')
        delay = max(0, int((0.35-(time.monotonic()-self.started))*1000))  # just long enough to read 'Ready'
        def reveal():
            if self._closed: return
            self._closed = True; self.destroy(); app.deiconify(); app.lift()
        app.after(delay, reveal)
