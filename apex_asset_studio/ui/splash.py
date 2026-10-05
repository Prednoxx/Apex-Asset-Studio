"""Startup splash: the user's artwork beside a quiet wordmark and a slim progress line."""
import time
import tkinter as tk
from pathlib import Path
from PIL import Image, ImageTk

from . import appearance

STAGES = 5  # number of stage() calls made during startup, for the progress line


class StartupSplash(tk.Toplevel):
    def __init__(self, app, colors=None, logo_path=None, version=''):
        super().__init__(app)
        self.started = time.monotonic(); self._closed = False; self._step = 0
        c = appearance.tokens(colors or appearance.PRESETS[appearance.DEFAULT_PRESET])
        f = appearance.fonts(app)
        self.overrideredirect(True)
        width, height = 760, 420
        self.geometry(f'{width}x{height}+{max(0,(self.winfo_screenwidth()-width)//2)}+{max(0,(self.winfo_screenheight()-height)//2)}')
        self.configure(background=c['border'])
        canvas = tk.Canvas(self, width=width-2, height=height-2, background=c['surface'], highlightthickness=0)
        canvas.place(x=1, y=1); self.canvas = canvas
        art_w = 290
        canvas.create_rectangle(0, 0, art_w, height, fill=c['background'], outline='')
        canvas.create_line(art_w, 0, art_w, height, fill=c['border'])
        path = Path(logo_path) if logo_path else Path(__file__).resolve().parents[1]/'resources'/'asuka.webp'
        try:
            with Image.open(path) as image:
                image = image.convert('RGBA'); image.thumbnail((art_w-40, height-40), Image.Resampling.LANCZOS)
                self.art = ImageTk.PhotoImage(image)
            canvas.create_image(art_w//2, height//2, image=self.art)
        except (OSError, ValueError):
            pass
        x = art_w + 44
        canvas.create_rectangle(x, 92, x+28, 95, fill=c['accent'], outline='')
        canvas.create_text(x, 112, text='APEX LEGENDS', anchor='nw', fill=c['muted'], font=f['section'])
        canvas.create_text(x-2, 130, text='Asset Studio', anchor='nw', fill=c['text'], font=f['display'])
        canvas.create_text(x, 186, text=f'Models, materials and animations · v{version}' if version else
                           'Models, materials and animations', anchor='nw', fill=c['muted'], font=f['small'])
        bar_y = height - 70; self._bar = (x, bar_y, width - 48)
        canvas.create_rectangle(x, bar_y, width-48, bar_y+2, fill=c['raised'], outline='')
        self._fill = canvas.create_rectangle(x, bar_y, x, bar_y+2, fill=c['accent'], outline='')
        self.status = canvas.create_text(x, bar_y+14, text='Starting…', anchor='nw', fill=c['muted'],
                                         font=f['small'], width=width-x-48)
        self.lift(); self.update()

    def stage(self, message):
        if self._closed: return
        self._step += 1
        x0, y, x1 = self._bar
        self.canvas.coords(self._fill, x0, y, x0+(x1-x0)*min(1, self._step/STAGES), y+2)
        self.canvas.itemconfigure(self.status, text=message); self.update()

    def finish(self, app):
        self.stage('Ready')
        # Keep quick startups readable without claiming background work is running.
        delay = max(0, int((1.2-(time.monotonic()-self.started))*1000))
        def reveal():
            if self._closed: return
            self._closed = True; self.destroy(); app.deiconify(); app.lift()
        app.after(delay, reveal)
