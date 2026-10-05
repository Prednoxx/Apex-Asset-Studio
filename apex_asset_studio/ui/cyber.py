"""Canvas-drawn decoration that changes with the active style: title type, ornament strips, section tags,
viewport brackets, the primary action button and the empty-viewport placeholder.

Every widget here has redraw(tokens); call refresh(app, tokens) after a style or palette change.
"""
import tkinter as tk
import tkinter.font
from . import appearance


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
        width = _measure(f[self.font_key], self.shown()) + 10 + self.pad[0]*2
        height = _line(f[self.font_key]) + 4 + self.pad[1]*2
        if self.jp:
            width = max(width, _measure(f['jp'], self.jp) + 8); height += _line(f['jp'])
        self.configure(width=width, height=height)

    def shown(self):
        return self.text.upper() if appearance.fx()['upper'] else self.text

    def redraw(self, t):
        self.t = t; self._resize(); self.delete('all'); self.configure(background=t[self.on])
        f = self.fonts(); x, y = 3 + self.pad[0], 1 + self.pad[1]
        styled_text(self, x, y, self.shown(), f[self.font_key], t)
        if self.jp:
            self.create_text(x + 1, y + _line(f[self.font_key]), text=self.jp, anchor='nw', fill=t['muted'], font=f['jp'])


class SectionTag(_Base):
    """Section heading with a Japanese sub-label and a rule that fills the remaining width."""
    def __init__(self, master, text, jp='', on='surface', **kwargs):
        super().__init__(master, on=on, height=22, **kwargs)
        self.text = text; self.jp = jp

    def redraw(self, t):
        self.t = t; self.delete('all'); self.configure(background=t[self.on])
        f = self.fonts(); fx = appearance.fx(); w = max(self.winfo_width(), 1); h = 22; mid = h / 2
        text = self.text.upper() if fx['upper'] else self.text
        label = _measure(f['section'], text)
        kind = fx['tag']
        if kind == 'slant':
            x1 = label + 20
            self.create_polygon(0, 3, x1, 3, x1 - 6, h - 3, 0, h - 3, fill=t['accent2'], outline='')
            self.create_text(7, mid, text=text, anchor='w', fill=t['accent2_text'], font=f['section'])
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
        x = x1 + 8
        if self.jp:
            self.create_text(x, mid, text=self.jp, anchor='w', fill=t['muted'], font=f['jp'])
            x += _measure(f['jp'], self.jp) + 10
        if x >= w - 10: return
        if kind in ('slant', 'box'):
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
        self.text = text; self.jp = jp; self.command = command
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
        w, h = max(self.winfo_width(), 1), max(self.winfo_height(), 1)
        text = self.text.upper() if fx['upper'] else self.text
        if self._disabled:
            fill, edge, ink = t['surface'], t['border'], t['faint']
        else:
            fill = t['accent2'] if self._hover and not self._pressed else t['accent']
            edge = fill; ink = t['accent2_text'] if self._hover and not self._pressed else t['accent_text']
        if kind == 'pill':
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
        if self.jp:
            self.create_text(tx + _measure(f['nav'], text) + 8, cy + 1, text=self.jp, anchor='w', fill=ink, font=f['jp'])


class Bracket(_Base):
    """One viewport corner mark. corner is 'nw', 'ne', 'sw' or 'se'."""
    def __init__(self, master, corner, size=16, color='accent2', on=None, **kwargs):
        on = on or ('viewport_top' if 'n' in corner else 'viewport')
        super().__init__(master, on=on, width=size, height=size, **kwargs)
        self.corner = corner; self.size = size; self.color = color

    def redraw(self, t):
        self.t = t; self.delete('all'); self.configure(background=t[self.on])
        s = self.size - 1; c = t[self.color]; kind = appearance.fx()['tag']
        x = 0 if 'w' in self.corner else s; y = 0 if 'n' in self.corner else s
        dx = 1 if 'w' in self.corner else -1; dy = 1 if 'n' in self.corner else -1
        if kind == 'pill':
            _star(self, s/2, s/2, s/2 - 1, c)
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
        styled_text(self, cx, 34, headline, f['placeholder'], t, anchor='center',
                    fill=t['text'] if fx['glitch'] else t['accent'], glitch_amount=3)
        if fx['glitch']:
            for y, x0, x1 in ((24, 130, 180), (40, 260, 310)):
                self.create_rectangle(x0, y, x1, y + 2, fill=t['accent'], outline='')
        self.create_text(cx, 70, text=jp, fill=t['muted'], font=f['jp'])
        self.create_text(cx, 98, text=self.message, fill=t['muted'], font=f['body'], width=420, justify='center')
