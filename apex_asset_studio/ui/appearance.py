"""Validated, atomically saved appearance preferences and the cybercore ttk theme."""
import json
import re
from pathlib import Path

SETTINGS_VERSION = 3

# accent = primary neon (selection, primary actions); accent2 = secondary neon (data, HUD lines).
PRESETS = {
    'Cybercore': dict(background='#07060b', surface='#0d0b14', raised='#171224', border='#2b2142',
                      text='#f1ebff', muted='#8d7fae', accent='#ff2e88', accent2='#00e5ff', viewport='#05040a'),
    'Unit-02': dict(background='#0a0606', surface='#120b0b', raised='#1f1212', border='#43201b',
                    text='#fff0e6', muted='#b08a7a', accent='#ff3b1f', accent2='#ffb000', viewport='#070404'),
    'Unit-01': dict(background='#08060d', surface='#0f0b17', raised='#1a1428', border='#33244d',
                    text='#efe9ff', muted='#9184b0', accent='#9b5cff', accent2='#a6ff3a', viewport='#060409'),
    'Ghost': dict(background='#04080d', surface='#08101a', raised='#0f1b2a', border='#1c3047',
                  text='#e6f6ff', muted='#7d98b0', accent='#2ef2c4', accent2='#4aa8ff', viewport='#03060a'),
}
DEFAULT_PRESET = 'Cybercore'
COLOR_LABELS = (
    ('background', 'Window chrome'), ('surface', 'Panels & tables'), ('raised', 'Buttons & inputs'),
    ('border', 'Grid lines'), ('text', 'Text'), ('muted', 'Secondary text'), ('accent', 'Primary neon'),
    ('accent2', 'Secondary neon'), ('viewport', '3D preview background'),
)
LAYOUTS = ('Classic Columns', 'Preview Focus', 'Stacked Workspace')
RARITY = {'common': '#a9a3b8', 'rare': '#4cc9f0', 'epic': '#c77dff', 'legendary': '#ffc53d',
          'mythic': '#ff4d6d', 'heirloom': '#ff4d6d', 'iconic': '#ff4d6d'}
_HEX = re.compile(r'#[0-9a-fA-F]{6}')


def normalize(value):
    value = value if isinstance(value, dict) else {}
    current = value.get('version') == SETTINGS_VERSION
    preset = value.get('preset', DEFAULT_PRESET) if current else DEFAULT_PRESET
    if preset not in PRESETS and preset != 'Custom': preset = DEFAULT_PRESET
    colors = dict(PRESETS.get(preset, PRESETS[DEFAULT_PRESET]))
    supplied = value.get('colors', {})
    if preset == 'Custom' and isinstance(supplied, dict):
        for key in colors:
            color = supplied.get(key)
            if isinstance(color, str) and _HEX.fullmatch(color): colors[key] = color.lower()
    layout = value.get('layout', LAYOUTS[0])
    return dict(version=SETTINGS_VERSION, preset=preset, colors=colors,
                layout=layout if layout in LAYOUTS else LAYOUTS[0],
                mascot_path=value.get('mascot_path', '') if isinstance(value.get('mascot_path', ''), str) else '',
                show_mascot=value.get('show_mascot', True) is not False,
                scanlines=value.get('scanlines', True) is not False)


def load(path):
    try: return normalize(json.loads(Path(path).read_text(encoding='utf-8')))
    except (OSError, ValueError): return normalize({})


def save(path, value):
    path = Path(path); path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix('.tmp')
    temp.write_text(json.dumps(normalize(value), indent=2), encoding='utf-8')
    temp.replace(path)


def _rgb(color): return [int(color[i:i+2], 16) for i in (1, 3, 5)]


def mix(a, b, amount):
    """Blend color a over b by amount (0..1)."""
    return '#%02x%02x%02x' % tuple(round(x*amount + y*(1-amount)) for x, y in zip(_rgb(a), _rgb(b)))


def luminance(color):
    def channel(v):
        v /= 255
        return v/12.92 if v <= .04045 else ((v+.055)/1.055)**2.4
    r, g, b = (channel(v) for v in _rgb(color))
    return .2126*r + .7152*g + .0722*b


def tokens(colors):
    """Full token set including derived values."""
    t = dict(PRESETS[DEFAULT_PRESET]); t.update(colors)
    t['selection'] = t['accent']
    t['selection_text'] = '#07060b' if luminance(t['accent']) > .18 else '#ffffff'
    t['accent_text'] = t['selection_text']
    t['accent2_text'] = '#07060b' if luminance(t['accent2']) > .18 else '#ffffff'
    t['hover'] = mix(t['accent2'], t['raised'], .10)
    t['glow'] = mix(t['accent'], t['surface'], .22)
    t['dim2'] = mix(t['accent2'], t['surface'], .45)
    t['dim'] = mix(t['accent'], t['surface'], .45)
    t['faint'] = mix(t['muted'], t['surface'], .55)
    t['warn'] = '#ffc53d'
    t['good'] = t['accent2']
    t['viewport_top'] = mix('#ffffff', t['viewport'], .03)
    t['viewport_mid'] = mix('#ffffff', t['viewport'], .018)
    return t


_FONT_CACHE = {}


def fonts(app):
    if _FONT_CACHE: return _FONT_CACHE
    from tkinter import font
    families = set(font.families(app))
    def pick(*names):
        return next((n for n in names if n in families), names[-1])
    ui = pick('Bahnschrift', 'Segoe UI Variable Text', 'Segoe UI', 'Noto Sans', 'DejaVu Sans', 'TkDefaultFont')
    head = pick('Bahnschrift SemiBold SemiConden', 'Bahnschrift SemiBold Condensed', 'Bahnschrift SemiBold',
                'DejaVu Sans Condensed', ui)
    head_bold = () if head.startswith('Bahnschrift') else ('bold',)
    mono = pick('Cascadia Mono', 'Consolas', 'JetBrains Mono', 'DejaVu Sans Mono', 'TkFixedFont')
    jp = pick('Yu Gothic UI', 'Meiryo UI', 'Meiryo', 'Noto Sans CJK JP', 'MS Gothic', ui)
    mincho = pick('Yu Mincho', 'MS Mincho', 'Noto Serif CJK JP', jp)
    _FONT_CACHE.update(
        body=(ui, 10), small=(ui, 9), strong=(head, 11, *head_bold),
        title=(head, 20, *head_bold), brand=(head, 15, *head_bold),
        section=(head, 9, *head_bold), mono=(mono, 9), mono_small=(mono, 8), data=(mono, 9),
        display=(head, 40, *head_bold), stat=(head, 24, *head_bold), nav=(head, 11, *head_bold),
        jp=(jp, 8), jp_big=(mincho, 30, 'bold'), jp_title=(mincho, 13, 'bold'), placeholder=(head, 26, *head_bold),
    )
    return _FONT_CACHE


def _png(image):
    import base64, io
    buffer = io.BytesIO(); image.save(buffer, 'PNG')
    return base64.b64encode(buffer.getvalue())


def _images(app, c):
    """Checkbox, radio and slider images (angular, neon), regenerated for each palette."""
    import tkinter as tk
    from PIL import Image, ImageDraw
    s = 4
    def rgb(color, alpha=255): return (*_rgb(color), alpha)
    def canvas(w, h, bg=None): return Image.new('RGBA', (w*s, h*s), (0, 0, 0, 0) if bg is None else rgb(bg))
    def done(image, w, h): return image.resize((w, h), Image.Resampling.LANCZOS)
    def chamfer(x0, y0, x1, y1, cut):
        return [(x0+cut, y0), (x1, y0), (x1, y1-cut), (x1-cut, y1), (x0, y1), (x0, y0+cut)]
    out = {}
    for key, fill, edge, mark in (('check_off', c['raised'], c['muted'], None), ('check_on', c['accent'], c['accent'], c['accent_text']),
                                  ('check_off_dis', c['surface'], c['border'], None), ('check_on_dis', c['border'], c['border'], c['faint'])):
        im = canvas(24, 16); d = ImageDraw.Draw(im)
        d.polygon([(x*s, y*s) for x, y in chamfer(1, 1, 15, 15, 4)], fill=rgb(fill), outline=rgb(edge), width=int(1.25*s))
        if mark: d.line([(4.2*s, 8.4*s), (6.8*s, 11*s), (11.8*s, 5.2*s)], fill=rgb(mark), width=int(2.1*s))
        out[key] = done(im, 24, 16)
    for key, fill, edge, dot in (('radio_off', c['raised'], c['muted'], None), ('radio_on', c['raised'], c['accent'], c['accent'])):
        im = canvas(24, 16); d = ImageDraw.Draw(im)
        d.polygon([(8*s, 1*s), (15*s, 8*s), (8*s, 15*s), (1*s, 8*s)], fill=rgb(fill), outline=rgb(edge), width=int(1.25*s))
        if dot: d.polygon([(8*s, 4.5*s), (11.5*s, 8*s), (8*s, 11.5*s), (4.5*s, 8*s)], fill=rgb(dot))
        out[key] = done(im, 24, 16)
    for key, color in (('thumb', c['accent2']), ('thumb_active', c['accent']), ('thumb_dis', c['faint'])):
        im = canvas(10, 18); d = ImageDraw.Draw(im)
        d.polygon([(1*s, 1*s), (9*s-1, 1*s), (9*s-1, 13*s), (5*s, 17*s-1), (1*s, 13*s)], fill=rgb(color))
        out[key] = done(im, 10, 18)
    for key, bg in (('track', c['background']), ('track_panel', c['surface'])):
        im = canvas(12, 18, bg); d = ImageDraw.Draw(im)
        d.rectangle((0, 8*s, 12*s-1, 10*s-1), fill=rgb(c['border']))
        out[key] = done(im, 12, 18)
    names = {}; objects = getattr(app, '_aas_image_objects', {})
    for key, image in out.items():
        name = f'aas_{key}'
        if key in objects: objects[key].configure(data=_png(image))
        else: objects[key] = tk.PhotoImage(name=name, data=_png(image), master=app)
        names[key] = name
    app._aas_image_objects = objects  # Tk deletes images whose Python object is collected
    return names


_ELEMENTS = set()


def _elements(style, n):
    if 'check' in _ELEMENTS: return
    style.element_create('AAS.check', 'image', n['check_off'],
                         ('disabled', 'selected', n['check_on_dis']), ('disabled', n['check_off_dis']),
                         ('selected', n['check_on']), width=24, sticky='w')
    style.element_create('AAS.radio', 'image', n['radio_off'], ('selected', n['radio_on']), width=24, sticky='w')
    style.element_create('AAS.trough', 'image', n['track'], border=(5, 0, 5, 0), sticky='ew')
    style.element_create('AASPanel.trough', 'image', n['track_panel'], border=(5, 0, 5, 0), sticky='ew')
    style.element_create('AAS.slider', 'image', n['thumb'], ('disabled', n['thumb_dis']),
                         ('pressed', n['thumb_active']), ('active', n['thumb_active']))
    _ELEMENTS.add('check')


def apply(app, value):
    from tkinter import ttk
    import tkinter as tk
    c = tokens(value['colors']); f = fonts(app)
    style = ttk.Style(app); style.theme_use('clam')
    _elements(style, _images(app, c))
    app.configure(background=c['background'])

    style.configure('.', background=c['background'], foreground=c['text'], font=f['body'],
                    bordercolor=c['border'], lightcolor=c['background'], darkcolor=c['background'],
                    troughcolor=c['background'], focuscolor=c['accent2'], selectbackground=c['accent'],
                    selectforeground=c['accent_text'], insertcolor=c['accent2'], fieldbackground=c['raised'])
    style.map('.', foreground=[('disabled', c['faint'])])

    style.configure('TFrame', background=c['background'], borderwidth=0)
    style.configure('Panel.TFrame', background=c['surface'])
    style.configure('Hairline.TFrame', background=c['border'])
    style.configure('Glow.TFrame', background=c['dim2'])
    style.configure('Card.TFrame', background=c['raised'])

    for prefix, bg in (('', c['background']), ('Panel.', c['surface']), ('Card.', c['raised'])):
        style.configure(f'{prefix}TLabel', background=bg, foreground=c['text'], font=f['body'])
        style.configure(f'Muted.{prefix}TLabel', foreground=c['muted'])
        style.configure(f'Small.{prefix}TLabel', foreground=c['muted'], font=f['small'])
        style.configure(f'Title.{prefix}TLabel', font=f['title'])
        style.configure(f'Strong.{prefix}TLabel', font=f['strong'])
        style.configure(f'Section.{prefix}TLabel', foreground=c['accent2'], font=f['section'])
        style.configure(f'Data.{prefix}TLabel', foreground=c['accent2'], font=f['data'])
        style.configure(f'JP.{prefix}TLabel', foreground=c['muted'], font=f['jp'])
        style.configure(f'Warn.{prefix}TLabel', foreground=c['warn'], font=f['small'])
        style.configure(f'{prefix}TCheckbutton', background=bg, foreground=c['text'], font=f['body'], focusthickness=0, padding=(0, 3))
        style.map(f'{prefix}TCheckbutton', background=[('active', bg)], foreground=[('disabled', c['faint']), ('active', c['accent2'])])
        style.layout(f'{prefix}TCheckbutton', [('Checkbutton.padding', {'sticky': 'nswe', 'children': [
            ('AAS.check', {'side': 'left', 'sticky': ''}), ('Checkbutton.label', {'side': 'left', 'sticky': 'nswe', 'expand': '1'})]})])
        style.configure(f'{prefix}TRadiobutton', background=bg, foreground=c['text'], font=f['body'], focusthickness=0, padding=(0, 3))
        style.map(f'{prefix}TRadiobutton', background=[('active', bg)], foreground=[('active', c['accent2'])])
        style.layout(f'{prefix}TRadiobutton', [('Radiobutton.padding', {'sticky': 'nswe', 'children': [
            ('AAS.radio', {'side': 'left', 'sticky': ''}), ('Radiobutton.label', {'side': 'left', 'sticky': 'nswe', 'expand': '1'})]})])
    style.configure('Tag.TLabel', background=c['accent2'], foreground=c['accent2_text'], font=f['mono_small'])
    style.configure('Stat.Card.TLabel', font=f['stat'], foreground=c['accent2'])
    style.configure('Placeholder.TLabel', background=c['raised'], foreground=c['faint'], font=f['body'])
    style.configure('Status.TLabel', foreground=c['muted'], font=f['mono'])
    style.configure('Clock.TLabel', foreground=c['accent2'], font=f['mono'])
    style.configure('Path.TLabel', foreground=c['muted'], font=f['mono_small'])
    style.configure('Dot.TLabel', foreground=c['accent2'], font=f['small'])
    style.configure('DotOff.TLabel', foreground=c['warn'], font=f['small'])

    # Buttons: dark plates with neon edges
    plate = dict(bordercolor=c['border'], lightcolor=c['raised'], darkcolor=c['raised'])
    style.configure('TButton', background=c['raised'], foreground=c['text'], padding=(12, 5), relief='flat',
                    borderwidth=1, focusthickness=0, anchor='center', font=f['strong'], **plate)
    style.map('TButton', background=[('disabled', c['surface']), ('pressed', c['dim2']), ('active', c['hover'])],
              foreground=[('disabled', c['faint']), ('active', c['accent2'])],
              bordercolor=[('disabled', c['border']), ('active', c['accent2']), ('focus', c['dim2'])],
              lightcolor=[('active', c['hover'])], darkcolor=[('active', c['hover'])])
    style.configure('Accent.TButton', background=c['accent'], foreground=c['accent_text'], font=f['strong'],
                    bordercolor=c['accent'], lightcolor=c['accent'], darkcolor=c['accent'], padding=(16, 7))
    style.map('Accent.TButton',
              background=[('disabled', c['surface']), ('active', c['accent2'])],
              foreground=[('disabled', c['faint']), ('active', c['accent2_text'])],
              bordercolor=[('disabled', c['border']), ('active', c['accent2'])],
              lightcolor=[('disabled', c['surface']), ('active', c['accent2'])],
              darkcolor=[('disabled', c['surface']), ('active', c['accent2'])])
    for name, bg in (('Ghost.TButton', c['background']), ('Ghost.Panel.TButton', c['surface'])):
        style.configure(name, background=bg, bordercolor=bg, lightcolor=bg, darkcolor=bg, foreground=c['muted'],
                        padding=(8, 4), font=f['section'])
        style.map(name, background=[('active', bg)], foreground=[('disabled', c['faint']), ('active', c['accent2'])],
                  bordercolor=[('active', bg)], lightcolor=[('active', bg)], darkcolor=[('active', bg)])
    style.configure('Nav.TButton', background=c['background'], bordercolor=c['background'], lightcolor=c['background'],
                    darkcolor=c['background'], foreground=c['muted'], padding=(12, 5), font=f['nav'])
    style.map('Nav.TButton', foreground=[('active', c['accent2'])], background=[('active', c['background'])],
              bordercolor=[('active', c['dim2'])], lightcolor=[('active', c['background'])], darkcolor=[('active', c['background'])])
    style.configure('NavActive.TButton', background=c['accent'], bordercolor=c['accent'], lightcolor=c['accent'],
                    darkcolor=c['accent'], foreground=c['accent_text'], padding=(12, 5), font=f['nav'])
    style.map('NavActive.TButton', background=[('active', c['accent'])], foreground=[('active', c['accent_text'])])

    # Inputs
    field = dict(fieldbackground=c['raised'], foreground=c['text'], insertcolor=c['accent2'], padding=(8, 5),
                 bordercolor=c['border'], lightcolor=c['raised'], darkcolor=c['raised'], font=f['body'])
    style.configure('TEntry', **field)
    style.map('TEntry', bordercolor=[('focus', c['accent2'])], lightcolor=[('focus', c['raised'])],
              fieldbackground=[('disabled', c['surface'])], foreground=[('disabled', c['faint'])])
    style.configure('TSpinbox', arrowcolor=c['accent2'], background=c['raised'], **field)
    style.configure('TCombobox', arrowcolor=c['accent2'], background=c['raised'], arrowsize=13, **field)
    style.map('TCombobox', fieldbackground=[('readonly', c['raised']), ('disabled', c['surface'])],
              background=[('active', c['hover']), ('readonly', c['raised'])],
              foreground=[('disabled', c['faint']), ('readonly', c['text'])],
              bordercolor=[('focus', c['accent2'])], arrowcolor=[('disabled', c['faint'])],
              selectbackground=[('readonly', c['raised'])], selectforeground=[('readonly', c['text'])])
    app.option_add('*TCombobox*Listbox.background', c['raised'])
    app.option_add('*TCombobox*Listbox.foreground', c['text'])
    app.option_add('*TCombobox*Listbox.selectBackground', c['accent'])
    app.option_add('*TCombobox*Listbox.selectForeground', c['accent_text'])
    app.option_add('*TCombobox*Listbox.font', f['body'])
    app.option_add('*TCombobox*Listbox.borderWidth', 0)

    # Tables and trees: solid neon selection bar
    for name, bg in (('Treeview', c['surface']), ('Sidebar.Treeview', c['background'])):
        style.configure(name, background=bg, fieldbackground=bg, foreground=c['text'], rowheight=29,
                        borderwidth=0, relief='flat', bordercolor=bg, lightcolor=bg, darkcolor=bg, font=f['body'], indent=14)
        style.map(name, background=[('selected', c['accent'])], foreground=[('selected', c['accent_text'])])
        style.layout(name, [('Treeview.treearea', {'sticky': 'nswe'})])
    style.configure('Treeview.Heading', background=c['surface'], foreground=c['accent2'], relief='flat', padding=(10, 7),
                    font=f['mono_small'], bordercolor=c['border'], lightcolor=c['surface'], darkcolor=c['surface'])
    style.map('Treeview.Heading', background=[('active', c['raised'])], foreground=[('active', c['text'])])

    style.configure('TNotebook', background=c['background'], borderwidth=0, tabmargins=(0, 0, 0, 0),
                    bordercolor=c['border'], lightcolor=c['background'], darkcolor=c['background'])
    style.configure('Pages.TNotebook', background=c['background'], borderwidth=0, padding=0,
                    bordercolor=c['background'], lightcolor=c['background'], darkcolor=c['background'])
    style.layout('Pages.TNotebook', [('Notebook.client', {'sticky': 'nswe'})])
    style.layout('Pages.TNotebook.Tab', [])
    style.configure('TNotebook.Tab', background=c['background'], foreground=c['muted'], padding=(14, 6),
                    borderwidth=0, font=f['nav'], bordercolor=c['background'], lightcolor=c['background'])
    style.map('TNotebook.Tab', background=[('selected', c['accent']), ('active', c['background'])],
              foreground=[('selected', c['accent_text']), ('active', c['accent2'])],
              bordercolor=[('selected', c['accent'])], lightcolor=[('selected', c['accent'])],
              expand=[('selected', (0, 0, 0, 0))])

    for orient in ('Vertical', 'Horizontal'):
        style.layout(f'{orient}.TScrollbar', [(f'{orient}.Scrollbar.trough', {'sticky': 'nswe', 'children': [
            (f'{orient}.Scrollbar.thumb', {'expand': '1', 'sticky': 'nswe'})]})])
        style.configure(f'{orient}.TScrollbar', background=c['border'], troughcolor=c['surface'], borderwidth=0,
                        bordercolor=c['surface'], lightcolor=c['border'], darkcolor=c['border'], arrowsize=7, gripcount=0, relief='flat')
        style.map(f'{orient}.TScrollbar', background=[('active', c['accent2'])], lightcolor=[('active', c['accent2'])], darkcolor=[('active', c['accent2'])])
    style.configure('Sidebar.Vertical.TScrollbar', troughcolor=c['background'], bordercolor=c['background'])
    style.configure('TSeparator', background=c['border'])
    style.configure('Horizontal.TProgressbar', background=c['accent'], troughcolor=c['raised'], bordercolor=c['raised'],
                    lightcolor=c['accent'], darkcolor=c['accent'], thickness=6)
    for prefix, bg in (('', c['background']), ('Panel.', c['surface'])):
        style.layout(f'{prefix}Horizontal.TScale', [('AASPanel.trough' if prefix else 'AAS.trough', {'sticky': 'ew', 'children': [
            ('AAS.slider', {'side': 'left', 'sticky': ''})]})])
        style.configure(f'{prefix}Horizontal.TScale', background=bg, sliderlength=10)
    style.configure('TPanedwindow', background=c['border'])
    style.configure('Sash', sashthickness=1, background=c['border'], gripcount=0)

    def visit(widget):
        if isinstance(widget, tk.Text):
            flush = getattr(widget, 'flush', False)
            widget.configure(background=c['surface'], foreground=c[getattr(widget, 'tone', 'text')],
                             insertbackground=c['accent2'], selectbackground=c['accent'], selectforeground=c['accent_text'],
                             borderwidth=0, highlightthickness=0, relief='flat', padx=0 if flush else 12, pady=0 if flush else 10)
        elif isinstance(widget, tk.Canvas) and not hasattr(widget, 'redraw'):
            widget.configure(background=c['background'], highlightthickness=0)
        elif isinstance(widget, tk.Toplevel):
            widget.configure(background=c['background'])
        for child in widget.winfo_children(): visit(child)
    visit(app)
    app.preview.set_palette(c['viewport'], c['text'], c['muted'], grid=c['accent'], hud=c['accent2'],
                            scanlines=value.get('scanlines', True))
    return c
