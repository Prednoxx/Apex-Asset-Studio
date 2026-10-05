"""Canvas-drawn HUD pieces for the cybercore look: glitch type, hazard stripes, tags, brackets, neon buttons.

Every widget here has redraw(tokens); call refresh(app, tokens) after a palette change.
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
    """Diagonal warning stripes."""
    def __init__(self, master, height=6, color='accent', on='background', step=14, **kwargs):
        super().__init__(master, on=on, height=height, **kwargs)
        self.color = color; self.step = step

    def redraw(self, t):
        self.t = t; self.delete('all'); self.configure(background=t[self.on])
        w, h = max(self.winfo_width(), 1), int(self.cget('height'))
        x = -h
        while x < w + h:
            self.create_polygon(x, h, x + h, 0, x + h + self.step/2, 0, x + self.step/2, h, fill=t[self.color], outline='')
            x += self.step


class GlitchText(_Base):
    """Text with a chromatic-aberration split (secondary neon left, primary neon right)."""
    def __init__(self, master, text, font='brand', jp=None, on='background', pad=(0, 0), **kwargs):
        super().__init__(master, on=on, **kwargs)
        self.text = text; self.font_key = font; self.jp = jp; self.pad = pad
        f = self.fonts(); probe = tk.font.Font(font=f[font])
        width = probe.measure(text) + 8 + pad[0]*2
        height = probe.metrics('linespace') + 4 + pad[1]*2
        if jp:
            jfont = tk.font.Font(font=f['jp'])
            width = max(width, jfont.measure(jp) + 8); height += jfont.metrics('linespace')
        self.configure(width=width, height=height)

    def set_text(self, text):
        self.text = text
        if self.t: self.redraw(self.t)

    def redraw(self, t):
        self.t = t; self.delete('all'); self.configure(background=t[self.on])
        f = self.fonts(); x, y = 3 + self.pad[0], 1 + self.pad[1]
        self.create_text(x - 2, y, text=self.text, anchor='nw', fill=t['accent2'], font=f[self.font_key])
        self.create_text(x + 2, y + 1, text=self.text, anchor='nw', fill=t['accent'], font=f[self.font_key])
        self.create_text(x, y, text=self.text, anchor='nw', fill=t['text'], font=f[self.font_key])
        if self.jp:
            line = tk.font.Font(font=f[self.font_key]).metrics('linespace')
            self.create_text(x + 1, y + line, text=self.jp, anchor='nw', fill=t['muted'], font=f['jp'])


class SectionTag(_Base):
    """■ LABEL ／ 日本語 ──────────── with tick marks, sized to its container width."""
    def __init__(self, master, text, jp='', on='surface', **kwargs):
        super().__init__(master, on=on, height=20, **kwargs)
        self.text = text.upper(); self.jp = jp

    def redraw(self, t):
        self.t = t; self.delete('all'); self.configure(background=t[self.on])
        f = self.fonts(); w = max(self.winfo_width(), 1)
        label = tk.font.Font(font=f['section']).measure(self.text)
        x1 = label + 20
        self.create_polygon(0, 2, x1, 2, x1 - 6, 18, 0, 18, fill=t['accent2'], outline='')
        self.create_text(7, 10, text=self.text, anchor='w', fill=t['accent2_text'], font=f['section'])
        x = x1 + 8
        if self.jp:
            self.create_text(x, 10, text=self.jp, anchor='w', fill=t['muted'], font=f['jp'])
            x += tk.font.Font(font=f['jp']).measure(self.jp) + 10
        if x < w - 10:
            self.create_line(x, 10, w, 10, fill=t['border'])
            for tick in range(int(w) - 2, int(x) + 20, -24):
                self.create_line(tick, 7, tick, 13, fill=t['border'])
            self.create_rectangle(w - 6, 8, w - 2, 12, fill=t['accent'], outline='')


class NeonButton(_Base):
    """Chamfered primary action button with hazard stripes. Mimics ttk's state()/instate()."""
    def __init__(self, master, text, command=None, jp='', on='surface', width=210, height=40, **kwargs):
        super().__init__(master, on=on, width=width, height=height, cursor='hand2', **kwargs)
        self.text = text.upper(); self.jp = jp; self.command = command
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
        f = self.fonts(); w, h = max(self.winfo_width(), 1), max(self.winfo_height(), 1); cut = 10
        shape = [cut, 0, w, 0, w, h - cut, w - cut, h, 0, h, 0, cut]
        if self._disabled:
            self.create_polygon(*shape, fill=t['surface'], outline=t['border'])
            text_color, stripe = t['faint'], t['border']
        else:
            fill = t['accent2'] if self._hover else t['accent']
            if self._pressed: fill = t['accent']
            self.create_polygon(*shape, fill=fill, outline='')
            text_color = t['accent2_text'] if self._hover else t['accent_text']
            stripe = text_color
        # stripes on the right end
        sx = w - 44
        for i in range(4):
            x = sx + i * 9
            self.create_polygon(x, h - 8, x + 4, h - 8, x + 8, 8, x + 4, 8, fill=stripe, outline='')
        self.create_text(16, h / 2, text=self.text, anchor='w', fill=text_color, font=f['nav'])
        if self.jp:
            label = tk.font.Font(font=f['nav']).measure(self.text)
            self.create_text(16 + label + 8, h / 2 + 1, text=self.jp, anchor='w', fill=text_color, font=f['jp'])


class Bracket(_Base):
    """One HUD corner bracket. corner is 'nw', 'ne', 'sw' or 'se'."""
    def __init__(self, master, corner, size=16, color='accent2', on=None, **kwargs):
        on = on or ('viewport_top' if 'n' in corner else 'viewport')
        super().__init__(master, on=on, width=size, height=size, **kwargs)
        self.corner = corner; self.size = size; self.color = color

    def redraw(self, t):
        self.t = t; self.delete('all'); self.configure(background=t[self.on])
        s = self.size - 1; c = t[self.color]
        x = 0 if 'w' in self.corner else s; y = 0 if 'n' in self.corner else s
        dx = 1 if 'w' in self.corner else -1; dy = 1 if 'n' in self.corner else -1
        self.create_line(x, y + dy*s, x, y, x + dx*s, y, fill=c, width=3)


class Signal(_Base):
    """Centered viewport placeholder: glitch headline, Japanese subtitle and a message."""
    def __init__(self, master, on='viewport_mid', **kwargs):
        super().__init__(master, on=on, width=420, height=130, **kwargs)
        self.headline = 'NO SIGNAL'; self.jp = '信号なし'; self.message = ''

    def show(self, message, headline='NO SIGNAL', jp='信号なし'):
        self.message = message; self.headline = headline; self.jp = jp
        if self.t: self.redraw(self.t)

    def redraw(self, t):
        self.t = t; self.delete('all'); self.configure(background=t[self.on])
        f = self.fonts(); cx = 210
        for dx, dy, color in ((-3, 0, t['accent2']), (3, 1, t['accent']), (0, 0, t['text'])):
            self.create_text(cx + dx, 34 + dy, text=self.headline, fill=color, font=f['placeholder'])
        # glitch slices
        for y, x0, x1 in ((24, 120, 170), (40, 250, 300)):
            self.create_rectangle(x0, y, x1, y + 2, fill=t['accent'], outline='')
        self.create_text(cx, 70, text=self.jp, fill=t['muted'], font=f['jp'])
        self.create_text(cx, 98, text=self.message, fill=t['muted'], font=f['body'], width=400, justify='center')
