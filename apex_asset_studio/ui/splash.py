"""Startup splash: boot-sequence screen with the user's artwork split into neon channels."""
import time
import tkinter as tk
import tkinter.font
from pathlib import Path
from PIL import Image, ImageChops, ImageDraw, ImageTk

from . import appearance, cyber

STAGES = 5  # number of stage() calls made during startup


def _neon_art(path, size, t, split=True, scan=True):
    """Artwork with a chromatic split (secondary neon left, primary neon right) and scanlines."""
    with Image.open(path) as image:
        art = image.convert('RGBA'); art.thumbnail(size, Image.Resampling.LANCZOS)
    w, h = art.size; pad = 10
    out = Image.new('RGBA', (w + pad*2, h), (0, 0, 0, 0))
    alpha = art.getchannel('A').point(lambda v: int(v * .55))
    for dx, color in (((-6, t['accent2']), (6, t['accent'])) if split else ((8, t['accent']),)):
        ghost = Image.new('RGBA', art.size, (*appearance._rgb(color), 0)); ghost.putalpha(alpha)
        out.alpha_composite(ghost, (pad + dx, 0))
    out.alpha_composite(art, (pad, 0))
    if not scan: return out
    lines = Image.new('RGBA', out.size, (0, 0, 0, 0)); d = ImageDraw.Draw(lines)
    for y in range(0, h, 3): d.line([(0, y), (out.width, y)], fill=(0, 0, 0, 70))
    lines.putalpha(ImageChops.multiply(lines.getchannel('A'), out.getchannel('A')))
    out.alpha_composite(lines)
    return out


def _plain_art(path, size):
    with Image.open(path) as image:
        art = image.convert('RGBA'); art.thumbnail(size, Image.Resampling.LANCZOS)
    return art


class StartupSplash(tk.Toplevel):
    def __init__(self, app, colors=None, logo_path=None, version=''):
        super().__init__(app)
        self.started = time.monotonic(); self._closed = False; self._step = 0
        t = self.t = appearance.tokens(colors or appearance.style()['colors'])
        f = self.f = appearance.fonts(app)
        self.overrideredirect(True)
        width, height = 820, 460
        self.geometry(f'{width}x{height}+{max(0,(self.winfo_screenwidth()-width)//2)}+{max(0,(self.winfo_screenheight()-height)//2)}')
        self.configure(background=t['accent'])
        c = tk.Canvas(self, width=width-2, height=height-2, background=t['background'], highlightthickness=0)
        c.place(x=1, y=1); self.canvas = c
        W, H = width-2, height-2

        fx = appearance.fx(); self.promo = bool(fx.get('promo')); self.aero = bool(fx.get('gloss'))
        if self.aero:
            self._build_aero(c, W, H, t, f, logo_path, version); self.lift(); self.update(); return
        if self.promo:
            self._build_promo(c, W, H, t, f, logo_path, version); self.lift(); self.update(); return
        grid = appearance.mix(t['border'], t['background'], .45)
        if not fx.get('art_slab'):
            for gx in range(0, W, 28): c.create_line(gx, 0, gx, H, fill=grid)
            for gy in range(0, H, 28): c.create_line(0, gy, W, gy, fill=grid)
        if fx.get('show_jp', True): c.create_text(W - 20, H - 70, text='素材工房', anchor='se', fill=appearance.mix(t['accent'], t['background'], .14),
                      font=(f['jp_big'][0], 64, 'bold'))
        for y0 in (0, H - 10):
            c.create_rectangle(0, y0, W, y0 + 10, fill=t['background'], outline='')
            cyber.draw_ornament(c, t, 0, y0, W, 10)

        if fx.get('art_slab'):
            c.create_polygon(90, 10, 330, 10, 230, H - 10, -10, H - 10, fill=t['accent'], outline='')
            c.create_polygon(340, 10, 356, 10, 256, H - 10, 240, H - 10, fill=t['accent2'], outline='')
            for i in range(26):
                for j in range(12):
                    r = max(0, 3.2 - (i + j) * .16)
                    if r > .4: c.create_oval(8 + j*14 - r, H - 20 - i*14 - r, 8 + j*14 + r, H - 20 - i*14 + r,
                                             fill=appearance.mix(t['accent'], t['background'], .55), outline='')
        path = Path(logo_path) if logo_path else Path(__file__).resolve().parents[1]/'resources'/'asuka.webp'
        try:
            self.art = ImageTk.PhotoImage(_neon_art(path, (290, H - 40), t, split=fx['glitch'], scan=fx['scanlines']))
            c.create_image(170, H // 2 + 4, image=self.art)
        except (OSError, ValueError):
            pass

        x = 350
        self._boot = fx['boot']
        c.create_text(x, 40, text=self._boot[0], anchor='nw', fill=t['accent2'], font=f['mono_small'])
        line = tk.font.Font(font=f['display']).metrics('linespace')
        upper = fx['upper']
        cyber.styled_text(c, x, 58, 'APEX ASSET' if upper else 'Apex Asset', f['display'], t, glitch_amount=3)
        cyber.styled_text(c, x, 58 + line * fx.get('leading', .86), 'STUDIO' if upper else 'Studio', f['display'], t, glitch_amount=3)
        sub_y = int(58 + line * (1 + fx.get('leading', .86))) + 2
        c.create_text(x + 2, sub_y, text=f'MODEL // MATERIAL // ANIMATION   BUILD {version}', anchor='nw',
                      fill=t['muted'], font=f['mono_small'])

        self._log_x, self._log_y = x, sub_y + 34
        self._lines = []
        self._segments = []
        seg_w, gap, sy = 14, 4, H - 56
        for i in range(24):
            sx = x + i * (seg_w + gap)
            self._segments.append(c.create_polygon(sx + 3, sy, sx + seg_w + 3, sy, sx + seg_w, sy + 10, sx, sy + 10,
                                                   fill=t['raised'], outline=''))
        self.status = c.create_text(x, sy - 22, text='INITIALIZING', anchor='nw', fill=t['accent'], font=f['mono'])
        self.lift(); self.update()

    def _build_aero(self, c, W, H, t, f, logo_path, version):
        """Frutiger Aero splash: soft glow backdrop, light ribbons, bokeh, the mascot, and one frosted glass card
        holding only the app name, the current step and a progress bar."""
        from PIL import ImageFilter
        from . import gloss
        self.configure(background=t['border'])
        light = t['light']
        top = gloss.rgb(appearance.mix(t['accent'], '#ffffff', .10) if light else appearance.mix(t['accent'], t['background'], .30))
        bottom = gloss.rgb(appearance.mix(t['accent2'], '#ffffff', .06) if light else t['background'])
        bg = gloss._vgradient((W, H), top, bottom)
        glow = Image.new('RGBA', (W, H), (0, 0, 0, 0)); d = ImageDraw.Draw(glow)
        d.ellipse((W * .45, -H * .3, W * 1.25, H * .9), fill=gloss.rgb(t['accent'], 120 if not light else 70))
        d.ellipse((-W * .2, H * .45, W * .5, H * 1.4), fill=gloss.rgb(t['accent2'], 70 if not light else 50))
        bg.alpha_composite(glow.filter(ImageFilter.GaussianBlur(70)))
        bg.alpha_composite(gloss.swoosh((W, H), '#ffffff', seed=5, alpha=60 if not light else 120))
        bg.alpha_composite(gloss.bokeh((W, H), '#ffffff' if not light else t['accent'], 22, 2, 8, 40, alpha=(10, 34)))
        path = Path(logo_path) if logo_path else Path(__file__).resolve().parents[1]/'resources'/'asuka.webp'
        try:
            art = _plain_art(path, (int(W * .48), int(H * 1.0)))
            halo = Image.new('RGBA', art.size, gloss.rgb('#ffffff' if light else t['accent'], 0))
            halo.putalpha(art.getchannel('A').point(lambda v: int(v * .55)))
            halo = halo.filter(ImageFilter.GaussianBlur(18))
            ax = W - art.width - 10; ay = H - art.height + 6
            bg.alpha_composite(halo, (ax, ay)); bg.alpha_composite(art, (ax, ay))
        except (OSError, ValueError):
            pass
        card = (34, H - 176, 34 + 380, H - 34)
        bg = gloss.glass(bg, card, '#ffffff' if light else t['background'], radius=18, tint_alpha=120 if light else 110)
        self._bgimg = ImageTk.PhotoImage(bg)
        c.create_image(0, 0, image=self._bgimg, anchor='nw')
        x0, y0, x1, y1 = card
        title = (f['display'][0], max(22, f['display'][1] - 6))
        c.create_text(x0 + 24, y0 + 30, text='Apex Asset Studio', anchor='w', fill=t['text'], font=title)
        c.create_text(x1 - 24, y0 + 74, text=f'v{version}', anchor='e', fill=t['muted'], font=f['small'])
        self.status = c.create_text(x0 + 24, y0 + 74, text='Starting…', anchor='w', fill=t['muted'], font=f['body'])
        self._bar = (x0 + 24, y0 + 98, x1 - 24, 14)
        self._bar_track = ImageTk.PhotoImage(gloss.pill(self._bar[2] - self._bar[0], self._bar[3], t['raised'], 'pressed', radius=7, dark=not light))
        c.create_image(self._bar[0], self._bar[1], image=self._bar_track, anchor='nw')
        self._bar_item = None
        self._boot = ('', 'Ready')
        self._lines = []; self._segments = []

    def _aero_progress(self, fraction):
        from . import gloss
        x0, y, x1, h = self._bar
        width = max(h, int((x1 - x0) * fraction))
        self._bar_fill = ImageTk.PhotoImage(gloss.pill(width, h, self.t['accent'], 'normal', radius=7, dark=not self.t['light']))
        if self._bar_item: self.canvas.delete(self._bar_item)
        self._bar_item = self.canvas.create_image(x0, y, image=self._bar_fill, anchor='nw')

    def _build_promo(self, c, W, H, t, f, logo_path, version):
        """Bright promo-poster layout: diagonal band, giant thin numeral, confetti, big thin date."""
        import datetime, random
        pale = appearance.mix(t['accent'], '#ffffff', .13)
        for k in range(-20, 30):  # diamond lattice, right side
            x = 500 + k * 34
            c.create_line(x, 0, x + H, H, fill=pale); c.create_line(x, 0, x - H, H, fill=pale)
        c.create_rectangle(0, 0, 470, H, fill='#ffffff', outline='')
        rng = random.Random(4)
        for i in range(22):  # dotted rain lines lower-left
            x = 18 + i * 9; top = H - rng.randint(60, 170)
            for y in range(top, H, 6): c.create_line(x, y, x, y + 3, fill=appearance.mix(t['accent'], '#ffffff', .35))
        band = (0, 180, W, 30, W, 170, 0, 310)
        c.create_polygon(*band, fill=t['accent'], outline='')
        c.create_text(-14, 250, text='0.3', anchor='w', fill=appearance.mix('#ffffff', t['accent'], .25), font=(f['display'][0], 150))
        cyber.confetti(c, 0, 0, W, H, 26, 11, 4, 20, avoid=(360, 40, W, 440))
        cyber.confetti(c, 360, 0, W - 360, H, 8, 5, 3, 8, avoid=(370, 60, W, 400))
        path = Path(logo_path) if logo_path else Path(__file__).resolve().parents[1]/'resources'/'asuka.webp'
        try:
            self.art = ImageTk.PhotoImage(_plain_art(path, (300, H - 14)))
            c.create_image(205, H, image=self.art, anchor='s')
        except (OSError, ValueError):
            pass
        x = 392
        c.create_text(x, 132, text='Apex Asset Studio', anchor='w', fill='#ffffff', font=(f['title'][0], 30))
        c.create_text(x + 2, 170, text='モデル・マテリアル・アニメーション書き出しツール', anchor='w', fill='#ffffff', font=f['jp_title'])
        today = datetime.date.today()
        c.create_text(x, 284, text=f'{today.year}.', anchor='sw', fill=t['text'], font=(f['title'][0], 18))
        year_w = tk.font.Font(font=(f['title'][0], 18)).measure(f'{today.year}.')
        big = (f['display'][0], 44)
        c.create_text(x + year_w, 292, text=f'{today.month}/{today.day:02d}', anchor='sw', fill=t['text'], font=big)
        big_w = tk.font.Font(font=big).measure(f'{today.month}/{today.day:02d}')
        c.create_text(x + year_w + big_w + 4, 284, text=f"({today.strftime('%a')})", anchor='sw', fill=t['text'], font=(f['title'][0], 18))
        c.create_text(x + 2, 304, text=f'Build {version}  ·  起動中です！ご期待ください ♪', anchor='nw', fill=t['muted'], font=f['jp_title'])
        self._boot = appearance.fx()['boot']
        self.status = c.create_text(W - 18, 22, text='Starting…', anchor='ne', fill=t['accent'], font=f['section'])
        self._log_x, self._log_y = x + 2, 336
        self._lines = []; self._segments = []
        for i in range(STAGES * 4):
            cx = x + 8 + i * 17; cy = H - 24
            self._segments.append(c.create_oval(cx - 5, cy - 5, cx + 5, cy + 5, fill=t['raised'], outline=''))

    def stage(self, message):
        if self._closed: return
        t, f, c = self.t, self.f, self.canvas
        if self.aero:
            self._step += 1
            self._aero_progress(min(1, self._step / STAGES))
            c.itemconfigure(self.status, text='Ready' if message == 'Ready' else message)
            self.update(); return
        if self.promo:
            if self._lines: c.itemconfigure(self._lines[-1][1], text='✓', fill=t['accent'])
            self._step += 1
            y = self._log_y + len(self._lines) * 16
            line = c.create_text(self._log_x, y, text=message.rstrip('…'), anchor='nw', fill=t['muted'], font=f['body'])
            state = c.create_text(self._log_x + 230, y, text='…', anchor='nw', fill=t['accent2'], font=f['body'])
            self._lines.append((line, state))
            filled = round(len(self._segments) * min(1, self._step / STAGES))
            for i, seg in enumerate(self._segments):
                c.itemconfigure(seg, fill=appearance.CONFETTI[i % len(appearance.CONFETTI)] if i < filled else t['raised'])
            c.itemconfigure(self.status, text=self._boot[1] if message == 'Ready' else self._boot[0])
            self.update(); return
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
        c.itemconfigure(self.status, text=self._boot[1] if message == 'Ready' else appearance.jp('LOADING  //  読み込み中'))
        self.update()

    def finish(self, app):
        self.stage('Ready')
        if self._lines and not self.aero: self.canvas.itemconfigure(self._lines[-1][1], text='♪' if self.promo else 'GO', fill=self.t['accent'])
        self.update()
        delay = max(0, int((0.35-(time.monotonic()-self.started))*1000))  # just long enough to read 'Ready'
        def reveal():
            if self._closed: return
            self._closed = True; self.destroy(); app.deiconify(); app.lift()
        app.after(delay, reveal)
