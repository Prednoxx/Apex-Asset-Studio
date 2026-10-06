"""Validated, atomically saved appearance preferences and the glossy ttk theme.

Themes share one glossy glass look and differ in palette, type, button shape and background picture
(resources/backgrounds).
"""
import json
import re
from pathlib import Path

SETTINGS_VERSION = 6


def _F(candidates, size, weight='normal'):
    return (tuple(candidates), size, weight)


_UI = ('Segoe UI', 'Noto Sans', 'DejaVu Sans')
_SEMI = (('Segoe UI Semibold', 'normal'), ('Noto Sans', 'bold'), ('DejaVu Sans', 'bold'))
_LIGHT = ('Segoe UI Light', 'Segoe UI', 'Noto Sans Light', 'Noto Sans', 'DejaVu Sans')
_MONO = ('Cascadia Mono', 'Consolas', 'DejaVu Sans Mono')


def _fontset(head=_SEMI, title=_SEMI, display=_LIGHT, ui=_UI, ui_size=10, title_size=18):
    return dict(body=_F(ui, ui_size), small=_F(ui, ui_size - 1), strong=_F(head, ui_size), section=_F(head, ui_size),
                nav=_F(ui, ui_size + 1), title=_F(title, title_size), brand=_F(head, 13), stat=_F(display, 26),
                placeholder=_F(display, 22), display=_F(display, 34), data=_F(ui, ui_size), mono=_F(_MONO, 9),
                mono_small=_F(_MONO, 8))


# Trebuchet headings for Meadow; Segoe UI Light titles for Glass.
_ECO_HEAD = (('Trebuchet MS', 'bold'),) + _SEMI
_METRO_TITLE = ('Segoe UI Light',) + _LIGHT


def _theme(colors, backdrop, radius=6, shine=1.0, mascot_accent=False, fonts=None):
    """radius: corner radius of buttons and fields (None = capsule); shine: strength of the gloss highlight."""
    return dict(colors=colors, fonts=fonts or _fontset(),
                fx=dict(backdrop=backdrop, radius=radius, shine=shine, mascot_accent=mascot_accent))


STYLES = {
    'Aero Day': _theme(
        dict(background='#e7eef8', surface='#fbfcfe', raised='#eff4fa', border='#c9d6e6', text='#16202d',
             muted='#4d5a6c', accent='#d42e38', accent2='#d9681a', viewport='#e2eaf5'), 'aero_day.jpg', mascot_accent=True),
    'Aero Night': _theme(
        dict(background='#0e0b16', surface='#141020', raised='#1e1830', border='#302746', text='#efecf6',
             muted='#a9a1bd', accent='#e2373f', accent2='#ff8a3c', viewport='#0c0a13'), 'aero_night.jpg', mascot_accent=True),
    'Aqua': _theme(
        dict(background='#dcf0f6', surface='#f5fbfd', raised='#e4f3f8', border='#b2d8e4', text='#0a2430',
             muted='#3d6170', accent='#0a85b8', accent2='#1fb5c9', viewport='#d4ecf4'), 'aqua.jpg', radius=None),
    'Meadow': _theme(
        dict(background='#ecf4e4', surface='#fbfdf8', raised='#eef5e6', border='#c6dcb2', text='#1a2a12',
             muted='#4b6140', accent='#3f9b22', accent2='#2a8fc9', viewport='#e7f1dd'), 'eco.jpg', radius=8,
        fonts=_fontset(head=_ECO_HEAD, title=_ECO_HEAD)),
    'Glass': _theme(
        dict(background='#e4f1f6', surface='#f7fbfd', raised='#eaf4f8', border='#bfd8e3', text='#0e2430',
             muted='#43616f', accent='#1a7fa8', accent2='#2f6fd6', viewport='#dfeef4'), 'metro.jpg', radius=2, shine=.55,
        fonts=_fontset(title=_METRO_TITLE, title_size=20)),
    'Aurora': _theme(
        dict(background='#06120d', surface='#0b1a13', raised='#12261c', border='#1f3a2c', text='#e6f5ee',
             muted='#8fb3a2', accent='#1fb36a', accent2='#4fd1c5', viewport='#05100b'), 'aurora.jpg'),
    'Sunburst': _theme(
        dict(background='#14110a', surface='#1b170d', raised='#262012', border='#3a321c', text='#f7f1df',
             muted='#b8ad8c', accent='#e2b100', accent2='#ffd54a', viewport='#110e08'), 'sunburst.jpg'),
    'Sweetheart': _theme(
        dict(background='#170c1c', surface='#1f1026', raised='#2b1735', border='#43264f', text='#fbeefc',
             muted='#c4a5c9', accent='#e8304a', accent2='#d660e0', viewport='#140a18'), 'sweetheart.jpg', radius=None),
}
DEFAULT_STYLE = 'Aero Day'
RENAMED = {'Frutiger Aqua': 'Aqua', 'Frutiger Eco': 'Meadow', 'Frutiger Metro': 'Glass'}  # names used before 0.4
STYLE_ORDER = list(STYLES)
TEXT_SCALES = (('Small', .9), ('Normal', 1.0), ('Large', 1.15), ('Larger', 1.3), ('Largest', 1.5))


def rarity(t):
    """Rarity text colors, deepened on light palettes and nudged toward the text color until they meet WCAG AA
    (AAA with high contrast) on the list background."""
    colors = dict(RARITY) if not t.get('light') else {
        'common': '#7d7a86', 'rare': '#1d87cf', 'epic': '#9147cf', 'legendary': '#c98a00',
        'mythic': '#e0335a', 'heirloom': '#e0335a', 'iconic': '#e0335a'}
    need = 7 if ACTIVE.get('contrast') else 4.5
    return {key: readable(color, t['surface'], need, t['text']) for key, color in colors.items()}
DEFAULT_PRESET = DEFAULT_STYLE
# The mascot, Ruka-tan: full artwork (startup screen, Settings, accent color) and her round avatar (header, icons).
_RESOURCES = __import__('pathlib').Path(__file__).resolve().parents[1] / 'resources'
MASCOT_NAME = 'Ruka-tan'
MASCOT_ART = _RESOURCES / 'ruka.webp'
MASCOT_AVATAR = _RESOURCES / 'ruka_avatar.png'
MASCOT_ACCENT = '#4b80c6'  # her ribbon blue (the Aero themes' accent when 'match accent' is on)
ACTIVE = {'style': DEFAULT_STYLE, 'scale': 1.0, 'contrast': False, 'reduce': False, 'mascot_accent': None}


def style(name=None):
    return STYLES.get(name or ACTIVE['style'], STYLES[DEFAULT_STYLE])


def fx():
    """The active theme's material: backdrop art, corner radius, gloss strength. Reduce effects keeps the shapes
    but swaps the backdrop art for a plain gradient and tones the gloss down."""
    base = style()['fx']
    if not ACTIVE.get('reduce'): return base
    return dict(base, backdrop='plain', shine=min(base['shine'], .4))


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
    preset = RENAMED.get(value.get('preset', DEFAULT_STYLE), value.get('preset', DEFAULT_STYLE))
    if preset not in STYLES and preset != 'Custom': preset = DEFAULT_STYLE
    base = RENAMED.get(value.get('base', DEFAULT_STYLE), value.get('base', DEFAULT_STYLE)) if preset == 'Custom' else preset
    if base not in STYLES: preset = base = DEFAULT_STYLE  # themes from older versions fall back to the default
    colors = dict(STYLES[base]['colors'])
    supplied = value.get('colors', {})
    if preset == 'Custom' and isinstance(supplied, dict):
        for key in colors:
            color = supplied.get(key)
            if isinstance(color, str) and _HEX.fullmatch(color): colors[key] = color.lower()
    layout = value.get('layout', LAYOUTS[0])
    return dict(version=SETTINGS_VERSION, preset=preset, base=base, colors=colors,
                layout=layout if layout in LAYOUTS else LAYOUTS[0],
                text_scale=value.get('text_scale') if value.get('text_scale') in dict(TEXT_SCALES).values() else 1.0,
                high_contrast=value.get('high_contrast') is True, reduce_effects=value.get('reduce_effects') is True,
                mascot_accent=value.get('mascot_accent', True) is not False)


def effective_colors(value):
    """Palette after the 'match accent to mascot' option (named styles that allow it only)."""
    colors = dict(value['colors'])
    accent = ACTIVE.get('mascot_accent')
    if accent and value.get('mascot_accent', True) and value.get('preset') != 'Custom' and STYLES[value['base']]['fx'].get('mascot_accent'):
        from .gloss import companion
        colors['accent'] = accent; colors['accent2'] = companion(accent)
    return colors


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


def contrast(a, b):
    la, lb = luminance(a), luminance(b)
    return (max(la, lb) + .05) / (min(la, lb) + .05)


def readable(color, against, minimum, toward):
    """Move color toward `toward` until it reaches the contrast minimum against `against`."""
    if contrast(color, against) >= minimum: return color
    for step in range(1, 21):
        candidate = mix(toward, color, step / 20)
        if contrast(candidate, against) >= minimum: return candidate
    return toward


def tokens(colors):
    """Full token set including derived values, with text contrast enforced (WCAG AA, or AAA in high contrast)."""
    t = dict(STYLES[DEFAULT_STYLE]['colors']); t.update(colors)
    hc = ACTIVE.get('contrast')
    for surface in ('surface', 'background'):
        t['muted'] = readable(t['muted'], t[surface], 7 if hc else 4.6, t['text'])
    if hc:
        t['border'] = mix(t['text'], t['surface'], .45)
        t['text'] = readable(t['text'], t['surface'], 12, '#ffffff' if luminance(t['surface']) < .5 else '#000000')
    t['selection'] = t['accent']
    dark_text = t['background'] if luminance(t['background']) < .1 else t['text']
    t['selection_text'] = dark_text if luminance(t['accent']) > .18 else '#ffffff'
    t['accent_text'] = t['selection_text']
    t['accent2_text'] = dark_text if luminance(t['accent2']) > .18 else '#ffffff'
    t['light'] = luminance(t['surface']) > .5
    t['hover'] = mix(t['accent2'], t['raised'], .10)
    t['faint'] = mix(t['muted'], t['surface'], .55)
    need = 7 if hc else 4.5
    t['warn'] = '#ffc53d' if luminance(t['surface']) < .5 else '#9a6400'  # amber; darker on light themes
    for surface in ('surface', 'background'): t['warn'] = readable(t['warn'], t[surface], need, t['text'])
    if t['light']:
        t['faint'] = mix(t['muted'], t['surface'], .7)
    t['faint'] = readable(t['faint'], t['surface'], 4.5 if hc else 3.0, t['text'])
    t['selection'] = mix(t['accent'], t['surface'], .62 if not t['light'] else .22)
    t['selection_text'] = '#ffffff' if contrast('#ffffff', t['selection']) >= contrast(t['text'], t['selection']) else t['text']
    t['selection'] = readable(t['selection'], t['selection_text'], 4.5, t['surface'])  # bright accents: deepen the bar
    t['accent_text'] = '#ffffff' if contrast('#ffffff', t['accent']) >= 3.6 else '#141414'  # white unless the accent is very light
    # Filled accent buttons/pills use accent_fill: the accent, deepened (or lightened) just enough that their label
    # meets the contrast minimum, with a little margin for the gloss highlight.
    t['accent_fill'] = readable(t['accent'], t['accent_text'], need + .4, '#000000' if t['accent_text'] == '#ffffff' else '#ffffff')
    t['hover'] = mix(t['accent'], t['raised'], .14)
    return t


_FONT_CACHE = {}


def fonts(app, name=None):
    """Font tuples for a style (the active one by default), resolved against installed families."""
    name = name if name in STYLES else ACTIVE['style']
    scale = ACTIVE.get('scale', 1.0); key_ = (name, scale)
    if key_ in _FONT_CACHE: return _FONT_CACHE[key_]
    from tkinter import font
    if '_families' not in _FONT_CACHE: _FONT_CACHE['_families'] = set(font.families(app))
    families = _FONT_CACHE['_families']
    resolved = {}
    for key, (candidates, size, weight) in STYLES[name]['fonts'].items():
        options = [c if isinstance(c, tuple) else (c, weight) for c in candidates]
        family, chosen = next(((fam, wt) for fam, wt in options if fam in families), ('TkDefaultFont', weight))
        size = max(6, round(size * scale))
        resolved[key] = (family, size, chosen) if chosen != 'normal' else (family, size)
    _FONT_CACHE[key_] = resolved
    return resolved


def _png(image):
    import base64, io
    buffer = io.BytesIO(); image.save(buffer, 'PNG')
    return base64.b64encode(buffer.getvalue())


def _photo(app, store, prefix, images):
    """Create or update named Tk images (kept referenced: Tk deletes images whose Python object is collected)."""
    import tkinter as tk
    objects = getattr(app, store, {}); names = {}
    for key, image in images.items():
        if key in objects: objects[key].configure(data=_png(image))
        else: objects[key] = tk.PhotoImage(name=f'{prefix}_{key}', data=_png(image), master=app)
        names[key] = f'{prefix}_{key}'
    setattr(app, store, objects)
    return names


def _control_images(app, c, f, m):
    """Glossy buttons, fields, checkboxes, radios and slider parts for the active palette and theme material."""
    from tkinter import font as tkfont
    from . import gloss
    dark = not c['light']; shine = m['shine']; radius = m['radius']
    # Images are exactly the widgets' natural height: ttk tiles (not stretches) an image element's middle,
    # so a taller widget would repeat the gradient as stripes.
    bh = tkfont.Font(font=f['strong']).metrics('linespace') + 14
    fh = tkfont.Font(font=f['body']).metrics('linespace') + 14
    corner = 6 if radius is None else radius
    button_radius = None if radius is None else radius
    neutral = gloss.shade(c['raised'], .10 if dark else -.02)
    out = {}
    for state in ('normal', 'hover', 'pressed', 'disabled'):
        out[f'button_{state}'] = gloss.pill(max(40, bh * 2), bh, neutral, state, radius=button_radius, dark=dark, shine=shine)
        out[f'accent_{state}'] = gloss.pill(max(40, bh * 2), bh, c['accent_fill'], state, radius=button_radius, dark=dark, shine=shine)
    field_radius = min(corner, fh // 2) if radius is not None else fh // 2
    out['field'] = gloss.field(max(40, fh * 2), fh, c['raised'], c['border'], radius=field_radius)
    out['field_focus'] = gloss.field(max(40, fh * 2), fh, c['raised'], c['border'], focus=c['accent'], radius=field_radius)
    out['field_disabled'] = gloss.field(max(40, fh * 2), fh, c['surface'], c['border'], radius=field_radius)
    scale = ACTIVE.get('scale', 1.0)  # checkboxes, radios and slider knobs grow with the text size
    box = round(16 * scale); check_radius = round((5 if radius is None else min(4, max(1, radius))) * scale)
    for key, fill, edge, mark in (('check_off', c['raised'], c['muted'], None), ('check_on', c['accent'], c['accent'], c['accent_text']),
                                  ('check_off_dis', c['surface'], c['border'], None), ('check_on_dis', c['border'], c['border'], c['faint'])):
        out[key] = _pad(gloss.check_mark(box, fill, edge, mark, radius=check_radius, shine=shine), box + 8, box)
    for key, edge, dot in (('radio_off', c['muted'], None), ('radio_on', c['accent'], c['accent'])):
        out[key] = _pad(gloss.radio_mark(box, c['raised'], edge, dot, shine=shine), box + 8, box)
    knob = round(16 * scale)
    for key, color in (('thumb', c['accent']), ('thumb_active', gloss.shade(c['accent'], .15)), ('thumb_dis', c['faint'])):
        out[key] = gloss.pill(knob, knob, color, 'normal', radius=knob // 2, dark=dark, shine=shine)
    for key, bg in (('track', c['background']), ('track_panel', c['surface'])):
        from PIL import Image, ImageDraw
        im = Image.new('RGBA', (24, 16), (*_rgb(bg), 255))
        ImageDraw.Draw(im).rounded_rectangle((0, 6, 23, 9), radius=2, fill=(*_rgb(c['border']), 255))
        out[key] = im
    edge = max(10, (bh // 2 + 2) if radius is None else corner + 4, field_radius + 4)
    return _photo(app, '_aas_control_objects', 'aasc', out), edge


def _pad(image, width, height):
    from PIL import Image
    canvas = Image.new('RGBA', (width, height), (0, 0, 0, 0)); canvas.alpha_composite(image, (0, (height - image.height) // 2))
    return canvas


_ELEMENTS = set()


def _elements(style, n, edge):
    """Image elements. Named images are updated in place for each palette; the stretch border depends on the corner
    radius, so button/field elements exist once per border width (ttk cannot change an element after creation)."""
    if 'base' not in _ELEMENTS:
        style.element_create('AAS.check', 'image', n['check_off'],
                             ('disabled', 'selected', n['check_on_dis']), ('disabled', n['check_off_dis']),
                             ('selected', n['check_on']), sticky='w')
        style.element_create('AAS.radio', 'image', n['radio_off'], ('selected', n['radio_on']), sticky='w')
        style.element_create('AAS.trough', 'image', n['track'], border=(5, 0, 5, 0), sticky='ew')
        style.element_create('AASPanel.trough', 'image', n['track_panel'], border=(5, 0, 5, 0), sticky='ew')
        style.element_create('AAS.slider', 'image', n['thumb'], ('disabled', n['thumb_dis']),
                             ('pressed', n['thumb_active']), ('active', n['thumb_active']))
        _ELEMENTS.add('base')
    if edge not in _ELEMENTS:
        for kind in ('button', 'accent'):
            style.element_create(f'AASG{edge}.{kind}', 'image', n[f'{kind}_normal'], ('disabled', n[f'{kind}_disabled']),
                                 ('pressed', n[f'{kind}_pressed']), ('active', n[f'{kind}_hover']), ('focus', n[f'{kind}_hover']),
                                 border=(edge, 4, edge, 4), sticky='nsew')
        style.element_create(f'AASG{edge}.field', 'image', n['field'], ('disabled', n['field_disabled']), ('focus', n['field_focus']),
                             border=(edge, 4, edge, 4), sticky='nsew')
        _ELEMENTS.add(edge)
    return f'AASG{edge}'


def apply(app, value):
    """Apply the saved appearance to every widget. Returns the color tokens."""
    from tkinter import ttk, font
    import tkinter as tk
    ACTIVE['style'] = value.get('base') or DEFAULT_STYLE
    ACTIVE['scale'] = value.get('text_scale', 1.0); ACTIVE['contrast'] = value.get('high_contrast', False)
    ACTIVE['reduce'] = value.get('reduce_effects', False)
    c = tokens(effective_colors(value)); f = fonts(app); m = fx()
    style = ttk.Style(app); style.theme_use('clam')
    names, edge = _control_images(app, c, f, m)
    element = _elements(style, names, edge)
    app.configure(background=c['background'])

    style.configure('.', background=c['background'], foreground=c['text'], font=f['body'],
                    bordercolor=c['border'], lightcolor=c['background'], darkcolor=c['background'],
                    troughcolor=c['background'], focuscolor=c['accent2'], selectbackground=c['accent'],
                    selectforeground=c['accent_text'], insertcolor=c['text'], fieldbackground=c['raised'])
    style.map('.', foreground=[('disabled', c['faint'])])

    style.configure('TFrame', background=c['background'], borderwidth=0)
    style.configure('Panel.TFrame', background=c['surface'])
    style.configure('Hairline.TFrame', background=c['border'])
    style.configure('Focus.TFrame', background=c['accent'])  # keyboard focus ring around the 3D view
    style.configure('Card.TFrame', background=c['raised'])

    for prefix, bg in (('', c['background']), ('Panel.', c['surface']), ('Card.', c['raised'])):
        style.configure(f'{prefix}TLabel', background=bg, foreground=c['text'], font=f['body'])
        style.configure(f'Muted.{prefix}TLabel', foreground=c['muted'])
        style.configure(f'Small.{prefix}TLabel', foreground=c['muted'], font=f['small'])
        style.configure(f'Title.{prefix}TLabel', font=f['title'])
        style.configure(f'Strong.{prefix}TLabel', font=f['strong'])
        style.configure(f'Section.{prefix}TLabel', foreground=c['muted'], font=f['small'])
        style.configure(f'Data.{prefix}TLabel', foreground=c['muted'], font=f['data'])
        # The label sits inside a focus element so keyboard focus shows as a ring around it.
        focus_ring = dict(focusthickness=1, focuscolor=c['accent'])
        style.configure(f'{prefix}TCheckbutton', background=bg, foreground=c['text'], font=f['body'], padding=(0, 3), **focus_ring)
        style.map(f'{prefix}TCheckbutton', background=[('active', bg)], foreground=[('disabled', c['faint']), ('active', c['accent'])])
        style.layout(f'{prefix}TCheckbutton', [('Checkbutton.padding', {'sticky': 'nswe', 'children': [
            ('AAS.check', {'side': 'left', 'sticky': ''}), ('Checkbutton.focus', {'side': 'left', 'sticky': 'w', 'children': [
                ('Checkbutton.label', {'sticky': 'nswe'})]})]})])
        style.configure(f'{prefix}TRadiobutton', background=bg, foreground=c['text'], font=f['body'], padding=(0, 3), **focus_ring)
        style.map(f'{prefix}TRadiobutton', background=[('active', bg)], foreground=[('active', c['accent'])])
        style.layout(f'{prefix}TRadiobutton', [('Radiobutton.padding', {'sticky': 'nswe', 'children': [
            ('AAS.radio', {'side': 'left', 'sticky': ''}), ('Radiobutton.focus', {'side': 'left', 'sticky': 'w', 'children': [
                ('Radiobutton.label', {'sticky': 'nswe'})]})]})])
    style.configure('Stat.Card.TLabel', font=f['stat'], foreground=c['text'])
    style.configure('Placeholder.TLabel', background=c['raised'], foreground=c['faint'], font=f['body'])
    style.configure('Status.TLabel', foreground=c['muted'], font=f['small'])

    # Buttons: glossy plates (image elements); ghost buttons are text-only links
    focused = [('Button.focus', {'sticky': 'nswe', 'children': [('Button.padding', {'sticky': 'nswe', 'children': [
        ('Button.label', {'sticky': 'nswe'})]})]})]
    def button(element):
        return [(element, {'sticky': 'nswe', 'children': focused})]
    style.layout('TButton', button(f'{element}.button')); style.layout('Accent.TButton', button(f'{element}.accent'))
    style.configure('TButton', padding=(12, 2), foreground=c['text'], background=c['background'], anchor='center',
                    font=f['strong'], focusthickness=1, focuscolor=c['muted'], relief='flat', borderwidth=0)
    style.map('TButton', foreground=[('disabled', c['faint'])], background=[])
    style.configure('Accent.TButton', padding=(16, 2), foreground=c['accent_text'], focuscolor=c['accent_text'])
    style.map('Accent.TButton', foreground=[('disabled', c['faint'])], background=[])
    for name, bg in (('Ghost.TButton', c['background']), ('Ghost.Panel.TButton', c['surface'])):
        style.layout(name, focused)
        style.configure(name, background=bg, foreground=c['muted'], padding=(8, 3), font=f['small'], focuscolor=c['accent'])
        style.map(name, background=[('active', bg)], foreground=[('disabled', c['faint']), ('active', c['text'])])

    # Inputs: glossy fields
    style.layout('TEntry', [(f'{element}.field', {'sticky': 'nswe', 'children': [('Entry.padding', {'sticky': 'nswe', 'children': [
        ('Entry.textarea', {'sticky': 'nswe'})]})]})])
    style.layout('TCombobox', [(f'{element}.field', {'sticky': 'nswe', 'children': [
        ('Combobox.downarrow', {'side': 'right', 'sticky': 'ns'}),
        ('Combobox.padding', {'expand': '1', 'sticky': 'nswe', 'children': [('Combobox.textarea', {'sticky': 'nswe'})]})]})])
    field = dict(fieldbackground=c['raised'], foreground=c['text'], insertcolor=c['text'], padding=(6, 3), font=f['body'])
    style.configure('TEntry', **field)
    style.map('TEntry', foreground=[('disabled', c['faint'])])
    style.configure('TSpinbox', arrowcolor=c['muted'], background=c['raised'], bordercolor=c['border'],
                    lightcolor=c['raised'], darkcolor=c['raised'], **field)
    style.configure('TCombobox', arrowcolor=c['muted'], background=c['raised'], arrowsize=12, **field)
    style.map('TCombobox', fieldbackground=[('readonly', c['raised']), ('disabled', c['surface'])],
              background=[('active', c['raised']), ('readonly', c['raised'])],
              foreground=[('disabled', c['faint']), ('readonly', c['text'])], arrowcolor=[('disabled', c['faint'])],
              selectbackground=[('readonly', c['raised'])], selectforeground=[('readonly', c['text'])])
    app.option_add('*TCombobox*Listbox.background', c['raised'])
    app.option_add('*TCombobox*Listbox.foreground', c['text'])
    app.option_add('*TCombobox*Listbox.selectBackground', c['selection'])
    app.option_add('*TCombobox*Listbox.selectForeground', c['selection_text'])
    app.option_add('*TCombobox*Listbox.font', f['body'])
    app.option_add('*TCombobox*Listbox.borderWidth', 0)

    # Tables and trees
    for name, bg in (('Treeview', c['surface']), ('Sidebar.Treeview', c['background'])):
        style.configure(name, background=bg, fieldbackground=bg, foreground=c['text'], rowheight=max(28, font.Font(font=f['body']).metrics('linespace') + 12),
                        borderwidth=0, relief='flat', bordercolor=bg, lightcolor=bg, darkcolor=bg, font=f['body'], indent=14)
        style.map(name, background=[('selected', c['selection'])], foreground=[('selected', c['selection_text'])])
        style.layout(name, [('Treeview.treearea', {'sticky': 'nswe'})])
    style.configure('Treeview.Heading', background=c['surface'], foreground=c['muted'], relief='flat', padding=(10, 7),
                    font=f['strong'], bordercolor=c['border'], lightcolor=c['surface'], darkcolor=c['surface'])
    style.map('Treeview.Heading', background=[('active', c['raised'])], foreground=[('active', c['text'])])

    # Notebooks: the main pages have no tabs (the header switches them); inner notebooks get pill tabs
    style.configure('TNotebook', background=c['background'], borderwidth=0, tabmargins=(0, 0, 0, 8),
                    bordercolor=c['background'], lightcolor=c['background'], darkcolor=c['background'])
    style.configure('Pages.TNotebook', padding=0)
    style.layout('Pages.TNotebook', [('Notebook.client', {'sticky': 'nswe'})])
    style.layout('Pages.TNotebook.Tab', [])
    style.configure('TNotebook.Tab', background=c['background'], foreground=c['muted'], padding=(14, 6),
                    borderwidth=0, font=f['nav'], bordercolor=c['background'], lightcolor=c['background'], darkcolor=c['background'])
    style.map('TNotebook.Tab', background=[('selected', c['selection']), ('active', c['raised'])],
              foreground=[('selected', c['selection_text']), ('active', c['text'])],
              bordercolor=[('selected', c['selection'])], lightcolor=[('selected', c['selection'])],
              expand=[('selected', (0, 0, 0, 0))])

    for orient in ('Vertical', 'Horizontal'):
        style.layout(f'{orient}.TScrollbar', [(f'{orient}.Scrollbar.trough', {'sticky': 'nswe', 'children': [
            (f'{orient}.Scrollbar.thumb', {'expand': '1', 'sticky': 'nswe'})]})])
        style.configure(f'{orient}.TScrollbar', background=c['border'], troughcolor=c['surface'], borderwidth=0,
                        bordercolor=c['surface'], lightcolor=c['border'], darkcolor=c['border'], arrowsize=7, gripcount=0, relief='flat')
        style.map(f'{orient}.TScrollbar', background=[('active', c['muted'])], lightcolor=[('active', c['muted'])], darkcolor=[('active', c['muted'])])
    style.configure('Sidebar.Vertical.TScrollbar', troughcolor=c['background'], bordercolor=c['background'])
    style.configure('TSeparator', background=c['border'])
    style.configure('Horizontal.TProgressbar', background=c['accent'], troughcolor=c['raised'], bordercolor=c['raised'],
                    lightcolor=c['accent'], darkcolor=c['accent'], thickness=6)
    for prefix, bg in (('', c['background']), ('Panel.', c['surface'])):
        style.layout(f'{prefix}Horizontal.TScale', [('AASPanel.trough' if prefix else 'AAS.trough', {'sticky': 'ew', 'children': [
            ('AAS.slider', {'side': 'left', 'sticky': ''})]})])
        style.configure(f'{prefix}Horizontal.TScale', background=bg, sliderlength=16)
    style.configure('TPanedwindow', background=c['border'])
    style.configure('Sash', sashthickness=1, background=c['border'], gripcount=0)

    def visit(widget):
        if isinstance(widget, tk.Text):
            flush = getattr(widget, 'flush', False)
            if getattr(widget, 'font_key', None): widget.configure(font=f[widget.font_key])
            widget.configure(background=c['surface'], foreground=c[getattr(widget, 'tone', 'text')],
                             insertbackground=c['text'], selectbackground=c['selection'], selectforeground=c['selection_text'],
                             borderwidth=0, highlightthickness=0, relief='flat', padx=0 if flush else 12, pady=0 if flush else 10)
        elif isinstance(widget, tk.Canvas) and not hasattr(widget, 'redraw'):
            widget.configure(background=c['background'], highlightthickness=0)
        elif isinstance(widget, tk.Toplevel):
            widget.configure(background=c['background'])
        elif isinstance(widget, (ttk.Entry, ttk.Combobox, ttk.Spinbox)):
            widget.configure(font=f['body'])
        for child in widget.winfo_children(): visit(child)
    visit(app)
    return c
