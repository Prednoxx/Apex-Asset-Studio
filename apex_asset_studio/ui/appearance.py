"""Validated, atomically saved desktop appearance preferences and the ttk theme."""
import json
import re
from pathlib import Path

SETTINGS_VERSION = 2

# Each palette defines the full token set. Selection is derived from accent + surface so
# custom accents always get a matching highlight.
PRESETS = {
    'Graphite': dict(background='#101215', surface='#171a1e', raised='#1f2328', border='#2a2f36',
                     text='#e6e8eb', muted='#8a929d', accent='#e8503a', viewport='#0c0e10'),
    'Asuka Red': dict(background='#130f11', surface='#1b1518', raised='#251c20', border='#382a30',
                      text='#f3e9e6', muted='#a8948f', accent='#ef5b45', viewport='#0e0b0c'),
    'Midnight': dict(background='#0d1117', surface='#131a22', raised='#1a232e', border='#26323f',
                     text='#e3eaf2', muted='#8696a8', accent='#4fb4e6', viewport='#0a0e13'),
    'Light': dict(background='#eceef1', surface='#ffffff', raised='#f4f5f7', border='#d7dbe1',
                  text='#1c2128', muted='#5f6875', accent='#d2402a', viewport='#dfe3e8'),
}
DEFAULT_PRESET = 'Graphite'
COLOR_LABELS = (
    ('background', 'Window chrome'), ('surface', 'Panels & tables'), ('raised', 'Buttons & inputs'),
    ('border', 'Dividers'), ('text', 'Text'), ('muted', 'Secondary text'), ('accent', 'Accent'),
    ('viewport', '3D preview background'),
)
LAYOUTS = ('Classic Columns', 'Preview Focus', 'Stacked Workspace')
_HEX = re.compile(r'#[0-9a-fA-F]{6}')


def normalize(value):
    value = value if isinstance(value, dict) else {}
    upgraded = value.get('version') == SETTINGS_VERSION
    preset = value.get('preset', DEFAULT_PRESET) if upgraded else DEFAULT_PRESET
    if preset not in PRESETS and preset != 'Custom': preset = DEFAULT_PRESET
    colors = dict(PRESETS.get(preset, PRESETS[DEFAULT_PRESET]))
    supplied = value.get('colors', {})
    # Stored colors only matter for a custom palette; named presets always use their current values.
    if preset == 'Custom' and isinstance(supplied, dict):
        for key in colors:
            color = supplied.get(key)
            if isinstance(color, str) and _HEX.fullmatch(color): colors[key] = color.lower()
    layout = value.get('layout', LAYOUTS[0])
    return dict(version=SETTINGS_VERSION, preset=preset, colors=colors,
                layout=layout if layout in LAYOUTS else LAYOUTS[0],
                mascot_path=value.get('mascot_path', '') if isinstance(value.get('mascot_path', ''), str) else '',
                show_mascot=value.get('show_mascot', True) is not False)


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
    return sum(v/255*w for v, w in zip(_rgb(color), (.2126, .7152, .0722)))


def is_light(colors): return luminance(colors['surface']) > .5


def tokens(colors):
    """Full token set including derived values."""
    t = dict(colors)
    light = is_light(colors)
    t['selection'] = mix(colors['accent'], colors['surface'], .16 if light else .24)
    t['hover'] = mix(colors['text'], colors['raised'], .06 if light else .07)
    t['sidebar_selection'] = mix(colors['accent'], colors['background'], .16 if light else .22)
    t['accent_hover'] = mix('#ffffff', colors['accent'], .12)
    t['accent_text'] = '#16181b' if luminance(colors['accent']) > .55 else '#ffffff'
    t['faint'] = mix(colors['muted'], colors['surface'], .65)
    t['good'] = '#3f9b63' if light else '#5cc98a'
    t['warn'] = '#b7791f' if light else '#e0a84a'
    return t


def _png(image):
    import base64, io
    buffer = io.BytesIO(); image.save(buffer, 'PNG')
    return base64.b64encode(buffer.getvalue())


def _images(app, c):
    """Anti-aliased checkbox, radio and slider images, regenerated for each palette."""
    import tkinter as tk
    from PIL import Image, ImageDraw
    s = 4  # supersampling
    def canvas(w, h): return Image.new('RGBA', (w*s, h*s), (0, 0, 0, 0))
    def rgb(color, alpha=255): return (*_rgb(color), alpha)
    def done(image, w, h): return image.resize((w, h), Image.Resampling.LANCZOS)
    out = {}
    for key, fill, edge, mark in (('check_off', c['raised'], c['muted'], None), ('check_on', c['accent'], c['accent'], c['accent_text']),
                                  ('check_off_dis', c['background'], c['border'], None), ('check_on_dis', c['border'], c['border'], c['faint'])):
        im = canvas(24, 16); d = ImageDraw.Draw(im)
        d.rounded_rectangle((1*s, 1*s, 15*s-1, 15*s-1), radius=4*s, fill=rgb(fill), outline=rgb(edge), width=int(1.25*s))
        if mark: d.line([(4.4*s, 8.3*s), (6.9*s, 10.8*s), (11.8*s, 5.4*s)], fill=rgb(mark), width=int(1.9*s), joint='curve')
        out[key] = done(im, 24, 16)
    for key, fill, edge, dot in (('radio_off', c['raised'], c['muted'], None), ('radio_on', c['accent'], c['accent'], c['accent_text'])):
        im = canvas(24, 16); d = ImageDraw.Draw(im)
        d.ellipse((1*s, 1*s, 15*s-1, 15*s-1), fill=rgb(fill), outline=rgb(edge), width=int(1.25*s))
        if dot: d.ellipse((5.5*s, 5.5*s, 10.5*s, 10.5*s), fill=rgb(dot))
        out[key] = done(im, 24, 16)
    for key, color in (('thumb', c['text']), ('thumb_active', c['accent']), ('thumb_dis', c['faint'])):
        im = canvas(14, 14); d = ImageDraw.Draw(im)
        d.ellipse((1*s, 1*s, 13*s-1, 13*s-1), fill=rgb(color))
        out[key] = done(im, 14, 14)
    for key, bg in (('track', c['background']), ('track_panel', c['surface'])):
        im = Image.new('RGBA', (12*s, 14*s), rgb(bg)); d = ImageDraw.Draw(im)
        d.rounded_rectangle((0, 5.5*s, 12*s-1, 8.5*s), radius=1.5*s, fill=rgb(c['border']))
        out[key] = done(im, 12, 14)
    names = {}; objects = getattr(app, '_aas_image_objects', {})
    for key, image in out.items():
        name = f'aas_{key}'
        if key in objects: objects[key].configure(data=_png(image))  # update in place; ttk elements follow
        else: objects[key] = tk.PhotoImage(name=name, data=_png(image), master=app)
        names[key] = name
    app._aas_image_objects = objects  # Tk deletes images whose Python object is collected
    return names


_ELEMENTS = set()


def _elements(style, n):
    if 'check' not in _ELEMENTS:
        style.element_create('AAS.check', 'image', n['check_off'],
                             ('disabled', 'selected', n['check_on_dis']), ('disabled', n['check_off_dis']),
                             ('selected', n['check_on']), width=24, sticky='w')
        style.element_create('AAS.radio', 'image', n['radio_off'], ('selected', n['radio_on']), width=24, sticky='w')
        style.element_create('AAS.trough', 'image', n['track'], border=(5, 0, 5, 0), sticky='ew')
        style.element_create('AASPanel.trough', 'image', n['track_panel'], border=(5, 0, 5, 0), sticky='ew')
        style.element_create('AAS.slider', 'image', n['thumb'], ('disabled', n['thumb_dis']),
                             ('pressed', n['thumb_active']), ('active', n['thumb_active']))
        _ELEMENTS.add('check')


_FONT_CACHE = {}


def fonts(app):
    if _FONT_CACHE: return _FONT_CACHE
    from tkinter import font
    families = set(font.families(app))
    def pick(*names):
        return next((n for n in names if n in families), names[-1])
    ui = pick('Segoe UI Variable Text', 'Segoe UI', 'Inter', 'Noto Sans', 'DejaVu Sans', 'TkDefaultFont')
    strong = pick('Segoe UI Variable Display Semib', 'Segoe UI Semibold', ui)
    bold_weight = () if strong != ui else ('bold',)
    mono = pick('Cascadia Mono', 'Consolas', 'JetBrains Mono', 'DejaVu Sans Mono', 'TkFixedFont')
    _FONT_CACHE.update(
        body=(ui, 10), small=(ui, 9), strong=(strong, 10, *bold_weight),
        title=(strong, 15, *bold_weight), brand=(strong, 12, *bold_weight),
        section=(strong, 8, *bold_weight), mono=(mono, 9), display=(strong, 30, *bold_weight),
    )
    return _FONT_CACHE


def apply(app, value):
    from tkinter import ttk
    import tkinter as tk
    c = tokens(value['colors']); f = fonts(app)
    style = ttk.Style(app); style.theme_use('clam')
    app.configure(background=c['background'])
    _elements(style, _images(app, c))
    flat = dict(bordercolor=c['border'], lightcolor=c['raised'], darkcolor=c['raised'])

    style.configure('.', background=c['background'], foreground=c['text'], font=f['body'],
                    bordercolor=c['border'], lightcolor=c['background'], darkcolor=c['background'],
                    troughcolor=c['background'], focuscolor=c['accent'], selectbackground=c['selection'],
                    selectforeground=c['text'], insertcolor=c['text'], fieldbackground=c['raised'])
    style.map('.', foreground=[('disabled', c['faint'])])

    # Containers: chrome (window background), panel (surface) and 1px hairlines between panels.
    style.configure('TFrame', background=c['background'], borderwidth=0)
    style.configure('Panel.TFrame', background=c['surface'])
    style.configure('Hairline.TFrame', background=c['border'])
    style.configure('Card.TFrame', background=c['raised'])

    for prefix, bg in (('', c['background']), ('Panel.', c['surface']), ('Card.', c['raised'])):
        style.configure(f'{prefix}TLabel', background=bg, foreground=c['text'], font=f['body'])
        style.configure(f'Muted.{prefix}TLabel', foreground=c['muted'])
        style.configure(f'Small.{prefix}TLabel', foreground=c['muted'], font=f['small'])
        style.configure(f'Title.{prefix}TLabel', font=f['title'])
        style.configure(f'Strong.{prefix}TLabel', font=f['strong'])
        style.configure(f'Section.{prefix}TLabel', foreground=c['muted'], font=f['section'])
        style.configure(f'Warn.{prefix}TLabel', foreground=c['warn'], font=f['small'])
        style.configure(f'{prefix}TCheckbutton', background=bg, foreground=c['text'], font=f['body'],
                        indicatorbackground=c['raised'], indicatorforeground=c['accent_text'],
                        indicatormargin=(0, 0, 8, 0), padding=(0, 2), focusthickness=0)
        style.map(f'{prefix}TCheckbutton', background=[('active', bg)],
                  indicatorbackground=[('selected', c['accent']), ('active', c['hover'])],
                  foreground=[('disabled', c['faint'])])
        style.configure(f'{prefix}TRadiobutton', background=bg, foreground=c['text'], font=f['body'],
                        indicatorbackground=c['raised'], indicatorforeground=c['accent'], focusthickness=0)
        style.map(f'{prefix}TRadiobutton', background=[('active', bg)])
    for prefix in ('', 'Panel.', 'Card.'):
        style.layout(f'{prefix}TCheckbutton', [('Checkbutton.padding', {'sticky': 'nswe', 'children': [
            ('AAS.check', {'side': 'left', 'sticky': ''}), ('Checkbutton.label', {'side': 'left', 'sticky': 'nswe', 'expand': '1'})]})])
        style.configure(f'{prefix}TCheckbutton', padding=(0, 3))
        style.layout(f'{prefix}TRadiobutton', [('Radiobutton.padding', {'sticky': 'nswe', 'children': [
            ('AAS.radio', {'side': 'left', 'sticky': ''}), ('Radiobutton.label', {'side': 'left', 'sticky': 'nswe', 'expand': '1'})]})])
        style.configure(f'{prefix}TRadiobutton', padding=(0, 3))
    style.configure('Brand.TLabel', font=f['brand'])
    style.configure('Version.TLabel', foreground=c['muted'], font=f['small'])
    style.configure('Display.TLabel', font=f['display'])
    style.configure('Stat.Card.TLabel', font=(f['title'][0], 20, *f['title'][2:]))
    style.configure('Status.TLabel', foreground=c['muted'], font=f['small'])
    style.configure('Path.TLabel', foreground=c['muted'], font=f['small'])
    style.configure('Placeholder.TLabel', background=c['raised'], foreground=c['muted'], font=f['body'])
    style.configure('Dot.TLabel', foreground=c['good'], font=f['small'])
    style.configure('DotOff.TLabel', foreground=c['warn'], font=f['small'])

    # Buttons
    style.configure('TButton', background=c['raised'], foreground=c['text'], padding=(12, 5), relief='flat',
                    borderwidth=1, focusthickness=0, anchor='center', font=f['body'], **flat)
    style.map('TButton', background=[('disabled', c['raised']), ('pressed', c['border']), ('active', c['hover'])],
              foreground=[('disabled', c['faint'])], bordercolor=[('focus', c['muted'])],
              lightcolor=[('active', c['hover'])], darkcolor=[('active', c['hover'])])
    style.configure('Accent.TButton', background=c['accent'], foreground=c['accent_text'], font=f['strong'],
                    bordercolor=c['accent'], lightcolor=c['accent'], darkcolor=c['accent'], padding=(16, 7))
    style.map('Accent.TButton',
              background=[('disabled', c['raised']), ('pressed', c['accent']), ('active', c['accent_hover'])],
              foreground=[('disabled', c['faint'])],
              bordercolor=[('disabled', c['border']), ('active', c['accent_hover'])],
              lightcolor=[('disabled', c['raised']), ('active', c['accent_hover'])],
              darkcolor=[('disabled', c['raised']), ('active', c['accent_hover'])])
    for name, bg in (('Ghost.TButton', c['background']), ('Ghost.Panel.TButton', c['surface'])):
        style.configure(name, background=bg, bordercolor=bg, lightcolor=bg, darkcolor=bg, foreground=c['muted'], padding=(10, 5))
        style.map(name, background=[('active', c['hover'])], foreground=[('active', c['text']), ('disabled', c['faint'])],
                  bordercolor=[('active', c['hover'])], lightcolor=[('active', c['hover'])], darkcolor=[('active', c['hover'])])
    style.configure('Nav.TButton', background=c['background'], bordercolor=c['background'], lightcolor=c['background'],
                    darkcolor=c['background'], foreground=c['muted'], padding=(12, 6), font=f['strong'])
    style.map('Nav.TButton', background=[('active', c['hover'])], foreground=[('active', c['text'])],
              bordercolor=[('active', c['hover'])], lightcolor=[('active', c['hover'])], darkcolor=[('active', c['hover'])])
    style.configure('NavActive.TButton', background=c['raised'], bordercolor=c['border'], lightcolor=c['raised'],
                    darkcolor=c['raised'], foreground=c['text'], padding=(12, 6), font=f['strong'])
    style.map('NavActive.TButton', background=[('active', c['raised'])])

    # Inputs
    field = dict(fieldbackground=c['raised'], foreground=c['text'], insertcolor=c['text'], padding=(8, 5),
                 bordercolor=c['border'], lightcolor=c['raised'], darkcolor=c['raised'])
    style.configure('TEntry', **field)
    style.map('TEntry', bordercolor=[('focus', c['accent'])], lightcolor=[('focus', c['raised'])],
              fieldbackground=[('disabled', c['background'])], foreground=[('disabled', c['faint'])])
    style.configure('TSpinbox', arrowcolor=c['muted'], background=c['raised'], **field)
    style.configure('TCombobox', arrowcolor=c['muted'], background=c['raised'], arrowsize=13, **field)
    style.map('TCombobox', fieldbackground=[('readonly', c['raised']), ('disabled', c['background'])],
              background=[('active', c['hover']), ('readonly', c['raised'])],
              foreground=[('disabled', c['faint']), ('readonly', c['text'])],
              bordercolor=[('focus', c['accent'])], arrowcolor=[('disabled', c['faint'])],
              selectbackground=[('readonly', c['raised'])], selectforeground=[('readonly', c['text'])])
    app.option_add('*TCombobox*Listbox.background', c['raised'])
    app.option_add('*TCombobox*Listbox.foreground', c['text'])
    app.option_add('*TCombobox*Listbox.selectBackground', c['selection'])
    app.option_add('*TCombobox*Listbox.selectForeground', c['text'])
    app.option_add('*TCombobox*Listbox.font', f['body'])
    app.option_add('*TCombobox*Listbox.borderWidth', 0)
    app.option_add('*Menu.background', c['raised'])
    app.option_add('*Menu.foreground', c['text'])

    # Tables and trees
    for name, bg, sel in (('Treeview', c['surface'], c['selection']), ('Sidebar.Treeview', c['background'], c['sidebar_selection'])):
        style.configure(name, background=bg, fieldbackground=bg, foreground=c['text'], rowheight=30,
                        borderwidth=0, relief='flat', bordercolor=bg, lightcolor=bg, darkcolor=bg, font=f['body'], indent=14)
        style.map(name, background=[('selected', sel)], foreground=[('selected', c['text'])])
    style.layout('Treeview', [('Treeview.treearea', {'sticky': 'nswe'})])
    style.layout('Sidebar.Treeview', [('Treeview.treearea', {'sticky': 'nswe'})])
    style.configure('Treeview.Heading', background=c['surface'], foreground=c['muted'], relief='flat', padding=(10, 7),
                    font=f['section'], bordercolor=c['border'], lightcolor=c['surface'], darkcolor=c['surface'])
    style.map('Treeview.Heading', background=[('active', c['raised'])], foreground=[('active', c['text'])])
    style.configure('Treeview.Item', padding=(4, 0))

    # Hidden-tab notebook for top-level pages; segmented tabs for inner notebooks.
    style.configure('TNotebook', background=c['background'], borderwidth=0, tabmargins=(0, 0, 0, 0),
                    bordercolor=c['border'], lightcolor=c['background'], darkcolor=c['background'])
    style.configure('Pages.TNotebook', background=c['background'], borderwidth=0, padding=0,
                    bordercolor=c['background'], lightcolor=c['background'], darkcolor=c['background'])
    style.layout('Pages.TNotebook', [('Notebook.client', {'sticky': 'nswe'})])
    style.layout('Pages.TNotebook.Tab', [])
    style.configure('TNotebook.Tab', background=c['background'], foreground=c['muted'], padding=(14, 6),
                    borderwidth=0, font=f['strong'], bordercolor=c['background'], lightcolor=c['background'])
    style.map('TNotebook.Tab', background=[('selected', c['raised']), ('active', c['hover'])],
              foreground=[('selected', c['text']), ('active', c['text'])],
              bordercolor=[('selected', c['border'])], lightcolor=[('selected', c['raised'])],
              expand=[('selected', (0, 0, 0, 0))])

    # Slim scrollbars without arrow buttons
    for orient in ('Vertical', 'Horizontal'):
        style.layout(f'{orient}.TScrollbar', [(f'{orient}.Scrollbar.trough', {'sticky': 'nswe', 'children': [
            (f'{orient}.Scrollbar.thumb', {'expand': '1', 'sticky': 'nswe'})]})])
        style.configure(f'{orient}.TScrollbar', background=c['border'], troughcolor=c['surface'], borderwidth=0,
                        bordercolor=c['surface'], lightcolor=c['border'], darkcolor=c['border'], arrowsize=9, gripcount=0, relief='flat')
        style.map(f'{orient}.TScrollbar', background=[('active', c['muted'])], lightcolor=[('active', c['muted'])], darkcolor=[('active', c['muted'])])

    style.configure('Sidebar.Vertical.TScrollbar', troughcolor=c['background'], bordercolor=c['background'])
    style.configure('TSeparator', background=c['border'])
    style.configure('Horizontal.TProgressbar', background=c['accent'], troughcolor=c['raised'], bordercolor=c['raised'],
                    lightcolor=c['accent'], darkcolor=c['accent'], thickness=6)
    for prefix, bg in (('', c['background']), ('Panel.', c['surface'])):
        style.layout(f'{prefix}Horizontal.TScale', [('AASPanel.trough' if prefix else 'AAS.trough', {'sticky': 'ew', 'children': [
            ('AAS.slider', {'side': 'left', 'sticky': ''})]})])
        style.configure(f'{prefix}Horizontal.TScale', background=bg, sliderlength=14)
    style.configure('TPanedwindow', background=c['border'])
    style.configure('Sash', sashthickness=1, background=c['border'], gripcount=0)

    def visit(widget):
        if isinstance(widget, tk.Text):
            bg = c['background'] if getattr(widget, 'chrome', False) else c['surface']
            widget.configure(background=bg, foreground=c['text'], insertbackground=c['text'],
                             selectbackground=c['selection'], selectforeground=c['text'], borderwidth=0,
                             highlightthickness=0, relief='flat',
                             padx=0 if getattr(widget, 'flush', False) else 12, pady=0 if getattr(widget, 'flush', False) else 10)
        elif isinstance(widget, tk.Canvas):
            widget.configure(background=c['background'], highlightthickness=0)
        elif isinstance(widget, tk.Toplevel):
            widget.configure(background=c['background'])
        for child in widget.winfo_children(): visit(child)
    visit(app)
    app.preview.set_palette(c['viewport'], c['text'], c['muted'])
    return c
