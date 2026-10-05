"""Validated, atomically saved appearance preferences and the cybercore ttk theme."""
import json
import re
from pathlib import Path

SETTINGS_VERSION = 4

# A style is a full aesthetic: palette, typefaces and decoration ("fx").
# accent = primary color (selection, main action); accent2 = secondary (data, HUD lines, tags).
def _F(candidates, size, weight='normal'):
    return (tuple(candidates), size, weight)


_MINCHO = ('Yu Mincho', 'MS Mincho', 'Noto Serif CJK JP')
_JP = ('Yu Gothic UI', 'Meiryo UI', 'Meiryo', 'Noto Sans CJK JP')
_COND = ('Bahnschrift SemiBold SemiConden', 'Bahnschrift SemiBold Condensed', 'Bahnschrift SemiBold', 'DejaVu Sans Condensed')


def _fontset(ui, head, mono, ui_size=10, head_scale=1.0, mono_size=9, head_weight='normal', title_size=20,
             display_size=40, jp=_JP, jp_size=8):
    h = lambda n: max(6, round(n*head_scale))
    return dict(
        body=_F(ui, ui_size), small=_F(ui, ui_size-1), strong=_F(head, h(11), head_weight),
        title=_F(head, title_size, head_weight), brand=_F(head, h(15), head_weight), section=_F(head, h(9), head_weight),
        nav=_F(head, h(11), head_weight), stat=_F(head, h(24), head_weight), placeholder=_F(head, h(26), head_weight),
        display=_F(head, display_size, head_weight), mono=_F(mono, mono_size), mono_small=_F(mono, mono_size-1),
        data=_F(mono, mono_size), jp=_F(jp, jp_size), jp_big=_F(_MINCHO, 30, 'bold'), jp_title=_F(_MINCHO, 13, 'bold'))


STYLES = {
    'Neon Cybercore': dict(
        blurb='Neon pink and cyan, glitch type, warning stripes, synthwave grid.',
        colors=dict(background='#07060b', surface='#0d0b14', raised='#171224', border='#2b2142', text='#f1ebff',
                    muted='#8d7fae', accent='#ff2e88', accent2='#00e5ff', viewport='#05040a'),
        fonts=_fontset(('Rajdhani Medium', 'Rajdhani', 'Bahnschrift', 'Segoe UI'), ('Rajdhani',) + _COND,
                       ('Share Tech Mono', 'Cascadia Mono', 'Consolas'), ui_size=11, head_weight='bold', title_size=24, display_size=44, mono_size=10),
        fx=dict(glitch=True, ornament='stripes', tag='slant', button='chamfer', floor='grid', scanlines=True, upper=True,
                nav='{n:02d} {LABEL}', signal=('NO SIGNAL', '信号なし'), boot=('SYS.BOOT  //  起動シーケンス', 'SYSTEM READY  //  準備完了'))),
    'Eva Terminal': dict(
        blurb='Black and warning orange, tall condensed caps, Mincho kanji, terminal readouts.',
        colors=dict(background='#050404', surface='#0b0806', raised='#171009', border='#3d2a12', text='#ffe8c2',
                    muted='#b08d5c', accent='#ff6a00', accent2='#ffc23a', viewport='#040302'),
        fonts=_fontset(('Rajdhani Medium', 'Rajdhani', 'Bahnschrift', 'Segoe UI'), ('Bebas Neue',) + _COND,
                       ('VT323', 'Consolas'), ui_size=11, head_scale=1.3, title_size=32, display_size=64, mono_size=13, jp=_MINCHO, jp_size=9),
        fx=dict(glitch=False, ornament='stripes', tag='box', button='chamfer', floor='hex', scanlines=True, upper=True,
                nav='{n:02d}  {LABEL}', signal=('PATTERN: NONE', 'パターン不明'), boot=('MAGI-STYLE BOOT  //  起動', 'ALL SYSTEMS NOMINAL  //  正常'))),
    'Vaporwave': dict(
        blurb='Purple dusk, hot pink and aqua, retro-futurist type, sunset over the grid.',
        colors=dict(background='#140a24', surface='#1b0f31', raised='#2a1748', border='#432a6b', text='#fdeaff',
                    muted='#b89ad8', accent='#ff71ce', accent2='#01cdfe', viewport='#10061f'),
        fonts=_fontset(('Varela Round', 'Segoe UI'), ('Righteous', 'Segoe UI'), ('VT323', 'Consolas'),
                       ui_size=10, head_scale=1.0, title_size=22, display_size=40, mono_size=13),
        fx=dict(shadow=('accent', 2), glitch=False, ornament='sunbars', tag='pill', button='pill', floor='sun', scanlines=True, upper=False,
                nav='{label}', signal=('ＮＯ ＳＩＧＮＡＬ', 'ようこそ'), boot=('ＷＥＬＣＯＭＥ  //  ようこそ', 'ＲＥＡＤＹ  //  準備完了'))),
    'Kawaii Pastel': dict(
        blurb='Soft pink and mint on cream, bubbly rounded type, stars instead of stripes.',
        colors=dict(background='#fbeefa', surface='#fff8fd', raised='#ffe4f3', border='#f0c6e2', text='#4a2a52',
                    muted='#9a7aa5', accent='#ff5fa8', accent2='#3cc4ac', viewport='#fde6f5'),
        fonts=_fontset(('Varela Round', 'Segoe UI'), ('Sniglet ExtraBold', 'Sniglet'), ('Varela Round', 'Consolas'),
                       ui_size=10, head_weight='bold', head_scale=1.05, title_size=22, display_size=40, mono_size=9),
        fx=dict(shadow=('accent', 2), glitch=False, ornament='stars', tag='pill', button='pill', floor='dots', scanlines=False, upper=False,
                nav='{label}', signal=('nothing here yet!', 'まだ何もないよ ♡'), boot=('hello! ♡  //  こんにちは', 'all ready! ✦  //  じゅんび完了'))),
    'Pixel JRPG': dict(
        blurb='Classic RPG menu windows, gold cursor, pixel fonts with kana.',
        colors=dict(background='#060a24', surface='#0b1340', raised='#152060', border='#8f9cf0', text='#ffffff',
                    muted='#9fa9e8', accent='#ffd23f', accent2='#7df9ff', viewport='#050820'),
        fonts=_fontset(('DotGothic16', 'MS Gothic'), ('Press Start 2P', 'DotGothic16'), ('VT323', 'DotGothic16'),
                       ui_size=10, head_scale=.72, title_size=14, display_size=26, mono_size=14, jp=('DotGothic16',) + _JP, jp_size=9),
        fx=dict(leading=1.15, shadow=('background', 2), glitch=False, ornament='pixels', tag='window', button='pixel', floor='checker', scanlines=True, upper=True,
                nav='▶ {LABEL}', signal=('SELECT A SKIN', 'そうびを えらんでください'), boot=('NOW LOADING  //  ロード中', 'PRESS START  //  スタート'))),
    'Mecha HUD': dict(
        blurb='Gunmetal cockpit, caution yellow and HUD blue, wide technical type, chevrons.',
        colors=dict(background='#0b0e11', surface='#11161b', raised='#1a2128', border='#2b3640', text='#e9eef2',
                    muted='#8696a4', accent='#ffcc00', accent2='#3fa9ff', viewport='#080b0e'),
        fonts=_fontset(('Rajdhani Medium', 'Rajdhani', 'Bahnschrift', 'Segoe UI'), ('Michroma', 'Bahnschrift'),
                       ('Share Tech Mono', 'Consolas'), ui_size=11, head_scale=.8, title_size=16, display_size=30, mono_size=10),
        fx=dict(floor_color='accent2', glitch=False, ornament='chevrons', tag='slant', button='chamfer', floor='grid', scanlines=False, upper=True,
                nav='{LABEL}', signal=('NO TARGET', '目標なし'), boot=('COCKPIT INIT  //  起動', 'LAUNCH READY  //  発進準備完了'))),
}
DEFAULT_STYLE = 'Neon Cybercore'
PRESETS = {name: style['colors'] for name, style in STYLES.items()}
DEFAULT_PRESET = DEFAULT_STYLE
ACTIVE = {'style': DEFAULT_STYLE}


def style(name=None):
    return STYLES.get(name or ACTIVE['style'], STYLES[DEFAULT_STYLE])


def fx(): return style()['fx']


COLOR_LABELS = (
    ('background', 'Window chrome'), ('surface', 'Panels & tables'), ('raised', 'Buttons & inputs'),
    ('border', 'Grid lines'), ('text', 'Text'), ('muted', 'Secondary text'), ('accent', 'Main accent'),
    ('accent2', 'Secondary accent'), ('viewport', '3D preview background'),
)
LAYOUTS = ('Classic Columns', 'Preview Focus', 'Stacked Workspace')
RARITY = {'common': '#a9a3b8', 'rare': '#4cc9f0', 'epic': '#c77dff', 'legendary': '#ffc53d',
          'mythic': '#ff4d6d', 'heirloom': '#ff4d6d', 'iconic': '#ff4d6d'}
_HEX = re.compile(r'#[0-9a-fA-F]{6}')


def normalize(value):
    value = value if isinstance(value, dict) else {}
    current = value.get('version') == SETTINGS_VERSION
    preset = value.get('preset', DEFAULT_STYLE) if current else DEFAULT_STYLE
    if preset not in STYLES and preset != 'Custom': preset = DEFAULT_STYLE
    base = value.get('base', DEFAULT_STYLE) if preset == 'Custom' else preset
    if base not in STYLES: base = DEFAULT_STYLE
    colors = dict(STYLES[base]['colors'])
    supplied = value.get('colors', {})
    if preset == 'Custom' and isinstance(supplied, dict):
        for key in colors:
            color = supplied.get(key)
            if isinstance(color, str) and _HEX.fullmatch(color): colors[key] = color.lower()
    layout = value.get('layout', LAYOUTS[0])
    scan = value.get('scanlines')
    return dict(version=SETTINGS_VERSION, preset=preset, base=base, colors=colors,
                layout=layout if layout in LAYOUTS else LAYOUTS[0],
                mascot_path=value.get('mascot_path', '') if isinstance(value.get('mascot_path', ''), str) else '',
                show_mascot=value.get('show_mascot', True) is not False,
                scanlines=STYLES[base]['fx']['scanlines'] if scan is None else scan is not False)


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
    t = dict(STYLES[DEFAULT_STYLE]['colors']); t.update(colors)
    t['selection'] = t['accent']
    dark_text = t['background'] if luminance(t['background']) < .1 else t['text']
    t['selection_text'] = dark_text if luminance(t['accent']) > .18 else '#ffffff'
    t['accent_text'] = t['selection_text']
    t['accent2_text'] = dark_text if luminance(t['accent2']) > .18 else '#ffffff'
    t['light'] = luminance(t['surface']) > .5
    t['hover'] = mix(t['accent2'], t['raised'], .10)
    t['glow'] = mix(t['accent'], t['surface'], .22)
    t['dim2'] = mix(t['accent2'], t['surface'], .45)
    t['dim'] = mix(t['accent'], t['surface'], .45)
    t['faint'] = mix(t['muted'], t['surface'], .55)
    t['warn'] = '#ffc53d'
    t['good'] = t['accent2']
    t['viewport_top'] = mix('#ffffff', t['viewport'], .03)
    t['viewport_mid'] = mix('#ffffff', t['viewport'], .018)
    if t['light']:
        t['faint'] = mix(t['muted'], t['surface'], .7)
    return t


_FONT_CACHE = {}


def register_bundled_fonts():
    """Make the fonts shipped in resources/fonts usable by Tk for this process only (nothing is installed)."""
    import os
    folder = Path(__file__).resolve().parents[1] / 'resources' / 'fonts'
    if os.name != 'nt' or not folder.is_dir(): return
    try:
        import ctypes
        add = ctypes.windll.gdi32.AddFontResourceExW
        for path in folder.glob('*.ttf'): add(str(path), 0x10, 0)  # FR_PRIVATE
    except (OSError, AttributeError):
        pass


def fonts(app, name=None):
    """Font tuples for a style (the active one by default), resolved against installed families."""
    name = name if name in STYLES else ACTIVE['style']
    if name in _FONT_CACHE: return _FONT_CACHE[name]
    from tkinter import font
    if '_families' not in _FONT_CACHE: _FONT_CACHE['_families'] = set(font.families(app))
    families = _FONT_CACHE['_families']
    resolved = {}
    for key, (candidates, size, weight) in STYLES[name]['fonts'].items():
        family = next((c for c in candidates if c in families), 'TkDefaultFont')
        resolved[key] = (family, size, weight) if weight != 'normal' else (family, size)
    _FONT_CACHE[name] = resolved
    return resolved


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
    from tkinter import ttk, font
    import tkinter as tk
    ACTIVE['style'] = value.get('base') or DEFAULT_STYLE
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
        style.configure(name, background=bg, fieldbackground=bg, foreground=c['text'], rowheight=max(28, font.Font(font=f['body']).metrics('linespace') + 12),
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
            if getattr(widget, 'font_key', None): widget.configure(font=f[widget.font_key])
            widget.configure(background=c['surface'], foreground=c[getattr(widget, 'tone', 'text')],
                             insertbackground=c['accent2'], selectbackground=c['accent'], selectforeground=c['accent_text'],
                             borderwidth=0, highlightthickness=0, relief='flat', padx=0 if flush else 12, pady=0 if flush else 10)
        elif isinstance(widget, tk.Canvas) and not hasattr(widget, 'redraw'):
            widget.configure(background=c['background'], highlightthickness=0)
        elif isinstance(widget, tk.Toplevel):
            widget.configure(background=c['background'])
        for child in widget.winfo_children(): visit(child)
    visit(app)
    app.preview.set_palette(c['viewport'], c['text'], c['muted'], grid=c[fx().get('floor_color', 'accent')], hud=c['accent2'],
                            scanlines=value.get('scanlines', True), floor=fx()['floor'])
    return c
