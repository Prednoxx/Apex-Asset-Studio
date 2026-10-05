from __future__ import annotations

import json
import os
import queue
import subprocess
import sys
import threading
import time
from collections import OrderedDict
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk, colorchooser
from PIL import Image, ImageTk

from ..catalog import Catalog
from ..game_locator import find_apex_installations
from ..rpak.rtech import OodleRuntime
from ..repository import AssetRepository
from ..rpak.model import decode_model
from ..rpak.animation import decode_animation
from ..rpak.material import safe_name, decode_material
from ..rpak.texture import extract_texture
from ..export.package import export_package, export_animation
from .preview import ModelPreview
from . import appearance
from .splash import StartupSplash
from . import cyber

APP_NAME = "Apex Asset Studio"
APP_VERSION = "0.3.1"


class ApexAssetStudioApp(tk.Tk):
    def __init__(self, catalog_path=None, show_splash=True):
        super().__init__()
        self.withdraw()
        self.title(APP_NAME)
        self.geometry("1360x840")
        self.minsize(1040, 660)
        self.option_add("*tearOff", False)
        appdata = Path(os.environ.get("LOCALAPPDATA", Path.home() / ".apex_asset_studio")) / "ApexAssetStudio"
        appdata.mkdir(parents=True, exist_ok=True)
        self.appearance_path = (Path(catalog_path).parent if catalog_path else appdata) / 'appearance.json'
        appearance.register_bundled_fonts()
        self.appearance = appearance.load(self.appearance_path)
        appearance.ACTIVE['style'] = self.appearance['base']
        splash = StartupSplash(self, self.appearance['colors'], self.appearance['mascot_path'] or None, APP_VERSION) if show_splash else None
        if splash: splash.stage('Opening index…')
        self.catalog = Catalog(catalog_path or appdata / "catalog.sqlite3")

        self.game_path = tk.StringVar()
        self.search_var = tk.StringVar()
        self.string_search_var = tk.StringVar()
        self.type_filter_var = tk.StringVar(value="All types")
        self.status_var = tk.StringVar(value="Ready")
        self.progress_var = tk.DoubleVar(value=0)
        self.simple_header_var = tk.StringVar(value="Library")
        self.list_count_var = tk.StringVar(value="")
        self.inspector_title = tk.StringVar(value="Nothing selected")
        self.inspector_meta = tk.StringVar(value="")
        self.frame_text = tk.StringVar(value="")
        self.animation_display = tk.StringVar(value="")
        self.advanced_count_var = tk.StringVar(value="")
        self.simple_search_var = tk.StringVar()
        self.model_choice_var = tk.StringVar()
        self.lod_var = tk.StringVar()
        app_folder = Path(sys.executable).parent if getattr(sys, 'frozen', False) else Path(__file__).resolve().parents[2]
        self.export_path_var = tk.StringVar(value=str(app_folder/'Exports'))
        self.all_lods_var = tk.BooleanVar(value=True)
        self._busy = False
        self._model = None
        self._cosmetic = None
        self._model_choices = []
        self._selection_serial = 0
        self._animation = None
        self._animation_serial = 0
        self._playing = False
        self._play_timer = None
        self.animation_name = tk.StringVar()
        self.frame_var = tk.DoubleVar(value=0)
        self.include_animation = tk.BooleanVar(value=True)
        self.animation_name.trace_add('write', self._update_animation_display)
        self.frame_var.trace_add('write', self._update_frame_text)
        self._animation_picker=None
        self._preview_pixels={};self._preview_cache=OrderedDict()

        self.scan_stop = threading.Event()
        self.events: queue.Queue = queue.Queue()
        self._scan_thread: threading.Thread | None = None
        self._scanning = False
        self._simple_sections: dict[str, tuple[str, ...]] = {}

        if splash: splash.stage('Loading settings…')
        self._build_ui()
        self._apply_appearance(save=False)
        self._update_animation_display()
        self.after(100, self._poll_events)
        if splash: splash.stage('Detecting Apex…')
        self._auto_detect()
        if splash: splash.stage('Loading library…')
        self.refresh_all_views()
        if splash: splash.finish(self)
        else: self.deiconify()

    # ------------------------------------------------------------------ shell
    def _build_ui(self):
        cyber.HazardStrip(self, height=5).pack(fill='x')
        header = ttk.Frame(self, padding=(14, 8, 14, 8))
        header.pack(fill='x')
        self.mascot_label = ttk.Label(header)
        self.mascot_label.pack(side='left', padx=(0, 10))
        cyber.GlitchText(header, APP_NAME, font='brand', jp=f'素材工房  //  BUILD {APP_VERSION}').pack(side='left', padx=(0, 24))
        nav = ttk.Frame(header)
        nav.pack(side='left')
        self.scan_btn = ttk.Button(header, text='SCAN LIBRARY', command=self._scan_button_clicked)
        self.scan_btn.pack(side='right')
        game = ttk.Frame(header)
        game.pack(side='right', padx=(0, 14))
        self.game_dot = ttk.Label(game, text='●', style='Dot.TLabel', cursor='hand2')
        self.game_dot.pack(side='left', padx=(0, 6))
        self.game_label = ttk.Label(game, style='Path.TLabel', cursor='hand2')
        self.game_label.pack(side='left')
        for widget in (self.game_dot, self.game_label):
            widget.bind('<Button-1>', lambda _e: self._show_page(self.appearance_tab))
        self.game_path.trace_add('write', lambda *_: self._update_game_label())
        ttk.Frame(self, style='Hairline.TFrame', height=1).pack(fill='x')

        status = ttk.Frame(self, padding=(14, 5, 14, 6))
        status.pack(side='bottom', fill='x')
        ttk.Label(status, text=' SYS ', style='Tag.TLabel').pack(side='left', padx=(0, 10))
        ttk.Label(status, textvariable=self.status_var, style='Status.TLabel').pack(side='left')
        self.clock_var = tk.StringVar()
        ttk.Label(status, textvariable=self.clock_var, style='Clock.TLabel').pack(side='right', padx=(16, 0))
        self._tick_clock()
        self.progress = ttk.Progressbar(status, variable=self.progress_var, maximum=100, length=260)
        self._status_frame = status
        ttk.Frame(self, style='Hairline.TFrame', height=1).pack(side='bottom', fill='x')

        self.tabs = ttk.Notebook(self, style='Pages.TNotebook')
        self.tabs.pack(fill='both', expand=True)
        self.simple_tab = ttk.Frame(self.tabs)
        self.advanced_tab = ttk.Frame(self.tabs)
        self.diag_tab = ttk.Frame(self.tabs)
        self.appearance_tab = ttk.Frame(self.tabs)
        self.nav_buttons = {}
        self.nav_labels = {}
        for n, (tab, text) in enumerate(((self.simple_tab, 'Library'), (self.advanced_tab, 'Explorer'),
                                         (self.diag_tab, 'Diagnostics'), (self.appearance_tab, 'Settings')), start=1):
            self.tabs.add(tab, text=text); self.nav_labels[str(tab)] = (n, text)
            button = ttk.Button(nav, text=text, style='Nav.TButton', command=lambda t=tab: self._show_page(t))
            button.pack(side='left', padx=(0, 4))
            self.nav_buttons[str(tab)] = button
        self.tabs.bind('<<NotebookTabChanged>>', lambda _e: self._sync_nav())
        self._build_simple()
        self._build_advanced()
        self._build_diag()
        self._build_appearance()
        self._sync_nav()
        self._update_game_label()

    # ------------------------------------------------------------------ library page
    def _show_page(self, tab):
        self.tabs.select(tab)

    def _sync_nav(self):
        current = self.tabs.select(); pattern = appearance.fx()['nav']
        for key, button in self.nav_buttons.items():
            n, label = self.nav_labels[key]
            button.configure(style='NavActive.TButton' if key == current else 'Nav.TButton',
                             text=pattern.format(n=n, label=label, LABEL=label.upper()))

    def _update_game_label(self):
        path = self.game_path.get().strip()
        found = bool(path) and Path(path).exists()
        self.game_label.configure(text='Apex Legends' if found else 'Set Apex folder')
        self.game_dot.configure(style='Dot.TLabel' if found else 'DotOff.TLabel')

    def _placeholder(self, entry, variable, text):
        """Muted hint text inside an empty entry."""
        hint = ttk.Label(entry, text=text, style='Placeholder.TLabel', cursor='xterm')
        def refresh(*_):
            if variable.get() or self.focus_get() is entry: hint.place_forget()
            else: hint.place(x=9, rely=.5, anchor='w')
        hint.bind('<Button-1>', lambda _e: entry.focus_set())
        entry.bind('<FocusIn>', refresh, add='+'); entry.bind('<FocusOut>', refresh, add='+')
        variable.trace_add('write', refresh)
        self.after_idle(refresh)

    SECTION_JP = {'Library': 'ライブラリ', 'Animation': '動作', 'Export': '出力', 'Selected asset': '選択',
                  'Index summary': '概要', 'Scan log': '記録'}

    def _section(self, parent, text, style='Section.Panel.TLabel'):
        return cyber.SectionTag(parent, text, self.SECTION_JP.get(text, ''), on='surface' if 'Panel' in style else 'background', width=80)

    def _tick_clock(self):
        self.clock_var.set(time.strftime('%H:%M:%S') + '  //  ONLINE')
        self.after(1000, self._tick_clock)

    def _show_preview_message(self, text):
        if text:
            headline, _, rest = text.partition('\n\n')
            self.preview_signal.show(rest or headline, headline if rest else None)
            self.preview_signal.place(relx=.5, rely=.17 if appearance.fx()['floor'] == 'sun' else .33, anchor='center')
            self.preview_live.configure(text='○ STANDBY', fg=self.tokens['muted'] if hasattr(self, 'tokens') else '#888888')
        else:
            self.preview_signal.place_forget()
            self.preview_live.configure(text='● LIVE', fg=self.tokens['accent'] if hasattr(self, 'tokens') else '#ff2e88')

    def _swap_selection_tags(self, _event=None):
        # Row tags (rarity colors) override the selection foreground; lift them off the selected row.
        tree = self.simple_assets
        for iid, tags in list(self._held_tags.items()):
            if tree.exists(iid) and iid not in tree.selection(): tree.item(iid, tags=tags)
            if not tree.exists(iid) or iid not in tree.selection(): self._held_tags.pop(iid, None)
        for iid in tree.selection():
            if iid not in self._held_tags: self._held_tags[iid] = tree.item(iid, 'tags'); tree.item(iid, tags=())

    def _debounce_search(self):
        if getattr(self, '_search_job', None): self.after_cancel(self._search_job)
        self._search_job = self.after(250, self._search_simple)

    def _set_inspector(self, title, subtitle=''):
        self._inspector_raw = (title, subtitle)
        upper = appearance.fx()['upper']
        self.inspector_title.set(str(title).upper() if upper else str(title))
        sep = '  //  ' if upper else '  ·  '
        self.inspector_meta.set((str(subtitle).upper() if upper else str(subtitle)).replace('  ·  ', sep))

    def _update_frame_text(self, *_):
        clip = self._animation
        if clip is None: self.frame_text.set('')
        else: self.frame_text.set(f'{int(self.frame_var.get())+1:,} / {clip["frames"]:,}')

    def _update_animation_display(self, *_):
        name = self.animation_name.get()
        self.animation_display.set(name or 'Bind pose. Browse animations to pick a clip.')
        self._update_frame_text()

    def _draw_preset_cards(self):
        """Each card is a miniature of its style: its colors, fonts, ornament, tag and button shape."""
        t = self.tokens; active = appearance.ACTIVE['style']
        for name, card in self.preset_cards.items():
            spec = appearance.STYLES[name]; p = appearance.tokens(spec['colors']); f = appearance.fonts(self, name)
            fx = spec['fx']; chosen = name == self.appearance['preset']
            appearance.ACTIVE['style'] = name  # draw helpers read the active style
            try:
                card.delete('all')
                card.configure(background=p['background'], highlightbackground=t['accent'] if chosen else t['border'],
                               highlightcolor=t['accent'] if chosen else t['border'])
                cyber.draw_ornament(card, p, 0, 0, 304, 6, fx['ornament'])
                title = name.upper() if fx['upper'] else name
                cyber.styled_text(card, 12, 14, title, f['strong'], p)
                card.create_text(12, 40, text=spec['blurb'], anchor='nw', width=170, fill=p['muted'], font=f['small'])
                # mini viewport
                card.create_rectangle(192, 16, 290, 96, fill=p['viewport'], outline=p['border'])
                if fx['floor'] in ('grid', 'sun', 'checker'):
                    if fx['floor'] == 'sun': card.create_oval(222, 38, 260, 76, fill=p['accent'], outline='')
                    card.create_rectangle(193, 58, 289, 95, fill=p['viewport'], outline='')
                    for i in range(7): card.create_line(193 + i*16, 95, 241, 58, fill=p['dim2'] if fx['floor'] == 'sun' else p['dim'])
                    for y in (64, 72, 84): card.create_line(193, y, 289, y, fill=p['dim2'] if fx['floor'] == 'sun' else p['dim'])
                elif fx['floor'] == 'hex':
                    for hx in range(200, 290, 18):
                        for hy in range(26, 96, 16):
                            ox = 9 if (hy // 16) % 2 else 0
                            card.create_polygon(hx+ox, hy-5, hx+ox+5, hy-2, hx+ox+5, hy+3, hx+ox, hy+6, hx+ox-5, hy+3, hx+ox-5, hy-2,
                                                fill='', outline=p['dim'])
                elif fx['floor'] == 'dots':
                    for dx in range(200, 290, 10):
                        for dy in range(24, 96, 10): card.create_oval(dx, dy, dx+2, dy+2, fill=p['dim'], outline='')
                card.create_line(194, 18, 194, 26, fill=p['accent2'], width=2); card.create_line(194, 18, 202, 18, fill=p['accent2'], width=2)
                # selected list row + button
                card.create_rectangle(12, 112, 180, 128, fill=p['accent'], outline='')
                card.create_text(18, 120, text='Airship Assassin', anchor='w', fill=p['accent_text'], font=f['small'])
                if fx['button'] == 'pill':
                    cyber._rounded(card, 192, 112, 290, 136, fill=p['accent'])
                elif fx['button'] == 'pixel':
                    card.create_rectangle(192, 112, 290, 136, fill=p['accent'], outline='')
                    card.create_rectangle(196, 116, 286, 118, fill=appearance.mix('#ffffff', p['accent'], .45), outline='')
                else:
                    card.create_polygon(198, 112, 290, 112, 290, 130, 284, 136, 192, 136, 192, 118, fill=p['accent'], outline='')
                card.create_text(241, 124, text='EXPORT' if fx['upper'] else 'Export', fill=p['accent_text'], font=f['section'])
                card.create_text(12, 152, text=('●  ' if chosen else '') + ('IN USE' if chosen else 'Click to use'), anchor='w',
                                 fill=p['accent2'] if chosen else p['muted'], font=f['section'])
            finally:
                appearance.ACTIVE['style'] = active
        custom = self.appearance['preset'] == 'Custom'
        self.custom_theme_label.configure(text=f"Using custom colors on the {self.appearance['base']} style. Pick a style above to reset them." if custom else '')

    def _build_simple(self):
        f = appearance.fonts(self)
        pane = ttk.Frame(self.simple_tab, style='Hairline.TFrame')
        pane.pack(fill='both', expand=True)
        self.workspace = pane
        nav = ttk.Frame(pane, padding=(8, 16, 4, 10))
        center = ttk.Frame(pane, style='Panel.TFrame', padding=(18, 16, 10, 10))
        detail = ttk.Frame(pane, style='Panel.TFrame', padding=(18, 16, 18, 16))
        self.workspace_panels = nav, center, detail

        # Sidebar: categories and owners with right-aligned counts
        self._section(nav, 'Library', 'Section.TLabel').pack(fill='x', padx=(10, 6), pady=(0, 10))
        nav_body = ttk.Frame(nav)
        nav_body.pack(fill='both', expand=True)
        self.simple_tree = ttk.Treeview(nav_body, columns=('count',), show='tree', selectmode='browse', style='Sidebar.Treeview')
        self.simple_tree.column('#0', width=150, minwidth=120, stretch=True)
        self.simple_tree.column('count', width=58, minwidth=40, anchor='e', stretch=False)
        self.simple_tree.pack(side='left', fill='both', expand=True)
        nav_scroll = ttk.Scrollbar(nav_body, orient='vertical', command=self.simple_tree.yview, style='Sidebar.Vertical.TScrollbar')
        nav_scroll.pack(side='right', fill='y')
        self.simple_tree.configure(yscrollcommand=nav_scroll.set)
        self.simple_tree.bind('<<TreeviewSelect>>', self._simple_section_selected)

        # Item list
        header = ttk.Frame(center, style='Panel.TFrame')
        header.pack(fill='x', padx=(0, 8))
        ttk.Label(header, textvariable=self.simple_header_var, style='Title.Panel.TLabel').pack(side='left')
        ttk.Label(header, textvariable=self.list_count_var, style='Muted.Panel.TLabel').pack(side='left', padx=(10, 0), pady=(7, 0))
        search = ttk.Frame(center, style='Panel.TFrame')
        search.pack(fill='x', pady=(12, 10), padx=(0, 8))
        entry = ttk.Entry(search, textvariable=self.simple_search_var)
        entry.pack(fill='x')
        entry.bind('<Return>', lambda _e: self._search_simple())
        entry.bind('<Escape>', lambda _e: self.simple_search_var.set(''))
        self._placeholder(entry, self.simple_search_var, 'Search this list')
        self.simple_search_var.trace_add('write', lambda *_: self._debounce_search())
        assets_body = ttk.Frame(center, style='Panel.TFrame')
        assets_body.pack(fill='both', expand=True)
        cols = ('name', 'quality', 'state')
        self.simple_assets = ttk.Treeview(assets_body, columns=cols, show='headings', selectmode='browse')
        for column, title, width, stretch in (('name', 'NAME', 140, True), ('quality', 'RARITY', 96, False), ('state', 'MODEL', 104, False)):
            self.simple_assets.heading(column, text=title, anchor='w')
            self.simple_assets.column(column, width=width, minwidth=60, stretch=stretch, anchor='w')
        self.simple_assets.pack(side='left', fill='both', expand=True)
        assets_scroll = ttk.Scrollbar(assets_body, orient='vertical', command=self.simple_assets.yview)
        assets_scroll.pack(side='right', fill='y', padx=(4, 0))
        self.simple_assets.configure(yscrollcommand=assets_scroll.set)
        self.simple_assets.bind('<<TreeviewSelect>>', self._swap_selection_tags)
        self.simple_assets.bind('<<TreeviewSelect>>', self._simple_asset_selected, add='+')
        self._held_tags = {}

        # Inspector
        head = ttk.Frame(detail, style='Panel.TFrame')
        titles = ttk.Frame(head, style='Panel.TFrame')
        titles.pack(side='left', fill='x', expand=True)
        ttk.Label(titles, textvariable=self.inspector_title, style='Title.Panel.TLabel', width=1).pack(fill='x')
        ttk.Label(titles, textvariable=self.inspector_meta, style='Data.Panel.TLabel', width=1).pack(fill='x', pady=(3, 0))
        ttk.Button(head, text='Reset view', style='Ghost.Panel.TButton', command=lambda: self.preview.reset_view()).pack(side='right', anchor='n')


        viewport = ttk.Frame(detail, style='Hairline.TFrame', padding=1)
        self.preview = ModelPreview(viewport, height=300)
        self.preview.pack(fill='both', expand=True)
        self.preview_signal = cyber.Signal(viewport)
        self.preview.message_callback = self._show_preview_message
        self.preview_hint = tk.Label(viewport, text='DRAG ORBIT  //  SHIFT·RMB PAN  //  WHEEL ZOOM', borderwidth=0, font=f['mono_small'])
        self.preview_hint.place(x=28, rely=1, y=-12, anchor='sw')
        self.preview_cam = tk.Label(viewport, text='CAM-01 // 映像', borderwidth=0, font=f['mono_small'])
        self.preview_cam.place(x=28, y=12)
        self.preview_live = tk.Label(viewport, text='○ STANDBY', borderwidth=0, font=f['mono_small'])
        self.preview_live.place(relx=1, x=-28, y=12, anchor='ne')
        for corner, (rx, ry, x, y) in {'nw': (0, 0, 6, 6), 'ne': (1, 0, -6, 6), 'sw': (0, 1, 6, -6), 'se': (1, 1, -6, -6)}.items():
            cyber.Bracket(viewport, corner).place(relx=rx, rely=ry, x=x, y=y, anchor=corner)

        model_bar = ttk.Frame(detail, style='Panel.TFrame')
        ttk.Label(model_bar, text='MODEL', style='Section.Panel.TLabel').pack(side='left', padx=(0, 8))
        self.model_choice = ttk.Combobox(model_bar, textvariable=self.model_choice_var, state='disabled', width=20)
        self.model_choice.pack(side='left', fill='x', expand=True)
        self.model_choice.bind('<<ComboboxSelected>>', lambda _e: self._load_cosmetic_model())
        ttk.Label(model_bar, text='LOD', style='Section.Panel.TLabel').pack(side='left', padx=(16, 8))
        self.lod_choice = ttk.Combobox(model_bar, textvariable=self.lod_var, state='disabled', width=7)
        self.lod_choice.pack(side='left')
        self.lod_choice.bind('<<ComboboxSelected>>', lambda _e: self._render_model())

        self.simple_info = tk.Text(detail, height=3, wrap='word', font=f['small'], state='disabled', cursor='arrow')
        self.simple_info.flush = True; self.simple_info.font_key = 'small'

        anim = ttk.Frame(detail, style='Panel.TFrame')
        top = ttk.Frame(anim, style='Panel.TFrame')
        top.pack(fill='x')
        self._section(top, 'Animation').pack(side='left', fill='x', expand=True, padx=(0, 8))
        self.animation_export_btn = ttk.Button(top, text='Export animation…', style='Ghost.Panel.TButton',
                                               command=self._export_animation, state='disabled')
        self.animation_export_btn.pack(side='right')
        self.animations_btn = ttk.Button(top, text='Browse animations…', style='Ghost.Panel.TButton',
                                         command=self._show_declared_animations, state='disabled')
        self.animations_btn.pack(side='right', padx=(0, 2))
        ttk.Label(anim, textvariable=self.animation_display, style='Panel.TLabel', width=1).pack(fill='x', pady=(4, 6))
        transport = ttk.Frame(anim, style='Panel.TFrame')
        transport.pack(fill='x')
        self.play_btn = ttk.Button(transport, text='Play', width=6, command=self._toggle_animation, state='disabled')
        self.play_btn.pack(side='left')
        ttk.Label(transport, textvariable=self.frame_text, style='Small.Panel.TLabel', width=12, anchor='e').pack(side='right')
        self.frame_slider = ttk.Scale(transport, variable=self.frame_var, command=self._seek_animation, state='disabled',
                                      style='Panel.Horizontal.TScale')
        self.frame_slider.pack(side='left', fill='x', expand=True, padx=(12, 8))

        export = ttk.Frame(detail, style='Panel.TFrame')
        export_top = ttk.Frame(export, style='Panel.TFrame')
        export_top.pack(fill='x')
        self._section(export_top, 'Export').pack(side='left', fill='x', expand=True, padx=(0, 8))
        self.open_source_btn = ttk.Button(export_top, text='Open RPak folder', style='Ghost.Panel.TButton',
                                          command=lambda: self._open_selected_container('simple'))
        self.open_source_btn.pack(side='right')
        self.open_source_btn.state(['disabled'])
        folder = ttk.Frame(export, style='Panel.TFrame')
        folder.pack(fill='x', pady=(4, 10))
        self.export_folder_entry = ttk.Entry(folder, textvariable=self.export_path_var)
        self.export_folder_entry.pack(side='left', fill='x', expand=True)
        self.export_folder_btn = ttk.Button(folder, text='Browse…', command=self._choose_export_folder)
        self.export_folder_btn.pack(side='left', padx=(6, 0))
        bar = ttk.Frame(export, style='Panel.TFrame')
        bar.pack(fill='x')
        self.all_lods_check = ttk.Checkbutton(bar, text='All LODs', variable=self.all_lods_var, style='Panel.TCheckbutton')
        self.all_lods_check.pack(side='left')
        self.include_animation_check = ttk.Checkbutton(bar, text='Include animation', variable=self.include_animation,
                                                       state='disabled', style='Panel.TCheckbutton')
        self.include_animation_check.pack(side='left', padx=(18, 0))
        self.export_btn = cyber.NeonButton(bar, 'Export model', command=self._export_model, jp='出力', height=36, width=240)
        self.export_btn.state(['disabled'])
        self.export_btn.pack(side='right')

        rows = ((head, (0, 12)), (viewport, (0, 10)), (model_bar, (0, 6)), (self.simple_info, (2, 4)),
                (ttk.Separator(detail), (8, 12)), (anim, (0, 0)), (ttk.Separator(detail), (14, 12)), (export, (0, 0)))
        for row, (widget, pady) in enumerate(rows):
            widget.grid(row=row, column=0, sticky='nsew', pady=pady)
        detail.columnconfigure(0, weight=1); detail.rowconfigure(1, weight=1)
        self.simple_info.grid_remove()

    # ------------------------------------------------------------------ settings page
    def _build_appearance(self):
        canvas = tk.Canvas(self.appearance_tab, highlightthickness=0)
        scrollbar = ttk.Scrollbar(self.appearance_tab, orient='vertical', command=canvas.yview)
        scrollbar.pack(side='right', fill='y'); canvas.pack(side='left', fill='both', expand=True)
        canvas.configure(yscrollcommand=scrollbar.set)
        outer = ttk.Frame(canvas, padding=(48, 30, 48, 48))
        window = canvas.create_window((0, 0), window=outer, anchor='nw')
        outer.bind('<Configure>', lambda _e: canvas.configure(scrollregion=canvas.bbox('all')))
        canvas.bind('<Configure>', lambda event: canvas.itemconfigure(window, width=event.width))
        canvas.bind_all('<MouseWheel>', lambda e: canvas.yview_scroll(-1 if e.delta > 0 else 1, 'units')
                        if self.tabs.select() == str(self.appearance_tab) else None, add='+')
        body = ttk.Frame(outer)
        body.pack(anchor='nw', fill='x')
        self.theme_var = tk.StringVar(value=self.appearance['preset'])
        self.layout_var = tk.StringVar(value=self.appearance['layout'])
        self.mascot_var = tk.BooleanVar(value=self.appearance['show_mascot'])

        cyber.GlitchText(body, 'SETTINGS', font='title', jp='設定').pack(anchor='w')
        ttk.Label(body, text='Changes apply immediately and are saved for next time.', style='Muted.TLabel').pack(anchor='w', pady=(4, 0))

        def section(title, hint=None):
            cyber.SectionTag(body, title, width=80, on='background').pack(fill='x', pady=(30, 0))
            if hint: ttk.Label(body, text=hint, style='Muted.TLabel').pack(anchor='w', pady=(4, 0))
            frame = ttk.Frame(body); frame.pack(fill='x', anchor='w', pady=(12, 0))
            return frame

        game = section('Game', 'Where Apex Legends is installed. Detected automatically on Steam and EA app installs.')
        self.path_entry = ttk.Entry(game, textvariable=self.game_path, width=64)
        self.path_entry.pack(side='left', fill='x', expand=True)
        self.detect_btn = ttk.Button(game, text='Detect', command=self._auto_detect)
        self.detect_btn.pack(side='left', padx=(8, 0))
        self.browse_btn = ttk.Button(game, text='Browse…', command=self._browse_game)
        self.browse_btn.pack(side='left', padx=(6, 0))

        themes = section('Theme')
        self.preset_cards = {}
        for index, name in enumerate(appearance.STYLES):
            card = tk.Canvas(themes, width=300, height=168, highlightthickness=2, cursor='hand2', borderwidth=0)
            card.grid(row=index // 3, column=index % 3, padx=(0, 14), pady=(0, 14), sticky='w')
            card.bind('<Button-1>', lambda _e, n=name: self._choose_theme(n))
            self.preset_cards[name] = card
        self.custom_theme_label = ttk.Label(body, text='', style='Muted.TLabel')
        self.custom_theme_label.pack(anchor='w', pady=(8, 0))

        layouts = section('Layout')
        for name, hint in (('Classic Columns', 'Library, list and preview side by side'),
                           ('Preview Focus', 'Larger preview on the right; library and list stacked'),
                           ('Stacked Workspace', 'List above the preview; wide library column')):
            row = ttk.Frame(layouts); row.pack(fill='x', anchor='w', pady=2)
            ttk.Radiobutton(row, text=name, value=name, variable=self.layout_var, command=self._choose_layout,
                            width=20).pack(side='left')
            ttk.Label(row, text=hint, style='Muted.TLabel').pack(side='left')

        colors = section('Custom colors', 'Edit any color to create a custom palette. Use hex values such as #e8503a.')
        self.color_vars = {}; self.color_swatches = {}
        for index, (key, label) in enumerate(appearance.COLOR_LABELS):
            row, column = index % 4, (index // 4) * 4
            ttk.Label(colors, text=label).grid(row=row, column=column, sticky='w', pady=4, padx=(0, 12))
            variable = tk.StringVar(value=self.appearance['colors'][key]); self.color_vars[key] = variable
            entry = ttk.Entry(colors, textvariable=variable, width=10)
            entry.grid(row=row, column=column+1, sticky='w')
            entry.bind('<Return>', lambda _e: self._apply_custom_colors())
            swatch = tk.Label(colors, width=3, background=variable.get(), relief='flat', borderwidth=0, cursor='hand2')
            swatch.grid(row=row, column=column+2, sticky='ns', padx=(6, 40), pady=6)
            swatch.bind('<Button-1>', lambda _e, k=key: self._pick_color(k))
            self.color_swatches[key] = swatch
        buttons = ttk.Frame(body); buttons.pack(anchor='w', pady=(14, 0))
        ttk.Button(buttons, text='Apply colors', command=self._apply_custom_colors).pack(side='left')
        ttk.Button(buttons, text='Reset to default', style='Ghost.TButton', command=self._reset_appearance).pack(side='left', padx=8)

        logo = section('Logo & effects', 'Logo is shown in the header and on the startup screen.')
        self.mascot_portrait = ttk.Label(logo)
        self.mascot_portrait.pack(side='left', anchor='n')
        logo_controls = ttk.Frame(logo); logo_controls.pack(side='left', anchor='n', padx=(24, 0))
        self.scanlines_var = tk.BooleanVar(value=self.appearance.get('scanlines', True))
        ttk.Checkbutton(logo_controls, text='CRT scanlines over the 3D preview', variable=self.scanlines_var,
                        command=self._toggle_scanlines).pack(anchor='w', pady=(0, 6))
        ttk.Checkbutton(logo_controls, text='Show logo in header', variable=self.mascot_var, command=self._toggle_mascot).pack(anchor='w')
        ttk.Button(logo_controls, text='Change logo…', command=self._choose_mascot).pack(anchor='w', pady=(12, 0))
        ttk.Button(logo_controls, text='Use original artwork', style='Ghost.TButton', command=self._restore_mascot).pack(anchor='w', pady=(6, 0))
        self.appearance_status = ttk.Label(body, text='', style='Muted.TLabel')
        self.appearance_status.pack(anchor='w', pady=(18, 0))

    def _apply_layout(self):
        pane = self.workspace; nav, center, detail = self.workspace_panels
        for panel in self.workspace_panels: panel.grid_forget()
        for column in range(3): pane.columnconfigure(column, weight=0, minsize=0, uniform='')
        for row in range(2): pane.rowconfigure(row, weight=0, minsize=0)
        layout = self.appearance['layout']
        self.preview.configure(height=150 if layout == 'Stacked Workspace' else 300)
        self.simple_assets.configure(height=3 if layout == 'Stacked Workspace' else 10)
        if layout == 'Classic Columns':
            nav.grid(row=0, column=0, sticky='nsew', padx=(0, 1))
            center.grid(row=0, column=1, sticky='nsew', padx=(0, 1))
            detail.grid(row=0, column=2, sticky='nsew')
            for i, weight in enumerate((2, 4, 6)): pane.columnconfigure(i, weight=weight)
            pane.columnconfigure(0, minsize=220); pane.columnconfigure(1, minsize=340)
            pane.rowconfigure(0, weight=1)
        elif layout == 'Preview Focus':
            nav.grid(row=0, column=0, sticky='nsew', padx=(0, 1), pady=(0, 1))
            center.grid(row=1, column=0, sticky='nsew', padx=(0, 1))
            detail.grid(row=0, column=1, rowspan=2, sticky='nsew')
            pane.columnconfigure(0, weight=4, uniform='focus'); pane.columnconfigure(1, weight=6, uniform='focus')
            pane.rowconfigure(0, weight=2); pane.rowconfigure(1, weight=3)
        else:
            nav.grid(row=0, column=0, rowspan=2, sticky='nsew', padx=(0, 1))
            center.grid(row=0, column=1, sticky='nsew', pady=(0, 1))
            detail.grid(row=1, column=1, sticky='nsew')
            pane.columnconfigure(0, weight=2, minsize=220); pane.columnconfigure(1, weight=8)
            pane.rowconfigure(0, weight=2); pane.rowconfigure(1, weight=4)

    def _apply_appearance(self, save=True):
        self.appearance_status.configure(text='')
        self.tokens = c = appearance.apply(self, self.appearance)
        f = appearance.fonts(self)
        self.simple_tree.tag_configure('category', foreground=c['accent2'], font=f['section'])
        self.simple_assets.tag_configure('muted', foreground=c['faint'])
        for rarity, color in appearance.RARITY.items(): self.simple_assets.tag_configure(rarity, foreground=color)
        for label, fg in ((self.preview_hint, c['faint']), (self.preview_cam, c['accent2']),
                          (self.preview_live, c['accent'] if self._model else c['muted'])):
            label.configure(background=appearance.mix('#ffffff', c['viewport'], .03 if label is not self.preview_hint else .0), foreground=fg)
        for label in (self.preview_hint, self.preview_cam, self.preview_live): label.configure(font=f['mono_small'])
        cyber.refresh(self, c)
        self._sync_nav()
        if hasattr(self, '_inspector_raw'): self._set_inspector(*self._inspector_raw)
        sel = self.simple_tree.selection()
        if sel and sel[0] in self._simple_sections:
            label = self.simple_tree.item(sel[0], 'text')
            self.simple_header_var.set(label.upper() if appearance.fx()['upper'] else label)
        self._draw_preset_cards(); self._apply_layout(); self._load_mascot()
        if save:
            try:
                appearance.save(self.appearance_path, self.appearance)
            except OSError as exc: self.appearance_status.configure(text=f'Could not save settings: {exc}')

    def _choose_theme(self, name=None):
        name = name or self.theme_var.get()
        self.theme_var.set(name)
        self.appearance['preset'] = name; self.appearance['base'] = name
        self.appearance['colors'] = dict(appearance.STYLES[name]['colors'])
        self.appearance['scanlines'] = appearance.STYLES[name]['fx']['scanlines']
        if hasattr(self, 'scanlines_var'): self.scanlines_var.set(self.appearance['scanlines'])
        self._sync_color_controls(); self._apply_appearance()

    def _sync_color_controls(self):
        for key, color in self.appearance['colors'].items():
            if key in self.color_vars:
                self.color_vars[key].set(color); self.color_swatches[key].configure(background=color)

    def _choose_layout(self, _event=None):
        self.appearance['layout'] = self.layout_var.get(); self._apply_appearance()

    def _pick_color(self, key):
        color = colorchooser.askcolor(color=self.appearance['colors'][key], parent=self, title='Choose '+key+' color')[1]
        if color: self.color_vars[key].set(color); self._apply_custom_colors()

    def _apply_custom_colors(self):
        import re
        colors = {key: variable.get().strip() for key, variable in self.color_vars.items()}
        if any(not re.fullmatch(r'#[0-9a-fA-F]{6}', color) for color in colors.values()):
            self.appearance_status.configure(text='Enter colors as hex values, for example #e8503a.'); return
        if colors == self.appearance['colors']: return
        self.appearance.update(preset='Custom', colors=colors); self.theme_var.set('Custom')
        self._sync_color_controls(); self._apply_appearance()

    def _reset_appearance(self):
        self.appearance = appearance.normalize({}); self.theme_var.set(self.appearance['preset']); self.scanlines_var.set(True)
        self.layout_var.set(self.appearance['layout']); self.mascot_var.set(True)
        self._sync_color_controls(); self._apply_appearance()

    def _toggle_scanlines(self):
        self.appearance['scanlines'] = self.scanlines_var.get(); self._apply_appearance()

    def _toggle_mascot(self):
        self.appearance['show_mascot'] = self.mascot_var.get(); self._apply_appearance()

    def _load_mascot(self):
        path = Path(self.appearance['mascot_path']) if self.appearance['mascot_path'] else Path(__file__).resolve().parents[1]/'resources'/'asuka.webp'
        try:
            with Image.open(path) as image:
                image = image.convert('RGBA')
                portrait = image.copy(); portrait.thumbnail((180, 240), Image.Resampling.LANCZOS)
                self._mascot_portrait_image = ImageTk.PhotoImage(portrait)
                header = image.copy(); header.thumbnail((40, 30), Image.Resampling.LANCZOS)
                self._mascot_image = ImageTk.PhotoImage(header)
                icon = image.copy(); icon.thumbnail((64, 64), Image.Resampling.LANCZOS)
                icon_image = ImageTk.PhotoImage(icon)
            self.mascot_portrait.configure(image=self._mascot_portrait_image)
            if self.appearance['show_mascot']:
                self.mascot_label.configure(image=self._mascot_image); self.mascot_label.pack(side='left', padx=(0, 10), before=self.mascot_label.master.winfo_children()[1])
            else:
                self.mascot_label.pack_forget()
            if hasattr(self, '_icon_image'): return
            self._icon_image = icon_image; self.iconphoto(True, self._icon_image)
        except (OSError, ValueError):
            self.mascot_label.configure(image='')
            self.appearance_status.configure(text='Logo file not found or unsupported.')

    def _choose_mascot(self):
        path = filedialog.askopenfilename(parent=self, title='Choose logo', filetypes=[('Images','*.png *.jpg *.jpeg *.webp'), ('All files','*.*')])
        if not path: return
        try:
            with Image.open(path) as image: image.verify()
        except (OSError, ValueError):
            self.appearance_status.configure(text='Cannot open image.'); return
        self.appearance['mascot_path'] = path; self.appearance['show_mascot'] = True; self.mascot_var.set(True)
        if hasattr(self, '_icon_image'): del self._icon_image
        self._apply_appearance()

    def _restore_mascot(self):
        self.appearance['mascot_path'] = ''; self.appearance['show_mascot'] = True; self.mascot_var.set(True)
        if hasattr(self, '_icon_image'): del self._icon_image
        self._apply_appearance()

    # ------------------------------------------------------------------ explorer page
    def _build_advanced(self):
        page = ttk.Frame(self.advanced_tab, padding=(18, 14, 18, 14))
        page.pack(fill='both', expand=True)
        inner = ttk.Notebook(page)
        inner.pack(fill='both', expand=True)
        assets_tab = ttk.Frame(inner, padding=(0, 12, 0, 0))
        strings_tab = ttk.Frame(inner, padding=(0, 12, 0, 0))
        inner.add(assets_tab, text='Assets')
        inner.add(strings_tab, text='Raw strings')

        top = ttk.Frame(assets_tab, padding=(0, 0, 0, 10))
        top.pack(fill='x')
        entry = ttk.Entry(top, textvariable=self.search_var)
        entry.pack(side='left', fill='x', expand=True, padx=(0, 8))
        entry.bind('<Return>', lambda _e: self.search_advanced())
        self._placeholder(entry, self.search_var, 'Search by name, GUID or container')
        self.type_filter = ttk.Combobox(top, textvariable=self.type_filter_var, state='readonly', width=14)
        self.type_filter.pack(side='left', padx=(0, 8))
        self.type_filter.bind('<<ComboboxSelected>>', lambda _e: self.search_advanced())
        ttk.Button(top, text='Search', command=self.search_advanced).pack(side='left')
        ttk.Button(top, text='Clear', style='Ghost.TButton', command=self._clear_advanced_search).pack(side='left', padx=(4, 0))
        ttk.Label(top, textvariable=self.advanced_count_var, style='Muted.TLabel').pack(side='right', padx=(12, 0))

        asset_pane = ttk.Panedwindow(assets_tab, orient='vertical')
        asset_pane.pack(fill='both', expand=True)
        table_frame = ttk.Frame(asset_pane, style='Panel.TFrame')
        detail_frame = ttk.Frame(asset_pane, style='Panel.TFrame', padding=(14, 12, 14, 0))
        asset_pane.add(table_frame, weight=4)
        asset_pane.add(detail_frame, weight=1)

        cols = ('type', 'name', 'guid', 'ver', 'hdr', 'pak', 'patch', 'compression', 'starpak')
        self.asset_table = ttk.Treeview(table_frame, columns=cols, show='headings', selectmode='browse')
        widths = {'type': 64, 'name': 260, 'guid': 150, 'ver': 50, 'hdr': 76, 'pak': 240, 'patch': 70, 'compression': 120, 'starpak': 100}
        labels = {'type': 'TYPE', 'name': 'NAME', 'guid': 'GUID', 'ver': 'VER', 'hdr': 'HEADER', 'pak': 'CONTAINER',
                  'patch': 'PATCH', 'compression': 'COMPRESSION', 'starpak': 'STARPAK'}
        for c in cols:
            self.asset_table.heading(c, text=labels[c], anchor='w')
            self.asset_table.column(c, width=widths[c], stretch=c in ('name', 'pak'), anchor='w')
        yscroll = ttk.Scrollbar(table_frame, orient='vertical', command=self.asset_table.yview)
        xscroll = ttk.Scrollbar(table_frame, orient='horizontal', command=self.asset_table.xview)
        self.asset_table.configure(yscrollcommand=yscroll.set, xscrollcommand=xscroll.set)
        xscroll.pack(side='bottom', fill='x'); yscroll.pack(side='right', fill='y')
        self.asset_table.pack(fill='both', expand=True)
        self.asset_table.bind('<<TreeviewSelect>>', self._advanced_asset_selected)

        detail_header = ttk.Frame(detail_frame, style='Panel.TFrame')
        detail_header.pack(fill='x')
        self._section(detail_header, 'Selected asset').pack(side='left', fill='x', expand=True, padx=(0, 8))
        self.advanced_open_btn = ttk.Button(detail_header, text='Open RPak folder', style='Ghost.Panel.TButton',
                                            command=lambda: self._open_selected_container('advanced'))
        self.advanced_open_btn.pack(side='right')
        self.advanced_open_btn.state(['disabled'])
        self.advanced_preview_btn = ttk.Button(detail_header, text='Preview model', command=self._preview_advanced, state='disabled')
        self.advanced_preview_btn.pack(side='right', padx=6)
        self.asset_detail = tk.Text(detail_frame, height=8, font=appearance.fonts(self)['mono'], wrap='none', state='disabled')
        self.asset_detail.flush = True; self.asset_detail.font_key = 'mono'
        self.asset_detail.pack(fill='both', expand=True, pady=(8, 0))

        string_top = ttk.Frame(strings_tab, padding=(0, 0, 0, 10))
        string_top.pack(fill='x')
        string_entry = ttk.Entry(string_top, textvariable=self.string_search_var)
        string_entry.pack(side='left', fill='x', expand=True, padx=(0, 8))
        string_entry.bind('<Return>', lambda _e: self.search_strings())
        self._placeholder(string_entry, self.string_search_var, 'Search readable strings inside every RPak')
        ttk.Button(string_top, text='Search', command=self.search_strings).pack(side='left')
        ttk.Button(string_top, text='Clear', style='Ghost.TButton', command=self._clear_string_search).pack(side='left', padx=(4, 0))

        string_frame = ttk.Frame(strings_tab, style='Panel.TFrame')
        string_frame.pack(fill='both', expand=True)
        string_cols = ('value', 'container', 'compression')
        self.string_table = ttk.Treeview(string_frame, columns=string_cols, show='headings')
        for key, title, width, stretch in (('value', 'VALUE', 700, True), ('container', 'CONTAINER', 360, True), ('compression', 'COMPRESSION', 110, False)):
            self.string_table.heading(key, text=title, anchor='w')
            self.string_table.column(key, width=width, stretch=stretch, anchor='w')
        string_scroll = ttk.Scrollbar(string_frame, orient='vertical', command=self.string_table.yview)
        string_scroll.pack(side='right', fill='y'); self.string_table.configure(yscrollcommand=string_scroll.set)
        self.string_table.pack(fill='both', expand=True)

    # ------------------------------------------------------------------ diagnostics page
    def _build_diag(self):
        page = ttk.Frame(self.diag_tab, padding=(18, 14, 18, 14))
        page.pack(fill='both', expand=True)
        header = ttk.Frame(page)
        header.pack(fill='x', pady=(0, 12))
        cyber.GlitchText(header, 'DIAGNOSTICS', font='title', jp='診断').pack(side='left')
        ttk.Button(header, text='Save report…', command=self.save_report).pack(side='right')
        ttk.Button(header, text='Show failures', command=self.show_failures).pack(side='right', padx=6)
        ttk.Button(header, text='Refresh', style='Ghost.TButton', command=self.refresh_summary).pack(side='right')
        tiles = ttk.Frame(page)
        tiles.pack(fill='x', pady=(0, 12))
        self.stat_vars = {}
        for i, (key, label) in enumerate((('containers', 'RPak containers'), ('assets', 'Indexed assets'),
                                          ('cosmetics', 'Cosmetics'), ('failed', 'Failed containers'))):
            card = ttk.Frame(tiles, style='Card.TFrame', padding=(16, 12, 16, 12))
            card.grid(row=0, column=i, sticky='nsew', padx=(0 if i == 0 else 12, 0))
            tiles.columnconfigure(i, weight=1, uniform='stats')
            self.stat_vars[key] = tk.StringVar(value='–')
            ttk.Label(card, textvariable=self.stat_vars[key], style='Stat.Card.TLabel').pack(anchor='w')
            ttk.Label(card, text=label, style='Small.Card.TLabel').pack(anchor='w', pady=(2, 0))
        pane = ttk.Panedwindow(page, orient='vertical')
        pane.pack(fill='both', expand=True)
        mono = appearance.fonts(self)['mono']
        summary_frame = ttk.Frame(pane, style='Panel.TFrame', padding=(14, 12, 14, 0))
        log_frame = ttk.Frame(pane, style='Panel.TFrame', padding=(14, 12, 14, 0))
        pane.add(summary_frame, weight=1)
        pane.add(log_frame, weight=2)
        self._section(summary_frame, 'Index summary').pack(fill='x')
        self.summary_text = tk.Text(summary_frame, height=14, font=mono, wrap='none', state='disabled')
        self.summary_text.flush = True; self.summary_text.font_key = 'mono'
        self.summary_text.pack(fill='both', expand=True, pady=(8, 0))
        self._section(log_frame, 'Scan log').pack(fill='x')
        self.log_text = tk.Text(log_frame, font=mono, wrap='none')
        self.log_text.flush = True; self.log_text.font_key = 'mono'
        self.log_text.pack(fill='both', expand=True, pady=(8, 0))

    def _auto_detect(self):
        if self._scanning:
            return
        installs = find_apex_installations()
        if installs:
            self.game_path.set(str(installs[0]))
            self.status_var.set(f"Detected Apex: {installs[0]}")
        elif not self.game_path.get():
            self.status_var.set("Apex not found. Select its installation folder.")

    def _browse_game(self):
        if self._scanning:
            return
        p = filedialog.askdirectory(title="Select Apex Legends installation")
        if p:
            self.game_path.set(p)
            self.status_var.set(f"Apex path: {p}")

    def _scan_button_clicked(self):
        if self._scanning:
            if not self.scan_stop.is_set():
                self.scan_stop.set()
                self.scan_btn.configure(text="Stopping…")
                self.scan_btn.state(["disabled"])
                self.status_var.set("Stopping scan after the current RPak…")
            return
        self.start_scan()

    def _set_scanning(self, scanning: bool):
        self._scanning = scanning
        for widget in (self.all_lods_check, self.export_folder_entry, self.export_folder_btn):
            widget.state(['disabled' if scanning else '!disabled'])
        if scanning:
            self._selection_serial += 1
            self._model = None
            self._animation=None;self._animation_serial+=1;self._playing=False;self.animation_name.set('')
            self.play_btn.configure(text='Play')
            for widget in (self.play_btn,self.frame_slider,self.animation_export_btn,self.include_animation_check): widget.state(['disabled'])
            self.export_btn.state(['disabled'])
            self.animations_btn.state(['disabled'])
            self.open_source_btn.state(['disabled'])
            self.preview.clear('Scanning library…')
            self.model_choice.configure(state='disabled')
            self.lod_choice.configure(state='disabled')
        if scanning:
            self.progress.pack(side="right")
            self.scan_btn.configure(text="Stop Scan")
            self.scan_btn.state(["!disabled"])
            self.path_entry.state(["disabled"])
            self.detect_btn.state(["disabled"])
            self.browse_btn.state(["disabled"])
        else:
            self.progress.pack_forget()
            self.scan_btn.configure(text="Scan Library")
            self.scan_btn.state(["!disabled"])
            self.path_entry.state(["!disabled"])
            self.detect_btn.state(["!disabled"])
            self.browse_btn.state(["!disabled"])
            self.scan_stop.clear()

    def start_scan(self):
        if self._busy:
            return
        root = Path(self.game_path.get().strip())
        if not root.exists():
            messagebox.showerror(APP_NAME, "Select the Apex Legends folder.")
            return
        if self._scan_thread and self._scan_thread.is_alive():
            return

        self.scan_stop.clear()
        self.progress_var.set(0)
        self.log_text.delete("1.0", "end")
        self._set_scanning(True)
        self.status_var.set("Scanning Apex asset library…")

        def progress(msg, cur, total):
            self.events.put(("progress", msg, cur, total))

        def worker():
            try:
                stats = self.catalog.scan_game(root, progress, self.scan_stop)
                self.events.put(("done", stats))
            except Exception as exc:
                self.events.put(("error", f"{type(exc).__name__}: {exc}"))

        self._scan_thread = threading.Thread(target=worker, daemon=True)
        self._scan_thread.start()

    def _poll_events(self):
        try:
            while True:
                event = self.events.get_nowait()
                if event[0] == "progress":
                    _, msg, cur, total = event
                    self.status_var.set(msg)
                    self.progress_var.set((cur / max(total, 1)) * 100)
                    # Keep diagnostics readable: log actual work and sparse skip milestones.
                    if not msg.startswith("Up to date:") or cur % 250 == 0:
                        self._log(f"[{cur}/{total}] {msg}")
                elif event[0] == "done":
                    stats = event[1]
                    self._set_scanning(False)
                    if stats.stopped:
                        self.status_var.set(
                            f"Scan stopped: {stats.containers_ok} updated, {stats.containers_skipped} unchanged, {stats.containers_failed} failed"
                        )
                    else:
                        self.status_var.set(
                            f"Scan complete: {stats.containers_ok} updated, {stats.containers_skipped} unchanged, {stats.containers_failed} failed"
                        )
                        self.progress_var.set(100)
                    self.refresh_all_views()
                elif event[0] == "error":
                    self._set_scanning(False)
                    self.status_var.set(event[1])
                    self._log(event[1])
                elif event[0] == 'model_ready':
                    _,serial,model,warnings = event
                    self._set_busy(False)
                    if serial != self._selection_serial:
                        continue
                    self._model = model
                    self.lod_choice.configure(values=[f'LOD {x}' for x in sorted(model.lods)],state='readonly')
                    level = min(model.lods)
                    self.lod_var.set(f'LOD {level}')
                    self._render_model()
                    self.export_btn.state(['!disabled'] if model.material_family_resolved else ['disabled'])
                    self.open_source_btn.state(['!disabled'])
                    self.animations_btn.state(['!disabled'])
                    total = sum(len(m.positions) for m in model.lods[min(model.lods)])
                    title = self._cosmetic['name'] if self._cosmetic else Path(model.name).stem
                    owner = f'{self._cosmetic["owner_name"]}  ·  {self.model_choice_var.get()}  ·  ' if self._cosmetic else ''
                    self._set_inspector(title, f'{owner}{total:,} vtx  ·  {len(model.bones)} bones  ·  {len(model.lods)} lod')
                    self._set_simple_info('\n'.join(warnings+model.warnings) + ('' if model.material_family_resolved else
                        '\nThis skin\'s material set is not decoded yet, so export is disabled.'))
                    self.status_var.set('Model loaded.' if model.material_family_resolved else 'Model loaded. Material set unavailable.')
                    if model.material_family_resolved: self._load_preview_textures(model,serial)
                elif event[0]=='preview_textures':
                    _,serial,textures,errors=event
                    if serial!=self._selection_serial: continue
                    self._preview_pixels.update(textures)
                    self.preview.set_textures(textures)
                    if self._animation_picker: self._animation_picker['preview'].set_textures(textures)
                    for error in errors: self._log(error)
                elif event[0]=='preview_cached':
                    _,key,sources,textures=event
                    self._preview_cache[key]=(sources,textures)
                    while sum(len(v[2]) for _,images in self._preview_cache.values() for v in images.values())>96*1024**2:
                        self._preview_cache.popitem(last=False)
                elif event[0] == 'work_error':
                    _,serial,error = event
                    self._set_busy(False)
                    if serial != self._selection_serial: continue
                    if self._model: self._render_model()
                    else: self.preview.clear('Preview unavailable')
                    self._set_simple_info(error)
                    self.status_var.set(error)
                    self._log(error)
                elif event[0] == 'work_progress':
                    self.status_var.set(event[1])
                elif event[0] in ('animation_ready','animation_error'):
                    _,serial,result=event
                    if serial!=self._animation_serial: continue
                    self._set_busy(False)
                    if self._animation_picker:
                        self._animation_picker['ready'](result,event[0]=='animation_error')
                        continue
                    if event[0]=='animation_error':
                        self.status_var.set(result); self._log(result)
                    else:
                        self._apply_animation(result)
                        data=f'{result["mapped_bones"]} bones'
                        if result['ik_rules']: data+=f' · {result["ik_rules"]} IK rules unapplied'
                        if result['autolayers']: data+=f' · {result["autolayers"]} autolayers unapplied'
                        self.status_var.set(data)
                        self._set_busy(False)
                elif event[0] == 'export_ready':
                    self._set_busy(False)
                    _,path,manifest = event
                    self.export_btn.state(['!disabled'] if self._model and self._model.material_family_resolved else ['disabled'])
                    self.status_var.set(f'Export saved ({manifest["status"]}): {path.parent}')
                    self._log(f'Export manifest: {path}')
        except queue.Empty:
            pass
        self.after(100, self._poll_events)

    def refresh_all_views(self):
        self.refresh_summary()
        self.refresh_simple_library()
        self.refresh_type_filter()
        self.search_advanced()

    # ------------------------------------------------------------------ library data
    def refresh_simple_library(self):
        self.simple_tree.delete(*self.simple_tree.get_children())
        self.simple_assets.delete(*self.simple_assets.get_children())
        self._simple_sections.clear()
        self.list_count_var.set('')
        if self.catalog.index_outdated:
            self.simple_header_var.set('Library')
            self.preview.clear('No library yet\n\nPress “Scan library” to index your Apex install.')
            self._set_inspector('Nothing selected'); self._set_simple_info('')
            self.status_var.set('Scan required')
            return
        owners = self.catalog.cosmetic_owners()
        categories = {}
        if owners:
            iid = self.simple_tree.insert('', 'end', text='All cosmetics', values=(f'{sum(o["count"] for o in owners):,}',))
            self._simple_sections[iid] = ('owner', None)
        for owner in owners:
            category = owner['category']
            if category not in categories:
                categories[category] = self.simple_tree.insert('', 'end', text='// ' + str(category).upper(), open=True, tags=('category',))
            iid = self.simple_tree.insert(categories[category], 'end', text=owner['owner_name'], values=(f'{owner["count"]:,}',))
            self._simple_sections[iid] = ('owner', owner['owner_guid'])
        sections = [s for s in self.catalog.simple_sections() if 'mdl_' in s['types']]
        if not sections and not owners:
            self.simple_header_var.set('Library')
            self.preview.clear('No models in the index')
            self._set_inspector('Nothing selected'); self._set_simple_info('')
            return
        if sections:
            group = self.simple_tree.insert('', 'end', text='// RAW ASSETS', open=True, tags=('category',))
            for section in sections:
                iid = self.simple_tree.insert(group, 'end', text=section['label'], values=(f'{section["count"]:,}',))
                self._simple_sections[iid] = ('raw', tuple(section['types']))

        first = next(iter(self._simple_sections), None)
        if first is None: return
        self.simple_tree.selection_set(first)
        self.simple_tree.focus(first)
        self._load_simple_section(first)

    def _simple_section_selected(self, _event=None):
        sel = self.simple_tree.selection()
        if not sel:
            return
        iid = sel[0]
        if iid not in self._simple_sections:
            return
        self._load_simple_section(iid)

    def _load_simple_section(self, iid: str):
        spec = self._simple_sections.get(iid)
        if not spec or self._scanning or self._busy:
            return
        label = self.simple_tree.item(iid, 'text')
        self.simple_header_var.set(label.upper() if appearance.fx()['upper'] else label)
        text = self.simple_search_var.get().strip()
        if spec[0] == 'owner':
            rows = self.catalog.search_cosmetics(text, owner_guid=spec[1])
        else:
            rows = self.catalog.search_assets(text, asset_type='mdl_', limit=2500)
        self.simple_assets.delete(*self.simple_assets.get_children()); self._held_tags = {}
        for r in rows:
            if spec[0] == 'owner':
                models = json.loads(r['details']).get('models', [])
                found = any(m.get('pak_name') for m in models)
                self.simple_assets.insert('', 'end', iid=f'cosmetic:{r["id"]}', tags=(str(r['quality']).lower(),) if found else ('muted',),
                                          values=(r['name'], r['quality'], 'Ready' if found else 'Unresolved'))
            else:
                self.simple_assets.insert('', 'end', iid=f'simple:{r["id"]}',
                                          values=(r['name'] or f'Unnamed {r["guid"]}', r['type'], r['decode_status']))
        self.list_count_var.set(f'{len(rows):,} item' + ('' if len(rows) == 1 else 's'))
        self.preview.clear('Select an item to preview it')
        self._set_inspector('Nothing selected', 'Pick an item from the list.')
        self._set_simple_info('')
        self.open_source_btn.state(['disabled'])
        self._model = None
        self._animation = None; self._playing = False; self._animation_serial += 1
        self.animation_name.set(''); self.play_btn.configure(text='Play')
        for widget in (self.play_btn, self.frame_slider, self.animation_export_btn, self.include_animation_check): widget.state(['disabled'])
        self.export_btn.state(['disabled'])
        self.animations_btn.state(['disabled'])

    def _simple_asset_selected(self, _event=None):
        if self._busy or self._scanning: return
        sel = self.simple_assets.selection()
        if not sel:
            return
        self._selection_serial += 1
        self._model = None
        self.export_btn.state(['disabled'])
        self.animations_btn.state(['disabled'])
        self.model_choice.configure(state='disabled')
        self.lod_choice.configure(state='disabled')
        if sel[0].startswith('cosmetic:'):
            row = self.catalog.get_cosmetic(int(sel[0].split(':')[1]))
            if row is None: return
            self._cosmetic = dict(row)
            self._set_inspector(self._cosmetic.get('name', ''), '  ·  '.join(str(x) for x in (self._cosmetic.get('owner_name'), self._cosmetic.get('quality')) if x))
            self._model_choices = json.loads(row['details']).get('models',[])
            self.model_choice.configure(values=[self._model_label(x) for x in self._model_choices],state='readonly' if self._model_choices else 'disabled')
            if self._model_choices:
                self.model_choice_var.set(self._model_label(self._model_choices[0]))
                self._load_cosmetic_model()
            else:
                self.preview.clear('This cosmetic has no linked model yet')
                self._set_simple_info('Model reference unresolved.')
            return
        self._cosmetic = None
        asset_id = int(sel[0].split(":", 1)[1])
        row = self.catalog.get_asset(asset_id)
        if row is None:
            return
        self._show_asset_metadata(row, simple=True)
        if row['type'] == 'mdl_':
            self._start_model_load(row['guid'],row['path'],None)

    def _advanced_asset_selected(self, _event=None):
        sel = self.asset_table.selection()
        if not sel:
            return
        asset_id = int(sel[0].split(":", 1)[1])
        row = self.catalog.get_asset(asset_id)
        if row is None:
            return
        self._show_asset_metadata(row, simple=False)

    def _show_asset_metadata(self, row, simple: bool):
        lines = [
            f"Type:              {row['type']}",
            f"GUID:              {row['guid']}",
            f"Asset version:     {row['version']}",
            f"Header size:       {row['header_size']}",
            f"Container:         {row['filename']}",
            f"Container path:    {row['path']}",
            f"Compression:       {row['compression']}",
            f"Patch count:       {row['patch_count']}",
            f"StarPak offset:    {row['starpak_offset'] or '(none)'}",
            f"StarPak index:     {row['starpak_index'] if row['starpak_index'] is not None else '(none)'}",
            f"Opt StarPak:       {row['opt_starpak_offset'] or '(none)'}",
        ]

        if simple:
            self._set_inspector(row['name'] or f'Unnamed {row["guid"]}', f'{row["type"]}  ·  {row["filename"]}')
            if row["type"] == "mdl_":
                self.preview.clear("Loading model…")
            else:
                self.preview.clear(f"No 3D preview for asset type {row['type']}")
            self._set_simple_info("\n".join(lines))
            self.open_source_btn.state(["!disabled"])
        else:
            lines += [f'Name:              {row["name"] or "unresolved"}',f'Decode status:     {row["decode_status"]}',f'Decode error:      {row["decode_error"] or "none"}',row['details'] or '']
            edges = self.catalog.dependencies(row['id'])
            lines += ['','Registered GUID references (raw dependencies):']
            lines += [f'{e["guid"]}  page {e["page"]}+{e["offset"]}  {e["type"] or "unresolved"}  {e["name"] or ""}  {e["filename"] or ""}' for e in edges[:100]]
            self._set_asset_detail("\n".join(lines))
            self.advanced_open_btn.state(["!disabled"])
            self.advanced_preview_btn.state(['!disabled'] if row['type']=='mdl_' and not self._busy else ['disabled'])

    def refresh_type_filter(self):
        values = ["All types", *self.catalog.asset_types()]
        self.type_filter.configure(values=values)
        if self.type_filter_var.get() not in values:
            self.type_filter_var.set("All types")

    def search_advanced(self):
        text = self.search_var.get().strip()
        chosen = self.type_filter_var.get()
        asset_type = None if chosen == "All types" else chosen
        rows = self.catalog.search_assets(text, asset_type=asset_type, limit=3000)
        self.asset_table.delete(*self.asset_table.get_children())
        for r in rows:
            self.asset_table.insert(
                "", "end", iid=f"asset:{r['id']}",
                values=(
                    r["type"], r['name'] or '(unresolved)', r["guid"], r["version"], r["header_size"], r["filename"],
                    r["patch_count"], r["compression"], r["starpak_offset"] or "",
                ),
            )
        self.advanced_count_var.set(f"{len(rows):,} shown")
        self._set_asset_detail('')
        self.advanced_open_btn.state(["disabled"])
        self.advanced_preview_btn.state(['disabled'])

    def _clear_advanced_search(self):
        self.search_var.set("")
        self.type_filter_var.set("All types")
        self.search_advanced()

    def search_strings(self):
        query = self.string_search_var.get().strip()
        self.string_table.delete(*self.string_table.get_children())
        if not query:
            self.status_var.set("Enter a string search term.")
            return
        rows = self.catalog.search_strings(query, limit=3000)
        for r in rows:
            self.string_table.insert("", "end", values=(r["value"], r["filename"], r["compression"]))
        self.status_var.set(f"Raw string search: {len(rows):,} results")

    def _clear_string_search(self):
        self.string_search_var.set("")
        self.string_table.delete(*self.string_table.get_children())

    def refresh_summary(self):
        s = self.catalog.summary()
        if hasattr(self, 'stat_vars'):
            for key, value in (('containers', s['containers']), ('assets', s['assets']), ('cosmetics', s['cosmetics']), ('failed', s['failed'])):
                self.stat_vars[key].set(f'{value:,}')
        game_root = Path(self.game_path.get()) if self.game_path.get().strip() else Path.cwd()
        try:
            oodle = OodleRuntime(game_root).description
        except Exception as exc:
            oodle = f"Backend check failed: {type(exc).__name__}: {exc}"

        lines = [
            f"{APP_NAME} {APP_VERSION}",
            f"Apex path: {self.game_path.get() or '(unset)'}",
            f"Oodle backend: {oodle}",
            f"Index state: {'update required' if self.catalog.index_outdated else 'current'}",
            "",
            f"Containers: {s['containers']}   OK: {s['ok']}   Failed: {s['failed']}",
            f"Indexed assets: {s['assets']:,}",
            f"Indexed readable strings: {s['strings']:,}",
            f"Resolved cosmetics: {s['cosmetics']:,} • Registered dependency references: {s['dependencies']:,}",
            f"Unresolved payloads: {s['unresolved']:,}",
            f"Containers awaiting payload refresh: {s['payload_pending']:,}",
            "",
            "Top asset types:",
        ]
        lines += [f"  {t:<8} {n:>10,}" for t, n in s["types"]]

        groups = self.catalog.failure_groups()
        if groups:
            lines.extend(["", "Failure groups:"])
            for g in groups[:12]:
                error = g["error"].replace("\n", " ")
                if len(error) > 110:
                    error = error[:107] + "..."
                lines.append(f"  {g['n']:>5,}  {g['compression']:<10}  {error}")

        self.summary_text.configure(state="normal")
        self.summary_text.delete("1.0", "end")
        self.summary_text.insert("1.0", "\n".join(lines))
        self.summary_text.configure(state="disabled")

    def show_failures(self):
        self.log_text.delete("1.0", "end")
        rows = self.catalog.failed_containers(3000)
        if not rows:
            self._log("No failed RPaks.")
            return
        for r in rows:
            self._log(f"{r['filename']} | compression={r['compression']} patch={r['patch_count']}\n  {r['error']}")

    def save_report(self):
        out = filedialog.asksaveasfilename(
            title="Save diagnostics",
            defaultextension=".json",
            filetypes=[("JSON", "*.json")],
            initialfile="ApexAssetStudio_Diagnostics.json",
        )
        if not out:
            return
        report = self.catalog.summary()
        report["app_version"] = APP_VERSION
        report["game_path"] = self.game_path.get()
        try:
            report["oodle_backend"] = OodleRuntime(Path(self.game_path.get()) if self.game_path.get() else Path.cwd()).description
        except Exception as exc:
            report["oodle_backend"] = f"Backend check failed: {type(exc).__name__}: {exc}"
        report["failure_groups"] = [dict(r) for r in self.catalog.failure_groups()]
        report["failures"] = [dict(r) for r in self.catalog.failed_containers(3000)]
        Path(out).write_text(json.dumps(report, indent=2), encoding="utf-8")
        self.status_var.set(f"Saved diagnostic report: {out}")

    def _open_selected_container(self, source: str):
        if source == 'simple' and self._model:
            os.startfile(Path(self._model.source).parent)
            return
        tree = self.simple_assets if source == "simple" else self.asset_table
        sel = tree.selection()
        if not sel:
            return
        asset_id = int(sel[0].split(":", 1)[1])
        row = self.catalog.get_asset(asset_id)
        if row is None:
            return
        folder = Path(row["path"]).parent
        if os.name == "nt":
            os.startfile(folder)
        else:
            subprocess.Popen(["xdg-open", str(folder)])

    def _set_simple_info(self, text: str):
        text = text.strip()
        self.simple_info.configure(state='normal', height=min(5, max(1, len(text.splitlines()))))
        self.simple_info.delete('1.0', 'end')
        self.simple_info.insert('1.0', text)
        self.simple_info.configure(state='disabled')
        if text: self.simple_info.grid()
        else: self.simple_info.grid_remove()

    def _set_asset_detail(self, text: str):
        self.asset_detail.configure(state="normal")
        self.asset_detail.delete("1.0", "end")
        self.asset_detail.insert("1.0", text)
        self.asset_detail.configure(state="disabled")

    def _search_simple(self):
        selected = self.simple_tree.selection()
        if selected:
            self._load_simple_section(selected[0])

    def _set_busy(self, busy):
        self._busy = busy
        if busy:
            self._playing=False; self.play_btn.configure(text='Play')
            if self._play_timer is not None: self.after_cancel(self._play_timer); self._play_timer=None
        state = 'disabled' if busy else '!disabled'
        for widget in (self.scan_btn,self.detect_btn,self.browse_btn,self.path_entry,self.simple_tree,self.simple_assets,
                       self.all_lods_check,self.export_folder_entry,self.export_folder_btn):
            widget.state([state])
        self.export_btn.state(['disabled'] if busy or self._model is None or not self._model.material_family_resolved else ['!disabled'])
        self.animations_btn.state(['disabled'] if busy or self._model is None else ['!disabled'])
        for widget in (self.play_btn,self.frame_slider,self.animation_export_btn,self.include_animation_check):
            widget.state(['disabled'] if busy or self._animation is None else ['!disabled'])
        self.model_choice.configure(state='readonly' if not busy and self._model_choices and self._cosmetic else 'disabled')
        self.lod_choice.configure(state='readonly' if not busy and self._model else 'disabled')
        self.advanced_preview_btn.state(['disabled'])

    @staticmethod
    def _model_label(choice):
        return {'bodyModel':'Full body', 'armsModel':'First-person arms', 'worldModel':'World model',
                'viewModel':'First-person model'}.get(choice['field'], choice['field'])

    def _load_cosmetic_model(self):
        if self._busy or self._scanning or not self._cosmetic: return
        choice = next((x for x in self._model_choices if self._model_label(x)==self.model_choice_var.get()),None)
        if not choice: return
        self._selection_serial += 1
        details = json.loads(self._cosmetic['details'])
        root = Path(self.game_path.get())
        preferred = root/'paks'/'Win64'/choice['pak_name'] if choice.get('pak_name') else None
        self._start_model_load(choice['guid'],preferred,details.get('skin_family'))

    def _start_model_load(self,guid,preferred=None,family=None):
        if self._busy or self._scanning: return
        self._model = None
        self._playing=False; self._animation=None; self._animation_serial+=1
        self._preview_pixels={}
        self.animation_name.set(''); self.play_btn.configure(text='Play')
        self._set_busy(True)
        serial = self._selection_serial
        root = self.game_path.get()
        self.preview.clear('Loading model…')
        self.status_var.set('Loading model…')
        def worker():
            try:
                with AssetRepository(self.catalog,root) as repo:
                    archive,asset = repo.asset(guid,preferred)
                    model = decode_model(archive,asset,family,allow_unresolved_family=True)
                    warnings = sorted(repo.warnings)
                self.events.put(('model_ready',serial,model,warnings))
            except Exception as exc:
                self.events.put(('work_error',serial,f'{type(exc).__name__}: {exc}'))
        threading.Thread(target=worker,daemon=True).start()

    def _render_model(self):
        if not self._model: return
        lod = int(self.lod_var.get().split()[-1])
        self.preview.set_model(self._model,lod)
        if self._animation: self.preview.set_pose(self._animation,int(self.frame_var.get()))

    def _load_preview_textures(self,model,serial):
        root=self.game_path.get()
        cache=self.appearance_path.parent/'preview_textures_v2'
        key=(root,model.guid,model.family,tuple(model.materials))
        cached=self._preview_cache.get(key)
        if cached:
            sources,textures=cached
            if all(Path(p).exists() and (Path(p).stat().st_size,Path(p).stat().st_mtime_ns)==(size,stamp) for p,size,stamp in sources):
                self._preview_cache.move_to_end(key);self._preview_pixels.update(textures)
                self.preview.set_textures(textures);return
            del self._preview_cache[key]
        def worker():
            textures={};errors=[];sources={Path(model.source)}
            try:
                with AssetRepository(self.catalog,root) as repo:
                    for index in sorted({m.material for meshes in model.lods.values() for m in meshes}):
                        if serial!=self._selection_serial: return
                        try:
                            material=decode_material(repo,model.materials[index],model.source)
                            bindings={t['role']:t for t in material['textures']}
                            if 'basecolor' not in bindings: continue
                            images={}
                            for role in ('basecolor','alpha'):
                                binding=bindings.get(role)
                                if not binding: continue
                                archive,asset=repo.asset(binding['guid'],model.source)
                                stamp=archive.path.stat()
                                folder=cache/f'{binding["guid"]}_{stamp.st_size}_{stamp.st_mtime_ns}'
                                png=folder/'Texture.png'
                                metadata=folder/'Texture.texture.json'
                                info=json.loads(metadata.read_text()) if metadata.exists() else None
                                valid=info is not None and 'source_fingerprints' in info and all(Path(p).exists() and
                                    (Path(p).stat().st_size,Path(p).stat().st_mtime_ns)==(size,stamp) for p,size,stamp in info.get('source_fingerprints',[]))
                                if not png.exists() or not valid:
                                    info=extract_texture(archive,asset,folder,'Texture',preview_size=2048)
                                    if not info['png']: raise ValueError(f'{binding["guid"]}: PNG decoding unavailable')
                                    png=folder/info['png']
                                sources.update(Path(p) for p in info.get('source_files',[]))
                                with Image.open(png) as original:
                                    image=original.convert('RGBA');image.thumbnail((2048,2048),Image.Resampling.LANCZOS)
                                images[role]=image
                                if role=='basecolor': srgb=info['srgb']
                            image=images['basecolor'];image.putalpha(255)
                            if 'alpha' in images:
                                channel=bindings['alpha'].get('scalar_channel')
                                if channel not in ('R','G','B','A'): raise ValueError('Opacity channel is unresolved')
                                alpha=images['alpha'].getchannel(channel).resize(image.size,Image.Resampling.BILINEAR)
                                image.putalpha(alpha)
                            textures[index]=(*image.size,image.tobytes(),srgb)
                            self.events.put(('preview_textures',serial,{index:textures[index]},[]))
                        except (ValueError,KeyError,OSError,RuntimeError) as exc:
                            errors.append(f'{model.materials[index]}: {exc}')
                    sources.update(repo.raw_opened)
                stamps=[(str(p),p.stat().st_size,p.stat().st_mtime_ns) for p in sources]
                if not errors: self.events.put(('preview_cached',key,stamps,textures))
            except Exception as exc: errors.append(f'Texture preview: {type(exc).__name__}: {exc}')
            self.events.put(('preview_textures',serial,{},errors))
        threading.Thread(target=worker,daemon=True).start()

    def _show_declared_animations(self):
        if not self._model or self._busy or self._scanning: return
        if self._animation_picker: self._animation_picker['window'].lift();return
        self._playing=False;self.play_btn.configure(text='Play')
        rows = self.catalog.declared_animations(self._model.guid,self._model.rig_guids)
        unique={}
        for row in rows: unique.setdefault(row['guid'],row)
        rows=list(unique.values())
        window = tk.Toplevel(self); window.title(f'Animations · {self.inspector_title.get()}')
        window.configure(background=self.appearance['colors']['background'])
        window.geometry('1180x700');window.minsize(950,550);window.transient(self);window.grab_set()
        if hasattr(self, '_icon_image'): window.iconphoto(False, self._icon_image)
        heading=ttk.Frame(window,padding=(16,14,16,0));heading.pack(fill='x')
        ttk.Label(heading,text='Animations',style='Title.TLabel').pack(side='left')
        ttk.Label(heading,text=f'{len(rows):,} sequences declared for {self.inspector_title.get()}',style='Muted.TLabel').pack(side='left',padx=(12,0),pady=(6,0))
        query = tk.StringVar(); entry=ttk.Entry(window,textvariable=query);entry.pack(fill='x',padx=16,pady=(12,10))
        self._placeholder(entry,query,'Filter sequences')
        body=ttk.Panedwindow(window,orient='horizontal');body.pack(fill='both',expand=True,padx=16,pady=(0,4))
        frame=ttk.Frame(body,style='Panel.TFrame');body.add(frame,weight=3)
        table=ttk.Treeview(frame,columns=('name','guid','link','source'),show='headings')
        for key,title,width in [('name','SEQUENCE',420),('guid','GUID',150),('link','LINK',130),('source','RPAK',280)]:
            table.heading(key,text=title,anchor='w');table.column(key,width=width,anchor='w')
        table.configure(displaycolumns=('name','source'));table.column('name',width=350);table.column('source',width=160)
        table.pack(side='left',fill='both',expand=True)
        scroll=ttk.Scrollbar(frame,command=table.yview);scroll.pack(side='right',fill='y');table.configure(yscrollcommand=scroll.set)
        def refresh(*_):
            table.delete(*table.get_children())
            text=query.get().casefold()
            for i,row in enumerate(rows):
                if text and text not in (str(row['name'])+' '+row['guid']+' '+row['filename']).casefold(): continue
                link='Model + rig' if row['declared_model_link'] and row['declared_rig_links'] else 'Model header' if row['declared_model_link'] else 'Rig header'
                name=Path(row['name'] or '').stem.replace('_',' ').strip().title()
                table.insert('','end',iid=str(i),values=(name,row['guid'],link,row['filename']))
        query_trace=query.trace_add('write',refresh);refresh();entry.focus_set()
        right=ttk.Frame(body,style='Panel.TFrame',padding=(14,14,14,10));body.add(right,weight=2)
        viewport_frame=ttk.Frame(right,style='Hairline.TFrame',padding=1);viewport_frame.pack(fill='both',expand=True)
        viewport=ModelPreview(viewport_frame);viewport.pack(fill='both',expand=True)
        viewport.set_palette(self.appearance['colors']['viewport'],'','')
        viewport.set_model(self._model,int(self.lod_var.get().split()[-1]));viewport.set_textures(self._preview_pixels)
        info=tk.StringVar(value='Select a sequence to load it.');ttk.Label(right,textvariable=info,wraplength=430,style='Panel.TLabel').pack(fill='x',pady=(10,6))
        controls=ttk.Frame(right,style='Panel.TFrame');controls.pack(fill='x',pady=4)
        blend=tk.IntVar(value=0)
        ttk.Label(controls,text='Blend',style='Muted.Panel.TLabel').pack(side='left')
        self._blend_choice=ttk.Spinbox(controls,from_=0,to=0,textvariable=blend,width=5)
        self._blend_choice.pack(side='left',padx=4)
        play=ttk.Button(controls,text='Play',state='disabled');play.pack(side='left',padx=4)
        position=tk.DoubleVar(value=0)
        timeline=ttk.Scale(right,variable=position,state='disabled',style='Panel.Horizontal.TScale');timeline.pack(fill='x',pady=(8,4))
        footer=ttk.Frame(window,padding=(16,10,16,14));footer.pack(fill='x')
        details=tk.BooleanVar(value=False)
        ttk.Checkbutton(footer,text='Show GUID and link columns',variable=details,
            command=lambda:table.configure(displaycolumns=('name','guid','link','source') if details.get() else ('name','source'))).pack(side='left')
        layout_timer=window.after(100,lambda:body.sashpos(0,int(body.winfo_width()*.56)))
        use=ttk.Button(footer,text='Use animation',state='disabled',style='Accent.TButton');use.pack(side='right')
        picker={'window':window,'preview':viewport,'clip':None,'playing':False,'timer':None,'frame':position}
        self._animation_picker=picker
        def tick():
            picker['timer']=None
            if not picker['playing'] or picker['clip'] is None: return
            clip=picker['clip'];value=int((time.perf_counter()-picker['start'])*clip['fps'])
            if value>=clip['frames']:
                if clip['loop']:value%=clip['frames']
                else:value=clip['frames']-1;picker['playing']=False;play.configure(text='Play')
            if int(position.get())!=value:position.set(value);viewport.set_pose(clip,value)
            if picker['playing']:picker['timer']=window.after(max(1,int(1000/clip['fps'])),tick)
        def stop():
            picker['playing']=False;play.configure(text='Play')
            if picker['timer'] is not None:window.after_cancel(picker['timer']);picker['timer']=None
        def toggle():
            if not picker['clip']:return
            if picker['playing']:stop();return
            if position.get()>=picker['clip']['frames']-1:position.set(0)
            picker['playing']=True;play.configure(text='Pause')
            picker['start']=time.perf_counter()-position.get()/picker['clip']['fps'];tick()
        def seek(value):
            if picker['clip']:
                viewport.set_pose(picker['clip'],int(float(value)))
                if picker['playing']:picker['start']=time.perf_counter()-float(value)/picker['clip']['fps']
        play.configure(command=toggle);timeline.configure(command=seek)
        def close(confirm=False):
            clip=picker['clip'];stop();self._animation_serial+=1;self._animation_picker=None
            window.after_cancel(layout_timer)
            query.trace_remove('write',query_trace);picker.pop('ready',None)
            self._set_busy(False);window.grab_release();window.destroy()
            # Worker allocations can collect closed-dialog cycles; release Tcl variables on the UI thread.
            for variable in (query,blend,info,position,details):
                variable.__del__();variable._tk=None
            if confirm and clip is not None:self._apply_animation(clip)
        use.configure(command=lambda:close(True))
        ttk.Button(footer,text='Cancel',command=close).pack(side='right',padx=8)
        window.protocol('WM_DELETE_WINDOW',close);window.bind('<Escape>',lambda e:close())
        def load(*_):
            selected=table.selection()
            if selected and not self._busy:
                stop();picker['clip']=None;use.state(['disabled']);play.state(['disabled']);timeline.state(['disabled'])
                info.set('Loading '+table.item(selected[0],'values')[0]+'…')
                entry.state(['disabled']);self._blend_choice.state(['disabled'])
                self._load_animation(rows[int(selected[0])],blend.get())
        def ready(result,error):
            entry.state(['!disabled']);self._blend_choice.state(['!disabled'])
            if error:info.set(result);return
            picker['clip']=result
            info.set(f'{result["name"]}\n{result["frames"]} frames · {result["fps"]:g} fps · {result["mapped_bones"]} bones')
            self._blend_choice.configure(to=result['blends']-1)
            timeline.configure(to=result['frames']-1);position.set(0);viewport.set_pose(result,0)
            for widget in (use,play,timeline):widget.state(['!disabled'])
            toggle()
        picker['ready']=ready
        def select(*_):
            if self._busy:return
            blend.set(0);self._blend_choice.configure(to=0);load()
        table.bind('<<TreeviewSelect>>',select)
        table.bind('<Button-1>',lambda e:'break' if self._busy else None)
        table.bind('<KeyPress>',lambda e:'break' if self._busy else None)
        self._blend_choice.configure(command=load);self._blend_choice.bind('<Return>',load)
        ttk.Button(controls,text='Reload',style='Ghost.Panel.TButton',command=load).pack(side='left')
        table.bind('<Double-1>',load)

    def _apply_animation(self,clip):
        self._animation=clip;self.include_animation.set(True)
        self.animation_name.set(f'{clip["name"]} · {clip["frames"]} frames · {clip["fps"]:g} fps')
        self.frame_slider.configure(to=clip['frames']-1);self.frame_var.set(0)
        self.preview.set_pose(clip,0);self._set_busy(False)

    def _load_animation(self,row,blend=0):
        if not self._model or self._busy: return
        if not set(row['declared_rig_links']).intersection(self._model.rig_guids):
            self.status_var.set('Sequence has no declared link to this model');return
        self._playing=False;self.play_btn.configure(text='Play')
        if not self._animation_picker:
            self._animation=None;self.animation_name.set('');self.preview.set_pose(None,0)
        self._animation_serial+=1; serial=self._animation_serial
        model=self._model; root=self.game_path.get()
        self._set_busy(True); self.status_var.set('Loading animation…')
        def worker():
            try:
                errors=[]
                with AssetRepository(self.catalog,root) as repository:
                    for rig in row['declared_rig_links']:
                        try:
                            clip=decode_animation(repository,model,row['guid'],rig,blend)
                            clip['sequence_path']=row['name']
                            break
                        except (ValueError,KeyError,RuntimeError) as exc: errors.append(f'{rig}: {exc}')
                    else: raise ValueError('\n'.join(errors) or 'Sequence has no declared rig')
                self.events.put(('animation_ready',serial,clip))
            except Exception as exc: self.events.put(('animation_error',serial,f'{type(exc).__name__}: {exc}'))
        threading.Thread(target=worker,daemon=True).start()

    def _seek_animation(self,value):
        if self._animation and not self._busy:
            self.preview.set_pose(self._animation,int(float(value)))
            if self._playing: self._play_start=time.perf_counter()-float(value)/self._animation['fps']

    def _toggle_animation(self):
        if self._animation is None or self._busy: return
        self._playing=not self._playing
        if self._play_timer is not None: self.after_cancel(self._play_timer); self._play_timer=None
        self.play_btn.configure(text='Pause' if self._playing else 'Play')
        if self._playing:
            if self.frame_var.get()>=self._animation['frames']-1: self.frame_var.set(0)
            self._play_start=time.perf_counter()-self.frame_var.get()/self._animation['fps']
            self._tick_animation()

    def _tick_animation(self):
        self._play_timer=None
        if not self._playing or self._animation is None: return
        clip=self._animation; frame=int((time.perf_counter()-self._play_start)*clip['fps'])
        if frame>=clip['frames']:
            if clip['loop']: frame%=clip['frames']
            else:
                frame=clip['frames']-1; self._playing=False; self.play_btn.configure(text='Play')
        if frame!=int(self.frame_var.get()): self.frame_var.set(frame); self.preview.set_pose(clip,frame)
        if self._playing: self._play_timer=self.after(max(1,int(1000/clip['fps'])),self._tick_animation)

    def _export_animation(self):
        if self._animation is None or self._busy: return
        Path(self.export_path_var.get()).mkdir(parents=True,exist_ok=True)
        path=filedialog.asksaveasfilename(title='Export animation',initialdir=self.export_path_var.get(),
            initialfile=safe_name(self._animation['name'])+'.aas.json',defaultextension='.aas.json',
            filetypes=[('Apex Asset Studio','*.aas.json')],confirmoverwrite=False)
        if not path: return
        if not path.endswith('.aas.json'): path+='.aas.json'
        targets=[Path(path),Path(path).with_name(Path(path).name[:-9]+'.glb')]
        existing=[str(p) for p in targets if p.exists()]
        if existing and not messagebox.askyesno('Replace files?','\n'.join(existing)): return
        model=self._model; clip=self._animation; serial=self._selection_serial
        self._playing=False; self.play_btn.configure(text='Play'); self._set_busy(True)
        def worker():
            try:
                Path(path).parent.mkdir(parents=True,exist_ok=True)
                manifest_path,manifest=export_animation(model,clip,path)
                self.events.put(('export_ready',manifest_path,manifest))
            except Exception as exc: self.events.put(('work_error',serial,f'{type(exc).__name__}: {exc}'))
        threading.Thread(target=worker,daemon=True).start()

    def _preview_advanced(self):
        sel = self.asset_table.selection()
        if not sel or self._busy or self._scanning: return
        row = self.catalog.get_asset(int(sel[0].split(':')[1]))
        if not row or row['type'] != 'mdl_': return
        self._cosmetic = None
        self._model_choices = []
        self._selection_serial += 1
        self.tabs.select(self.simple_tab)
        self._start_model_load(row['guid'],row['path'])

    def _choose_export_folder(self):
        if self._busy: return
        path = filedialog.askdirectory(title='Choose export root',initialdir=self.export_path_var.get())
        if path: self.export_path_var.set(path)

    def _export_model(self):
        if not self._model or not self._model.material_family_resolved or self._busy or self._scanning: return
        model = self._model
        cosmetic = dict(self._cosmetic) if self._cosmetic else None
        label = f'{cosmetic["owner_name"]} - {cosmetic["name"]} - {self.model_choice_var.get()}' if cosmetic else Path(model.name).stem
        root = self.game_path.get(); destination = self.export_path_var.get()
        existing=Path(destination)/safe_name(label)
        overwrite=existing.exists()
        if overwrite and not messagebox.askyesno('Replace export?',str(existing)): return
        all_lods = self.all_lods_var.get(); serial = self._selection_serial
        animation=self._animation if self.include_animation.get() else None
        self._playing=False; self.play_btn.configure(text='Play')
        self._set_busy(True)
        def worker():
            try:
                path,manifest = export_package(model,self.catalog,root,destination,label,cosmetic,all_lods,
                    lambda text:self.events.put(('work_progress',text)),overwrite=overwrite,animation=animation)
                self.events.put(('export_ready',path,manifest))
            except Exception as exc:
                self.events.put(('work_error',serial,f'Export failed: {type(exc).__name__}: {exc}'))
        threading.Thread(target=worker,daemon=True).start()

    def _log(self, text):
        self.log_text.insert("end", str(text) + "\n")
        self.log_text.see("end")


def main():
    app = ApexAssetStudioApp()
    app.mainloop()
