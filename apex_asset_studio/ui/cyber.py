"""Canvas-drawn decoration that changes with the active style: title type, ornament strips, section tags,
viewport brackets, the primary action button and the empty-viewport placeholder.

Every widget here has redraw(tokens); call refresh(app, tokens) after a style or palette change.
"""
import random
import tkinter as tk
import tkinter.font
from . import appearance

AVATAR = {}  # 'image': circular avatar PhotoImage provided by the app (promo styles)


def confetti(c, x0, y0, w, h, count, seed, rmin=3, rmax=9, avoid=None):
    rng = random.Random(seed)
    for _ in range(count):
        r = rng.uniform(rmin, rmax); x = rng.uniform(x0 + r, x0 + w - r); y = rng.uniform(y0 + r, y0 + h - r)
        if avoid and avoid[0] < x < avoid[2] and avoid[1] < y < avoid[3]: continue
        c.create_oval(x - r, y - r, x + r, y + r, fill=rng.choice(appearance.CONFETTI), outline='')


def _registry(app):
    if not hasattr(app, '_cyber_widgets'): app._cyber_widgets = []
    return app._cyber_widgets


def refresh(app, tokens):
    alive = []
    for widget in _registry(app):
        try:
            if widget.winfo_exists(): widget.redraw(tokens); alive.append(widget)
        except tk.TclError:
            pass
    app._cyber_widgets[:] = alive


def _measure(font, text): return tk.font.Font(font=font).measure(text)


def _line(font): return tk.font.Font(font=font).metrics('linespace')


def _star(canvas, x, y, r, fill):
    k = r * .38
    canvas.create_polygon(x, y-r, x+k, y-k, x+r, y, x+k, y+k, x, y+r, x-k, y+k, x-r, y, x-k, y-k, fill=fill, outline='')


def _rounded(canvas, x0, y0, x1, y1, fill, outline=''):
    r = (y1 - y0) / 2
    canvas.create_oval(x0, y0, x0 + 2*r, y1, fill=fill, outline=outline)
    canvas.create_oval(x1 - 2*r, y0, x1, y1, fill=fill, outline=outline)
    canvas.create_rectangle(x0 + r, y0, x1 - r, y1, fill=fill, outline='')
    if outline:
        canvas.create_line(x0 + r, y0, x1 - r, y0, fill=outline); canvas.create_line(x0 + r, y1, x1 - r, y1, fill=outline)


def styled_text(canvas, x, y, text, font, t, anchor='nw', fill=None, glitch_amount=2):
    """Draw text with the active style's treatment: chromatic split, drop shadow or plain."""
    fx = appearance.fx(); fill = fill or t['text']
    if fx['glitch']:
        canvas.create_text(x - glitch_amount, y, text=text, anchor=anchor, fill=t['accent2'], font=font)
        canvas.create_text(x + glitch_amount, y + 1, text=text, anchor=anchor, fill=t['accent'], font=font)
    elif fx.get('shadow'):
        dx = fx['shadow'][1]
        canvas.create_text(x + dx, y + dx, text=text, anchor=anchor, fill=t[fx['shadow'][0]], font=font)
    canvas.create_text(x, y, text=text, anchor=anchor, fill=fill, font=font)


class _Base(tk.Canvas):
    on = 'background'

    def __init__(self, master, on='background', **kwargs):
        kwargs.setdefault('highlightthickness', 0); kwargs.setdefault('borderwidth', 0)
        super().__init__(master, **kwargs)
        self.on = on; self.t = None
        _registry(self.winfo_toplevel()).append(self)
        self.bind('<Configure>', lambda _e: self.t and self.redraw(self.t))

    def fonts(self): return appearance.fonts(self)


class HazardStrip(_Base):
    """Full-width ornament band: stripes, sunset bars, stars, pixels or chevrons depending on the style."""
    def __init__(self, master, height=6, on='background', **kwargs):
        super().__init__(master, on=on, height=height, **kwargs)

    def redraw(self, t):
        self.t = t; self.delete('all'); self.configure(background=t[self.on])
        draw_ornament(self, t, 0, 0, max(self.winfo_width(), 1), int(self.cget('height')))


def draw_ornament(c, t, x0, y0, w, h, kind=None):
    kind = kind or appearance.fx()['ornament']
    if kind == 'stripes':
        step = 14; x = x0 - h
        while x < x0 + w + h:
            c.create_polygon(x, y0+h, x+h, y0, x+h+step/2, y0, x+step/2, y0+h, fill=t['accent'], outline='')
            x += step
    elif kind == 'sunbars':
        bars = 4
        for i in range(bars):
            color = appearance.mix(t['accent2'], t['accent'], i/(bars-1))
            c.create_rectangle(x0, y0 + i*h/bars, x0 + w, y0 + (i+1)*h/bars - 1, fill=color, outline='')
    elif kind == 'stars':
        c.create_rectangle(x0, y0 + h/2 - 1, x0 + w, y0 + h/2, fill=t['border'], outline='')
        for i, x in enumerate(range(int(x0) + 10, int(x0 + w), 26)):
            if i % 2: c.create_oval(x-2, y0+h/2-2, x+2, y0+h/2+2, fill=t['accent2'], outline='')
            else: _star(c, x, y0 + h/2, h/2, t['accent'])
    elif kind == 'pixels':
        size = max(2, h // 2)
        for row in range(2):
            for i, x in enumerate(range(int(x0), int(x0 + w), size)):
                if (i + row) % 2 == 0:
                    c.create_rectangle(x, y0 + row*size, x + size, y0 + (row+1)*size, fill=t['accent'] if row == 0 else t['border'], outline='')
    elif kind == 'broadcast':
        # solid bar with a slanted end, three slashes, then a hairline to the edge
        end = x0 + min(w * .32, 420)
        c.create_polygon(x0, y0, end, y0, end - h, y0 + h, x0, y0 + h, fill=t['accent'], outline='')
        for i in range(3):
            sx = end + 6 + i * (h + 4)
            c.create_polygon(sx, y0, sx + h * .6, y0, sx - h * .4, y0 + h, sx - h, y0 + h, fill=t['accent2'], outline='')
        c.create_rectangle(end + 6 + 3 * (h + 4), y0 + h - 2, x0 + w, y0 + h - 1, fill=t['border'], outline='')
    elif kind == 'confetti':
        c.create_rectangle(x0, y0 + h - 2, x0 + w, y0 + h, fill=t['accent'], outline='')
        rng = random.Random(7)
        for x in range(int(x0) + 30, int(x0 + w), 90):
            r = rng.uniform(1.5, h / 2 - .5)
            c.create_oval(x - r, y0 + h/2 - r - 1, x + r, y0 + h/2 + r - 1, fill=rng.choice(appearance.CONFETTI), outline='')
    elif kind == 'chevrons':
        c.create_rectangle(x0, y0, x0 + w, y0 + h, fill=t['background'], outline='')
        for x in range(int(x0) - h, int(x0 + w), 18):
            c.create_polygon(x, y0, x+6, y0, x+6+h/2, y0+h/2, x+6, y0+h, x, y0+h, x+h/2, y0+h/2, fill=t['accent'], outline='')


class GlitchText(_Base):
    """Title text drawn with the active style's treatment, with an optional small subtitle line."""
    def __init__(self, master, text, font='brand', jp=None, on='background', pad=(0, 0), **kwargs):
        super().__init__(master, on=on, **kwargs)
        self.text = text; self.font_key = font; self.jp = jp; self.pad = pad
        self._resize()

    def _resize(self):
        f = self.fonts()
        if appearance.fx().get('promo') and self.font_key == 'brand':
            self.configure(width=_measure(f['brand'], self.text) + 175, height=58); return
        width = _measure(f[self.font_key], self.shown()) + 10 + self.pad[0]*2
        height = _line(f[self.font_key]) + 4 + self.pad[1]*2
        sub = appearance.jp(self.jp)
        if sub:
            width = max(width, _measure(f['jp'], sub) + 8); height += _line(f['jp'])
        self.configure(width=width, height=height)

    def shown(self):
        return self.text.upper() if appearance.fx()['upper'] else self.text

    def _promo_plate(self, t):
        f = self.fonts(); w, h = int(self.cget('width')), int(self.cget('height'))
        self.create_polygon(0, 8, w - 4, 2, w - 22, h - 4, 0, h - 2, fill=t['accent'], outline='')
        self.create_text(w - 30, h / 2 + 2, text='0.3', anchor='e', fill=appearance.mix('#ffffff', t['accent'], .22),
                         font=(f['display'][0], 34))
        image = AVATAR.get('image')
        if image:
            self.create_oval(4, 1, 58, 55, fill='#ffffff', outline='')
            self.create_image(31, 28, image=image)
        self.create_text(66, h / 2 - 7, text=self.text, anchor='w', fill='#ffffff', font=f['brand'])
        sub = appearance.jp(self.jp)
        if sub: self.create_text(67, h / 2 + 14, text=sub, anchor='w', fill=appearance.mix('#ffffff', t['accent'], .8), font=f['jp'])
        for x, y, r, color in ((w - 10, 10, 4, appearance.CONFETTI[1]), (w - 30, h - 6, 3, appearance.CONFETTI[0]), (60, 6, 2.5, appearance.CONFETTI[4])):
            self.create_oval(x - r, y - r, x + r, y + r, fill=color, outline='')

    def redraw(self, t):
        self.t = t; self._resize(); self.delete('all'); self.configure(background=t[self.on])
        if appearance.fx().get('promo') and self.font_key == 'brand': return self._promo_plate(t)
        f = self.fonts(); x, y = 3 + self.pad[0], 1 + self.pad[1]
        styled_text(self, x, y, self.shown(), f[self.font_key], t)
        sub = appearance.jp(self.jp)
        if sub:
            self.create_text(x + 1, y + _line(f[self.font_key]), text=sub, anchor='nw', fill=t['muted'], font=f['jp'])


class SectionTag(_Base):
    """Section heading with a Japanese sub-label and a rule that fills the remaining width."""
    def __init__(self, master, text, jp='', on='surface', **kwargs):
        super().__init__(master, on=on, height=22, **kwargs)
        self.text = text; self.jp = jp

    def redraw(self, t):
        self.t = t; self.delete('all'); self.configure(background=t[self.on])
        f = self.fonts(); fx = appearance.fx(); w = max(self.winfo_width(), 1)
        h = max(22, _line(f['section']) + 6); mid = h / 2
        if int(self.cget('height')) != h: self.configure(height=h)
        text = self.text.upper() if fx['upper'] else self.text
        label = _measure(f['section'], text)
        kind = fx['tag']
        if kind == 'slant':
            x1 = label + 20
            self.create_polygon(0, 3, x1, 3, x1 - 6, h - 3, 0, h - 3, fill=t['accent2'], outline='')
            self.create_text(7, mid, text=text, anchor='w', fill=t['accent2_text'], font=f['section'])
        elif kind == 'aero':
            self._orb = _orb_image(10, t['accent'])
            self.create_image(5, mid, image=self._orb)
            self.create_text(16, mid, text=text, anchor='w', fill=t['text'], font=f['section'])
            x1 = label + 16
        elif kind == 'underline':
            self.create_text(0, mid - 1, text=text, anchor='w', fill=t['accent'], font=f['section'])
            x1 = label
        elif kind == 'skew':
            self.create_polygon(0, 2, 10, 2, 4, h - 2, -6, h - 2, fill=t['accent'], outline='')
            x1 = label + 30
            self.create_polygon(13, 2, x1 + 6, 2, x1, h - 2, 7, h - 2, fill=t['accent2'], outline='')
            self.create_text(18, mid, text=text, anchor='w', fill=t['accent2_text'], font=f['section'])
        elif kind == 'box':
            x1 = label + 16
            self.create_rectangle(0, 3, x1, h - 3, fill=t['accent'], outline='')
            self.create_text(8, mid, text=text, anchor='w', fill=t['accent_text'], font=f['section'])
        elif kind == 'pill':
            x1 = label + 24
            _rounded(self, 0, 2, x1, h - 2, fill=t['accent2'])
            self.create_text(12, mid, text=text, anchor='w', fill=t['accent2_text'], font=f['section'])
        else:  # window: JRPG cursor + label
            self.create_polygon(0, mid - 5, 8, mid, 0, mid + 5, fill=t['accent'], outline='')
            self.create_text(14, mid, text=text, anchor='w', fill=t['accent'], font=f['section'])
            x1 = label + 16
        x = x1 + 10
        sub = appearance.jp(self.jp)
        if sub:
            self.create_text(x, mid, text=sub, anchor='w', fill=t['muted'], font=f['jp'])
            x += _measure(f['jp'], sub) + 10
        if x >= w - 10: return
        if kind == 'aero':
            steps = 24; span = (w - x) / steps
            for i in range(steps):
                self.create_line(x + i*span, mid, x + (i+1)*span + 1, mid, fill=appearance.mix(t['border'], t[self.on], 1 - i/steps))
            return
        if kind == 'underline':
            self.create_rectangle(0, h - 2, w, h - 1, fill=t['accent'], outline='')
            rng = random.Random(len(self.text))
            for i in range(3):
                r = 3 - i * .6; cx = w - 8 - i * 11
                self.create_oval(cx - r, mid - r - 1, cx + r, mid + r - 1, fill=rng.choice(appearance.CONFETTI), outline='')
        elif kind == 'skew':
            self.create_rectangle(x, h - 4, w, h - 3, fill=t['border'], outline='')
            for i in range(3):
                sx = w - 30 + i * 9
                self.create_polygon(sx + 4, 4, sx + 8, 4, sx + 4, h - 6, sx, h - 6, fill=t['accent'], outline='')
        elif kind in ('slant', 'box'):
            self.create_line(x, mid, w, mid, fill=t['border'])
            for tick in range(int(w) - 2, int(x) + 20, -24):
                self.create_line(tick, mid - 3, tick, mid + 3, fill=t['border'])
            self.create_rectangle(w - 6, mid - 2, w - 2, mid + 2, fill=t['accent'], outline='')
        elif kind == 'pill':
            for dot in range(int(x), int(w) - 12, 8):
                self.create_oval(dot, mid - 1, dot + 2, mid + 1, fill=t['border'], outline='')
            if fx['ornament'] == 'stars': _star(self, w - 8, mid, 6, t['accent'])
            else: self.create_oval(w - 10, mid - 4, w - 2, mid + 4, fill=t['accent'], outline='')
        else:
            self.create_line(x, mid - 1, w, mid - 1, fill=t['border']); self.create_line(x, mid + 2, w, mid + 2, fill=t['border'])


class NeonButton(_Base):
    """Primary action button shaped by the active style. Mimics ttk's state()/instate()."""
    def __init__(self, master, text, command=None, jp='', on='surface', width=210, height=40, **kwargs):
        super().__init__(master, on=on, width=width, height=height, cursor='hand2', **kwargs)
        self.text = text; self.jp = jp; self.command = command; self.base_height = height
        self._disabled = False; self._hover = False; self._pressed = False
        self.bind('<Enter>', lambda _e: self._set(hover=True)); self.bind('<Leave>', lambda _e: self._set(hover=False, pressed=False))
        self.bind('<ButtonPress-1>', lambda _e: self._set(pressed=True))
        self.bind('<ButtonRelease-1>', self._release)

    def _set(self, **kw):
        for k, v in kw.items(): setattr(self, '_' + k, v)
        if self.t: self.redraw(self.t)

    def _release(self, event):
        inside = 0 <= event.x <= self.winfo_width() and 0 <= event.y <= self.winfo_height()
        self._set(pressed=False)
        if inside and not self._disabled and self.command: self.command()

    def state(self, spec=None):
        if spec:
            for item in spec:
                if item == 'disabled': self._disabled = True
                elif item == '!disabled': self._disabled = False
            self.configure(cursor='arrow' if self._disabled else 'hand2')
            if self.t: self.redraw(self.t)
        return ('disabled',) if self._disabled else ()

    def instate(self, spec):
        return all(self._disabled if item == 'disabled' else not self._disabled if item == '!disabled' else False for item in spec)

    def redraw(self, t):
        self.t = t; self.delete('all'); self.configure(background=t[self.on])
        f = self.fonts(); fx = appearance.fx(); kind = fx['button']
        want = max(self.base_height, _line(f['nav']) + 14)
        if int(self.cget('height')) != want: self.configure(height=want)
        w, h = max(self.winfo_width(), int(self.cget('width')) if self.winfo_width() < 20 else 1), want
        text = self.text.upper() if fx['upper'] else self.text
        if self._disabled:
            fill, edge, ink = t['surface'], t['border'], t['faint']
        else:
            fill = t['accent2'] if self._hover and not self._pressed else t['accent']
            edge = fill; ink = t['accent2_text'] if self._hover and not self._pressed else t['accent_text']
        if kind == 'gloss':
            from PIL import ImageTk
            from . import gloss
            state = 'disabled' if self._disabled else 'pressed' if self._pressed else 'hover' if self._hover else 'normal'
            self._img = ImageTk.PhotoImage(gloss.pill(w, h, t['accent'], state, radius=8, dark=not t['light']), master=self)
            self.create_image(0, 0, image=self._img, anchor='nw')
            ink = t['faint'] if self._disabled else t['accent_text']
            self.create_text(w / 2, h / 2, text=text, fill=ink, font=f['strong'])
            return
        if kind == 'flat':
            if not self._disabled and self._hover: fill = t['accent2']
            self.create_rectangle(0, 0, w, h, fill=fill, outline=edge if self._disabled else '')
            r = h * .3; cx = w - h / 2
            self.create_oval(cx - r, h/2 - r, cx + r, h/2 + r, fill='#ffffff' if not self._disabled else t['border'], outline='')
            self.create_text(cx + 1, h/2 - 1, text='›', fill=fill if not self._disabled else t['faint'], font=f['strong'])
            tx = 16
        elif kind == 'skew':
            k = h * .35
            if not self._disabled and self._hover:
                fill, ink = t['text'], t['background']
            self.create_polygon(k, 0, w, 0, w - k, h, 0, h, fill=fill, outline=edge if self._disabled else '')
            if not self._disabled:
                self.create_polygon(w - k - 26, 0, w - 18, 0, w - k - 18 - k, h, w - k - 26 - k, h,
                                    fill=t['accent'] if self._hover else appearance.mix('#000000', fill, .18), outline='')
            self.create_text(w - k - 8, h/2, text='»', anchor='e', fill=ink, font=f['nav'])
            tx = k + 12
        elif kind == 'pill':
            if not self._disabled and self._hover: _rounded(self, 3, 4, w - 1, h - 1, fill=t['accent'])
            _rounded(self, 1, 1, w - 3, h - 4, fill=fill, outline=edge if self._disabled else '')
            _star(self, w - 22, h/2 - 1.5, 6, ink)
            tx = 18
        elif kind == 'pixel':
            s = 4
            self.create_polygon(s, 0, w - s, 0, w - s, s, w, s, w, h - s, w - s, h - s, w - s, h, s, h, s, h - s, 0, h - s, 0, s, s, s,
                                fill=fill, outline='')
            if not self._disabled:
                self.create_rectangle(s, s, w - s, s + 2, fill=appearance.mix('#ffffff', fill, .45), outline='')
            tx = 30 if self._hover and not self._disabled else 18
            if self._hover and not self._disabled:
                self.create_polygon(12, h/2 - 6, 20, h/2, 12, h/2 + 6, fill=ink, outline='')
        else:
            cut = 10
            self.create_polygon(cut, 0, w, 0, w, h - cut, w - cut, h, 0, h, 0, cut, fill=fill, outline=edge if self._disabled else '')
            for i in range(4):
                x = w - 44 + i * 9
                self.create_polygon(x, h - 8, x + 4, h - 8, x + 8, 8, x + 4, 8, fill=ink if not self._disabled else t['border'], outline='')
            tx = 16
        cy = h/2 - (1.5 if kind == 'pill' else 0)
        self.create_text(tx, cy, text=text, anchor='w', fill=ink, font=f['nav'])
        sub = appearance.jp(self.jp)
        if sub:
            self.create_text(tx + _measure(f['nav'], text) + 8, cy + 1, text=sub, anchor='w', fill=ink, font=f['jp'])


_ORBS = {}


def _orb_image(size, color):
    from PIL import ImageTk
    key = (size, color)
    if key not in _ORBS:
        from . import gloss
        im = gloss.pill(size, size, color, 'normal', radius=size // 2)
        _ORBS[key] = ImageTk.PhotoImage(im)
    return _ORBS[key]


class HeaderBar(tk.Canvas):
    """Glossy Aero title bar drawn on one canvas: mascot orb, app name, page tabs, game status and Scan button.

    The app supplies callbacks: pages() -> [(key, label, active)], on_page(key), scan() -> (label, enabled),
    on_scan(), game() -> (ok, label), on_game().
    """
    HEIGHT = 62

    def __init__(self, master, app, **callbacks):
        super().__init__(master, height=self.HEIGHT, highlightthickness=0, borderwidth=0)
        self.app = app; self.cb = callbacks; self.t = None; self.hover = None; self.hits = []; self._bg_key = None
        _registry(self.winfo_toplevel()).append(self)
        self.bind('<Configure>', lambda _e: self.t and self.redraw(self.t))
        self.bind('<Motion>', self._motion); self.bind('<Leave>', lambda _e: self._set_hover(None))
        self.bind('<ButtonRelease-1>', self._click)

    def _background(self, t, w, h):
        from PIL import ImageTk
        from . import gloss
        key = (w, h, t['background'], t['accent'], t['light'])
        if key == self._bg_key: return
        top = gloss.rgb(appearance.mix(t['accent'], t['background'], .16 if not t['light'] else .08))
        bottom = gloss.rgb(t['background'])
        image = gloss._vgradient((w, h), top, bottom)
        image.alpha_composite(gloss.swoosh((w, h), t['accent2'], seed=3, alpha=45 if not t['light'] else 60))
        image.alpha_composite(gloss.bokeh((w, h), t['accent'], 10, 9, 6, 26, alpha=(10, 28)))
        sheen = gloss._vgradient((w, h // 2), (255, 255, 255, 26 if not t['light'] else 90), (255, 255, 255, 0))
        image.alpha_composite(sheen)
        self._bg = ImageTk.PhotoImage(image, master=self); self._bg_key = key

    def redraw(self, t):
        from PIL import ImageTk
        from . import gloss
        self.t = t; self.delete('all'); self.hits = []
        f = appearance.fonts(self); w = max(self.winfo_width(), 1)
        h = max(self.HEIGHT, _line(f['brand']) + _line(f['small']) + 22, _line(f['nav']) + 30)
        if int(self.cget('height')) != h: self.configure(height=h)
        self._background(t, w, h)
        self.create_image(0, 0, image=self._bg, anchor='nw')
        self.create_line(0, h - 1, w, h - 1, fill=appearance.mix(t['accent'], t['border'], .35))
        x = 14
        orb = AVATAR.get('orb')
        if orb: self.create_image(x, h / 2, image=orb, anchor='w'); x += orb.width() + 12
        block = _line(f['brand']) + _line(f['small']); top = (h - block) / 2
        self.create_text(x, top, text='Apex Asset Studio', anchor='nw', fill=t['text'], font=f['brand'])
        self.create_text(x + 1, top + _line(f['brand']), text=f"v{AVATAR.get('version', '')}", anchor='nw', fill=t['muted'], font=f['small'])
        x += _measure(f['brand'], 'Apex Asset Studio') + 34
        self._pills = []
        for key, label, active in self.cb['pages']():
            tw = _measure(f['nav'], label) + 30; ph = _line(f['nav']) + 14; y0 = (h - ph) / 2
            if active or self.hover == ('page', key):
                color = t['accent'] if active else gloss.shade(t['raised'], .12 if not t['light'] else -.03)
                img = ImageTk.PhotoImage(gloss.pill(tw, ph, color, 'normal', radius=8, dark=not t['light']), master=self)
                self._pills.append(img); self.create_image(x, y0, image=img, anchor='nw')
            ink = t['accent_text'] if active else (t['text'] if self.hover == ('page', key) else t['muted'])
            self.create_text(x + tw / 2, h / 2, text=label, fill=ink, font=f['nav'])
            self.hits.append(((x, y0, x + tw, y0 + ph), ('page', key))); x += tw + 6
        # right side: scan button then game status
        label, enabled = self.cb['scan']()
        bw = _measure(f['strong'], label) + 34; bh = _line(f['strong']) + 14; bx = w - 14 - bw; by = (h - bh) / 2
        state = 'disabled' if not enabled else 'hover' if self.hover == ('scan',) else 'normal'
        img = ImageTk.PhotoImage(gloss.pill(bw, bh, gloss.shade(t['raised'], .14 if not t['light'] else -.02), state, radius=8,
                                            dark=not t['light']), master=self)
        self._pills.append(img); self.create_image(bx, by, image=img, anchor='nw')
        self.create_text(bx + bw / 2, h / 2, text=label, fill=t['text'] if enabled else t['faint'], font=f['strong'])
        if enabled: self.hits.append(((bx, by, bx + bw, by + bh), ('scan',)))
        ok, game = self.cb['game']()
        gx = bx - 16
        self.create_text(gx, h / 2, text=game, anchor='e', fill=t['text'] if self.hover == ('game',) else t['muted'], font=f['small'])
        gw = _measure(f['small'], game)
        dot = t['accent2'] if ok else t['warn']
        self.create_oval(gx - gw - 16, h / 2 - 4, gx - gw - 8, h / 2 + 4, fill=dot, outline='')
        self.hits.append(((gx - gw - 18, h / 2 - 12, gx, h / 2 + 12), ('game',)))
        self.configure(cursor='hand2' if self.hover else '')

    def _hit(self, event):
        for (x0, y0, x1, y1), target in self.hits:
            if x0 <= event.x <= x1 and y0 <= event.y <= y1: return target
        return None

    def _set_hover(self, target):
        if target != self.hover:
            self.hover = target
            if self.t: self.redraw(self.t)

    def _motion(self, event): self._set_hover(self._hit(event))

    def _click(self, event):
        target = self._hit(event)
        if not target: return
        if target[0] == 'page': self.cb['on_page'](target[1])
        elif target[0] == 'scan': self.cb['on_scan']()
        else: self.cb['on_game']()


class Bracket(_Base):
    """One viewport corner mark. corner is 'nw', 'ne', 'sw' or 'se'."""
    def __init__(self, master, corner, size=16, color='accent2', on=None, **kwargs):
        on = on or ('viewport_top' if 'n' in corner else 'viewport')
        super().__init__(master, on=on, width=size, height=size, **kwargs)
        self.corner = corner; self.size = size; self.color = color

    def redraw(self, t):
        self.t = t; self.delete('all'); self.configure(background=t[self.on])
        if appearance.fx().get('brackets') is False: return
        s = self.size - 1; c = t[self.color]; kind = appearance.fx()['tag']
        x = 0 if 'w' in self.corner else s; y = 0 if 'n' in self.corner else s
        dx = 1 if 'w' in self.corner else -1; dy = 1 if 'n' in self.corner else -1
        if kind == 'pill':
            _star(self, s/2, s/2, s/2 - 1, c)
        elif kind == 'underline':
            color = appearance.CONFETTI[{'nw': 0, 'ne': 2, 'sw': 4, 'se': 1}[self.corner]]
            self.create_oval(s/2 - 4, s/2 - 4, s/2 + 4, s/2 + 4, fill=color, outline='')
        elif kind == 'skew':
            c = t['accent']
            self.create_line(x, y + dy*s, x, y, x + dx*s, y, fill=c, width=3)
        else:
            self.create_line(x, y + dy*s, x, y, x + dx*s, y, fill=c, width=4 if kind == 'window' else 3)


class Signal(_Base):
    """Centered viewport placeholder: headline, Japanese subtitle and a message."""
    def __init__(self, master, on='viewport_mid', **kwargs):
        super().__init__(master, on=on, width=440, height=130, **kwargs)
        self.message = ''; self.headline = None

    def show(self, message, headline=None):
        self.message = message; self.headline = headline
        if self.t: self.redraw(self.t)

    def redraw(self, t):
        self.t = t; self.delete('all'); self.configure(background=t[self.on])
        f = self.fonts(); fx = appearance.fx(); cx = 220
        headline, jp = fx['signal']
        if self.headline: headline = self.headline.upper() if fx['upper'] else self.headline
        if fx.get('gloss'):
            self.create_text(cx, 44, text=headline, fill=t['text'], font=f['placeholder'])
            self.create_text(cx, 82, text=self.message, fill=t['muted'], font=f['body'], width=420, justify='center')
            return
        if fx.get('promo'):
            self.create_text(cx, 34, text=headline, fill=t['text'], font=f['placeholder'])
            self.create_text(cx, 70, text=jp, fill=t['accent'], font=f['jp_title'])
            self.create_text(cx, 98, text=self.message, fill=t['muted'], font=f['body'], width=420, justify='center')
            confetti(self, 0, 0, 440, 130, 9, 3, 2, 6, avoid=(70, 8, 370, 115))
            return
        styled_text(self, cx, 34, headline, f['placeholder'], t, anchor='center',
                    fill=t['text'] if fx['glitch'] or fx['tag'] == 'skew' else t['accent'], glitch_amount=3)
        if fx['glitch']:
            for y, x0, x1 in ((24, 130, 180), (40, 260, 310)):
                self.create_rectangle(x0, y, x1, y + 2, fill=t['accent'], outline='')
        if fx['tag'] == 'skew':
            width = _measure(f['placeholder'], headline)
            self.create_polygon(cx - width/2 - 10, 58, cx + width/2 + 14, 58, cx + width/2 + 8, 63, cx - width/2 - 16, 63,
                                fill=t['accent'], outline='')
            self.create_text(cx, 76, text=jp, fill=t['muted'], font=f['section'])
        else:
            self.create_text(cx, 70, text=jp, fill=t['muted'], font=f['jp'])
        self.create_text(cx, 98, text=self.message, fill=t['muted'], font=f['body'], width=420, justify='center')
