"""Validated, atomically saved desktop appearance preferences."""
import json
import re
from pathlib import Path

PRESETS = {
    'Studio Dark': dict(background='#202329', surface='#2c3038', text='#edf0f5', muted='#b1b8c4', accent='#e87045', selection='#703b2b', viewport='#16191d'),
    'Asuka Red': dict(background='#221c20', surface='#34272e', text='#fff1ec', muted='#d0b7b1', accent='#ef6549', selection='#803d34', viewport='#181316'),
    'Ocean': dict(background='#18232d', surface='#243746', text='#eaf5ff', muted='#a9c4d6', accent='#64c8ec', selection='#275674', viewport='#101a23'),
    'Light': dict(background='#eceef2', surface='#ffffff', text='#202631', muted='#525c6b', accent='#9f341d', selection='#d8e7fa', viewport='#dde2ea'),
}
LAYOUTS = ('Classic Columns', 'Preview Focus', 'Stacked Workspace')


def normalize(value):
    value = value if isinstance(value, dict) else {}
    preset = value.get('preset', 'Asuka Red')
    if preset not in PRESETS and preset != 'Custom': preset = 'Asuka Red'
    colors = dict(PRESETS.get(preset, PRESETS['Asuka Red']))
    supplied = value.get('colors', {})
    if isinstance(supplied, dict):
        for key in colors:
            color = supplied.get(key)
            if isinstance(color, str) and re.fullmatch(r'#[0-9a-fA-F]{6}', color): colors[key] = color.lower()
    layout = value.get('layout', LAYOUTS[0])
    return dict(preset=preset, colors=colors, layout=layout if layout in LAYOUTS else LAYOUTS[0],
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


def apply(app, value):
    from tkinter import ttk
    import tkinter as tk
    colors = value['colors']; style = ttk.Style(app); style.theme_use('clam')
    app.configure(background=colors['background'])
    style.configure('.', background=colors['background'], foreground=colors['text'], font=('Segoe UI', 10),
                    bordercolor=colors['surface'], lightcolor=colors['surface'], darkcolor=colors['surface'])
    style.configure('TFrame', borderwidth=0)
    style.configure('Title.TLabel', font=('Segoe UI Semibold', 12))
    style.configure('TEntry', fieldbackground=colors['surface'], foreground=colors['text'], insertcolor=colors['text'])
    style.configure('TCombobox', fieldbackground=colors['surface'], foreground=colors['text'], arrowcolor=colors['text'])
    style.map('TCombobox', fieldbackground=[('readonly', colors['surface'])], foreground=[('readonly', colors['text']), ('disabled', colors['muted'])])
    style.configure('TButton', background=colors['surface'], foreground=colors['text'], padding=(10, 5), relief='flat', borderwidth=0)
    style.map('TButton', background=[('active', colors['selection'])], foreground=[('disabled', colors['muted'])])
    style.configure('TCheckbutton', background=colors['background'], foreground=colors['text'])
    style.map('TCheckbutton', background=[('active', colors['background'])], foreground=[('disabled', colors['muted'])])
    style.configure('Treeview', background=colors['surface'], fieldbackground=colors['surface'], foreground=colors['text'], rowheight=27, borderwidth=0, relief='flat')
    style.map('Treeview', background=[('selected', colors['selection'])], foreground=[('selected', colors['text'])])
    style.configure('Treeview.Heading', background=colors['background'], foreground=colors['muted'], relief='flat', padding=(6, 6))
    style.map('Treeview.Heading', background=[('active', colors['selection'])])
    style.configure('TNotebook', borderwidth=0, tabmargins=(0, 0, 0, 0))
    style.configure('TNotebook.Tab', background=colors['surface'], foreground=colors['muted'], padding=(14, 7), borderwidth=0)
    style.map('TNotebook.Tab', background=[('selected', colors['selection'])], foreground=[('selected', colors['text'])])
    style.configure('Muted.TLabel', foreground=colors['muted'])
    style.configure('Status.TLabel', foreground=colors['muted'])
    style.configure('Accent.TLabel', foreground=colors['accent'], font=('Segoe UI Semibold', 17))
    rgb = [int(colors['accent'][i:i+2], 16)/255 for i in (1,3,5)]
    accent_text = '#17191d' if sum(v*w for v,w in zip(rgb, (.2126,.7152,.0722))) > .45 else '#ffffff'
    style.configure('Accent.TButton', background=colors['accent'], foreground=accent_text)
    style.map('Accent.TButton', background=[('disabled', colors['surface']), ('active', colors['selection'])],
              foreground=[('disabled', colors['muted']), ('active', colors['text'])])
    style.configure('Vertical.TScrollbar', background=colors['surface'], troughcolor=colors['background'], arrowcolor=colors['muted'], borderwidth=0)
    style.configure('Horizontal.TScrollbar', background=colors['surface'], troughcolor=colors['background'], arrowcolor=colors['muted'], borderwidth=0)
    style.configure('TSeparator', background=colors['selection'])
    style.configure('Horizontal.TProgressbar', background=colors['accent'])
    style.configure('Horizontal.TScale',background=colors['accent'],troughcolor=colors['surface'],
                    bordercolor=colors['surface'],lightcolor=colors['accent'],darkcolor=colors['surface'])
    app.option_add('*TCombobox*Listbox.background', colors['surface'])
    app.option_add('*TCombobox*Listbox.foreground', colors['text'])
    def visit(widget):
        if isinstance(widget, tk.Text): widget.configure(background=colors['surface'], foreground=colors['text'], insertbackground=colors['text'], selectbackground=colors['selection'], borderwidth=0, padx=6, pady=4)
        elif isinstance(widget, tk.Canvas): widget.configure(background=colors['background'])
        for child in widget.winfo_children(): visit(child)
    visit(app)
    app.preview.set_palette(colors['viewport'], colors['text'], colors['muted'])
