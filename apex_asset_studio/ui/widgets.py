"""Canvas-drawn widgets that follow the active theme: the glossy header bar, section headings and the primary
action button. Each has redraw(tokens); call refresh(app, tokens) after a theme or palette change."""
import tkinter as tk
import tkinter.font
from PIL import ImageTk

from . import appearance, gloss

AVATAR = {}  # 'orb': round mascot PhotoImage for the header (None hides it), 'version': app version text


def _registry(app):
    if not hasattr(app, '_theme_widgets'): app._theme_widgets = []
    return app._theme_widgets


def refresh(app, tokens):
    alive = []
    for widget in _registry(app):
        try:
            if widget.winfo_exists(): widget.redraw(tokens); alive.append(widget)
        except tk.TclError:
            pass
    app._theme_widgets[:] = alive


def _measure(font, text): return tk.font.Font(font=font).measure(text)


def _line(font): return tk.font.Font(font=font).metrics('linespace')


def _plate(w, h, color, state='normal', dark=True):
    """Glossy plate in the active theme's shape (capsule, rounded or nearly square)."""
    m = appearance.fx()
    radius = None if m['radius'] is None else m['radius'] + 2
    return gloss.pill(w, h, color, state, radius=radius, dark=dark, shine=m['shine'])


class _Base(tk.Canvas):
    def __init__(self, master, on='background', **kwargs):
        kwargs.setdefault('highlightthickness', 0); kwargs.setdefault('borderwidth', 0)
        super().__init__(master, **kwargs)
        self.on = on; self.t = None
        _registry(self.winfo_toplevel()).append(self)
        self.bind('<Configure>', lambda _e: self.t and self.redraw(self.t))

    def fonts(self): return appearance.fonts(self)


_BULLETS = {}


def _bullet(size, color):
    m = appearance.fx(); key = (size, color, m['radius'], m['shine'])
    if key not in _BULLETS:
        radius = size // 2 if m['radius'] is None or m['radius'] >= 4 else max(1, m['radius'])
        _BULLETS[key] = ImageTk.PhotoImage(gloss.pill(size, size, color, 'normal', radius=radius, shine=m['shine']))
    return _BULLETS[key]


class SectionTag(_Base):
    """Section heading: a small glossy bullet, the label, and a hairline that fades out to the right."""
    def __init__(self, master, text, on='surface', **kwargs):
        super().__init__(master, on=on, height=22, **kwargs)
        self.text = text

    def redraw(self, t):
        self.t = t; self.delete('all'); self.configure(background=t[self.on])
        f = self.fonts(); w = max(self.winfo_width(), 1)
        h = max(22, _line(f['section']) + 6); mid = h / 2
        if int(self.cget('height')) != h: self.configure(height=h)
        self._dot = _bullet(10, t['accent'])
        self.create_image(5, mid, image=self._dot)
        self.create_text(16, mid, text=self.text, anchor='w', fill=t['text'], font=f['section'])
        x = 16 + _measure(f['section'], self.text) + 10
        if x >= w - 10: return
        steps = 24; span = (w - x) / steps
        for i in range(steps):
            self.create_line(x + i*span, mid, x + (i+1)*span + 1, mid, fill=appearance.mix(t['border'], t[self.on], 1 - i/steps))


class GlossButton(_Base):
    """The primary action button (Export). Mimics ttk's state()/instate()."""
    def __init__(self, master, text, command=None, on='surface', width=210, height=40, **kwargs):
        super().__init__(master, on=on, width=width, height=height, cursor='hand2', **kwargs)
        self.text = text; self.command = command; self.base_height = height
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
        f = self.fonts()
        want = max(self.base_height, _line(f['strong']) + 16)
        if int(self.cget('height')) != want: self.configure(height=want)
        w, h = max(self.winfo_width(), int(self.cget('width')) if self.winfo_width() < 20 else 1), want
        state = 'disabled' if self._disabled else 'pressed' if self._pressed else 'hover' if self._hover else 'normal'
        color = gloss.shade(t['raised'], .06 if not t['light'] else -.02) if self._disabled else t['accent']
        self._img = ImageTk.PhotoImage(_plate(w, h, color, 'normal' if self._disabled else state, dark=not t['light']), master=self)
        self.create_image(0, 0, image=self._img, anchor='nw')
        self.create_text(w / 2, h / 2, text=self.text, fill=t['faint'] if self._disabled else t['accent_text'], font=f['strong'])


class HeaderBar(tk.Canvas):
    """Title bar drawn on one canvas over the theme's backdrop art: mascot orb, app name, page tabs, game status
    and the Scan button.

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
        m = appearance.fx()
        key = (w, h, m['backdrop'], tuple(sorted((k, v) for k, v in t.items() if isinstance(v, str))))
        if key == self._bg_key: return
        image = gloss.backdrop(m['backdrop'], (w, h), t, base=t['background'], energy=.35)
        sheen = gloss._vgradient((w, h // 2), (255, 255, 255, 26 if not t['light'] else 80), (255, 255, 255, 0))
        image.alpha_composite(sheen)
        self._bg = ImageTk.PhotoImage(image, master=self); self._bg_key = key

    def redraw(self, t):
        self.t = t; self.delete('all'); self.hits = []
        f = appearance.fonts(self); w = max(self.winfo_width(), 1); dark = not t['light']
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
                color = t['accent'] if active else gloss.shade(t['raised'], .12 if dark else -.03)
                img = ImageTk.PhotoImage(_plate(tw, ph, color, dark=dark), master=self)
                self._pills.append(img); self.create_image(x, y0, image=img, anchor='nw')
            ink = t['accent_text'] if active else (t['text'] if self.hover == ('page', key) else t['muted'])
            self.create_text(x + tw / 2, h / 2, text=label, fill=ink, font=f['nav'])
            self.hits.append(((x, y0, x + tw, y0 + ph), ('page', key))); x += tw + 6
        # right side: scan button then game status
        label, enabled = self.cb['scan']()
        bw = _measure(f['strong'], label) + 34; bh = _line(f['strong']) + 14; bx = w - 14 - bw; by = (h - bh) / 2
        state = 'disabled' if not enabled else 'hover' if self.hover == ('scan',) else 'normal'
        img = ImageTk.PhotoImage(_plate(bw, bh, gloss.shade(t['raised'], .14 if dark else -.02), state, dark=dark), master=self)
        self._pills.append(img); self.create_image(bx, by, image=img, anchor='nw')
        self.create_text(bx + bw / 2, h / 2, text=label, fill=t['text'] if enabled else t['faint'], font=f['strong'])
        if enabled: self.hits.append(((bx, by, bx + bw, by + bh), ('scan',)))
        ok, game = self.cb['game']()
        gx = bx - 16
        self.create_text(gx, h / 2, text=game, anchor='e', fill=t['text'] if self.hover == ('game',) else t['muted'], font=f['small'])
        gw = _measure(f['small'], game)
        self.create_oval(gx - gw - 16, h / 2 - 4, gx - gw - 8, h / 2 + 4, fill=t['accent2'] if ok else t['warn'], outline='')
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
