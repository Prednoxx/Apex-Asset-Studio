"""Startup splash: boot-sequence screen with the user's artwork split into neon channels."""
import time
import tkinter as tk
from pathlib import Path
from PIL import Image, ImageChops, ImageDraw, ImageTk

from . import appearance

STAGES = 5  # number of stage() calls made during startup


def _neon_art(path, size, t):
    """Artwork with a chromatic split (secondary neon left, primary neon right) and scanlines."""
    with Image.open(path) as image:
        art = image.convert('RGBA'); art.thumbnail(size, Image.Resampling.LANCZOS)
    w, h = art.size; pad = 10
    out = Image.new('RGBA', (w + pad*2, h), (0, 0, 0, 0))
    alpha = art.getchannel('A').point(lambda v: int(v * .55))
    for dx, color in ((-6, t['accent2']), (6, t['accent'])):
        ghost = Image.new('RGBA', art.size, (*appearance._rgb(color), 0)); ghost.putalpha(alpha)
        out.alpha_composite(ghost, (pad + dx, 0))
    out.alpha_composite(art, (pad, 0))
    lines = Image.new('RGBA', out.size, (0, 0, 0, 0)); d = ImageDraw.Draw(lines)
    for y in range(0, h, 3): d.line([(0, y), (out.width, y)], fill=(0, 0, 0, 70))
    lines.putalpha(ImageChops.multiply(lines.getchannel('A'), out.getchannel('A')))
    out.alpha_composite(lines)
    return out


class StartupSplash(tk.Toplevel):
    def __init__(self, app, colors=None, logo_path=None, version=''):
        super().__init__(app)
        self.started = time.monotonic(); self._closed = False; self._step = 0
        t = self.t = appearance.tokens(colors or appearance.PRESETS[appearance.DEFAULT_PRESET])
        f = self.f = appearance.fonts(app)
        self.overrideredirect(True)
        width, height = 820, 460
        self.geometry(f'{width}x{height}+{max(0,(self.winfo_screenwidth()-width)//2)}+{max(0,(self.winfo_screenheight()-height)//2)}')
        self.configure(background=t['accent'])
        c = tk.Canvas(self, width=width-2, height=height-2, background=t['background'], highlightthickness=0)
        c.place(x=1, y=1); self.canvas = c
        W, H = width-2, height-2

        grid = appearance.mix(t['border'], t['background'], .45)
        for gx in range(0, W, 28): c.create_line(gx, 0, gx, H, fill=grid)
        for gy in range(0, H, 28): c.create_line(0, gy, W, gy, fill=grid)
        c.create_text(W - 20, H - 70, text='素材工房', anchor='se', fill=appearance.mix(t['accent'], t['background'], .14),
                      font=(f['jp_big'][0], 64, 'bold'))
        for y0 in (0, H - 8):
            c.create_rectangle(0, y0, W, y0 + 8, fill=t['background'], outline='')
            for hx in range(-10, W + 10, 16):
                c.create_polygon(hx, y0 + 8, hx + 8, y0, hx + 14, y0, hx + 6, y0 + 8, fill=t['accent'], outline='')

        path = Path(logo_path) if logo_path else Path(__file__).resolve().parents[1]/'resources'/'asuka.webp'
        try:
            self.art = ImageTk.PhotoImage(_neon_art(path, (290, H - 40), t))
            c.create_image(170, H // 2 + 4, image=self.art)
        except (OSError, ValueError):
            pass

        x = 350
        c.create_text(x, 40, text='SYS.BOOT  //  起動シーケンス', anchor='nw', fill=t['accent2'], font=f['mono_small'])
        for dx, dy, color in ((-3, 0, t['accent2']), (3, 1, t['accent']), (0, 0, t['text'])):
            c.create_text(x + dx, 58 + dy, text='APEX ASSET', anchor='nw', fill=color, font=f['display'])
            c.create_text(x + dx, 108 + dy, text='STUDIO', anchor='nw', fill=color, font=f['display'])
        c.create_text(x + 2, 170, text=f'MODEL // MATERIAL // ANIMATION   BUILD {version}', anchor='nw',
                      fill=t['muted'], font=f['mono_small'])

        self._log_x, self._log_y = x, 206
        self._lines = []
        self._segments = []
        seg_w, gap, sy = 14, 4, H - 56
        for i in range(24):
            sx = x + i * (seg_w + gap)
            self._segments.append(c.create_polygon(sx + 3, sy, sx + seg_w + 3, sy, sx + seg_w, sy + 10, sx, sy + 10,
                                                   fill=t['raised'], outline=''))
        self.status = c.create_text(x, sy - 22, text='INITIALIZING…', anchor='nw', fill=t['accent'], font=f['mono'])
        self.lift(); self.update()

    def stage(self, message):
        if self._closed: return
        t, f, c = self.t, self.f, self.canvas
        if self._lines:
            c.itemconfigure(self._lines[-1][1], text='OK', fill=t['accent2'])
        self._step += 1
        y = self._log_y + len(self._lines) * 18
        label = message.rstrip('…').upper()
        line = c.create_text(self._log_x, y, text=f'> {label} ' + '.' * max(2, 30 - len(label)), anchor='nw',
                             fill=t['muted'], font=f['mono'])
        state = c.create_text(self._log_x + 300, y, text='…', anchor='nw', fill=t['warn'], font=f['mono'])
        self._lines.append((line, state))
        filled = round(len(self._segments) * min(1, self._step / STAGES))
        for i, seg in enumerate(self._segments):
            c.itemconfigure(seg, fill=t['accent'] if i < filled else t['raised'])
        c.itemconfigure(self.status, text='SYSTEM READY  //  準備完了' if message == 'Ready' else 'LOADING  //  読み込み中')
        self.update()

    def finish(self, app):
        self.stage('Ready')
        if self._lines: self.canvas.itemconfigure(self._lines[-1][1], text='GO', fill=self.t['accent'])
        self.update()
        delay = max(0, int((1.4-(time.monotonic()-self.started))*1000))
        def reveal():
            if self._closed: return
            self._closed = True; self.destroy(); app.deiconify(); app.lift()
        app.after(delay, reveal)
