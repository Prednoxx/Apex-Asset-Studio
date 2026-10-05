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

APP_NAME = "Apex Asset Studio"
APP_VERSION = "0.3.1"


class ApexAssetStudioApp(tk.Tk):
    def __init__(self, catalog_path=None, show_splash=True):
        super().__init__()
        self.withdraw()
        splash = StartupSplash(self) if show_splash else None
        self.title(f"{APP_NAME} — {APP_VERSION}")
        self.geometry("1280x800")
        self.minsize(1000, 650)
        self.option_add("*tearOff", False)
        appdata = Path(os.environ.get("LOCALAPPDATA", Path.home() / ".apex_asset_studio")) / "ApexAssetStudio"
        appdata.mkdir(parents=True, exist_ok=True)
        self.appearance_path = (Path(catalog_path).parent if catalog_path else appdata) / 'appearance.json'
        self.appearance = appearance.load(self.appearance_path)
        if splash: splash.stage('Opening index…')
        self.catalog = Catalog(catalog_path or appdata / "catalog.sqlite3")

        self.game_path = tk.StringVar()
        self.search_var = tk.StringVar()
        self.string_search_var = tk.StringVar()
        self.type_filter_var = tk.StringVar(value="All types")
        self.status_var = tk.StringVar(value="Ready")
        self.progress_var = tk.DoubleVar(value=0)
        self.simple_header_var = tk.StringVar(value="Assets")
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
        self.after(100, self._poll_events)
        if splash: splash.stage('Detecting Apex…')
        self._auto_detect()
        if splash: splash.stage('Loading library…')
        self.refresh_all_views()
        if splash: splash.finish(self)
        else: self.deiconify()

    def _build_ui(self):
        brand = ttk.Frame(self, padding=(8, 4))
        brand.pack(fill='x')
        self.mascot_label = ttk.Label(brand)
        self.mascot_label.pack(side='left', padx=(0, 8))
        ttk.Label(brand, text=APP_NAME, style='Accent.TLabel').pack(side='left')
        ttk.Button(brand, text='Appearance…', command=lambda: self.tabs.select(self.appearance_tab)).pack(side='right')
        toolbar = ttk.Frame(self, padding=(8, 7))
        toolbar.pack(fill="x")
        ttk.Label(toolbar, text="Apex:").pack(side="left")
        self.path_entry = ttk.Entry(toolbar, textvariable=self.game_path)
        self.path_entry.pack(side="left", fill="x", expand=True, padx=(6, 6))
        self.detect_btn = ttk.Button(toolbar, text="Detect", command=self._auto_detect)
        self.detect_btn.pack(side="left", padx=2)
        self.browse_btn = ttk.Button(toolbar, text="Browse…", command=self._browse_game)
        self.browse_btn.pack(side="left", padx=2)
        ttk.Separator(toolbar, orient="vertical").pack(side="left", fill="y", padx=8)
        self.scan_btn = ttk.Button(toolbar, text="Scan Library", command=self._scan_button_clicked)
        self.scan_btn.pack(side="left", padx=2)

        self.tabs = ttk.Notebook(self)
        self.tabs.pack(fill="both", expand=True, padx=8, pady=(0, 6))
        self.simple_tab = ttk.Frame(self.tabs)
        self.advanced_tab = ttk.Frame(self.tabs)
        self.diag_tab = ttk.Frame(self.tabs)
        self.appearance_tab = ttk.Frame(self.tabs)
        self.tabs.add(self.simple_tab, text="Simple View")
        self.tabs.add(self.advanced_tab, text="Advanced View")
        self.tabs.add(self.diag_tab, text="Diagnostics")
        self.tabs.add(self.appearance_tab, text="Appearance")
        self._build_simple()
        self._build_advanced()
        self._build_diag()
        self._build_appearance()

        status = ttk.Frame(self, padding=(8, 4))
        status.pack(fill="x")
        ttk.Label(status, textvariable=self.status_var, style="Status.TLabel").pack(side="left")
        self.progress = ttk.Progressbar(status, variable=self.progress_var, maximum=100, length=300)
        self._status_frame = status

    def _build_simple(self):
        pane = ttk.Frame(self.simple_tab)
        pane.pack(fill="both", expand=True)
        self.workspace = pane
        nav = ttk.Frame(pane, padding=6)
        center = ttk.Frame(pane, padding=6)
        detail = ttk.Frame(pane, padding=6)
        self.workspace_panels = nav, center, detail

        ttk.Label(nav, text="Library", style="Title.TLabel").pack(anchor="w", pady=(0, 6))
        nav_body = ttk.Frame(nav); nav_body.pack(fill='both',expand=True)
        self.simple_tree = ttk.Treeview(nav_body, show="tree", selectmode="browse")
        self.simple_tree.pack(side='left',fill="both", expand=True)
        nav_scroll = ttk.Scrollbar(nav_body,orient='vertical',command=self.simple_tree.yview)
        nav_scroll.pack(side='right',fill='y');self.simple_tree.configure(yscrollcommand=nav_scroll.set)
        self.simple_tree.bind("<<TreeviewSelect>>", self._simple_section_selected)

        header = ttk.Frame(center)
        header.pack(fill="x")
        ttk.Label(header, textvariable=self.simple_header_var, style="Title.TLabel").pack(side="left")

        search = ttk.Frame(center)
        search.pack(fill='x',pady=(6,0))
        entry = ttk.Entry(search,textvariable=self.simple_search_var)
        entry.pack(side='left',fill='x',expand=True)
        entry.bind('<Return>',lambda e:self._search_simple())
        ttk.Button(search,text='Search',command=self._search_simple).pack(side='left',padx=(4,0))
        cols = ("name", "quality", "state")
        assets_body = ttk.Frame(center);assets_body.pack(fill='both',expand=True,pady=(7,0))
        self.simple_assets = ttk.Treeview(assets_body, columns=cols, show="headings", selectmode="browse")
        for column,title,width in (('name','Name',240),('quality','Quality / Type',100),('state','Resolution',155)):
            self.simple_assets.heading(column,text=title)
            self.simple_assets.column(column,width=width,stretch=column=='name')
        self.simple_assets.pack(side='left',fill="both", expand=True)
        assets_scroll = ttk.Scrollbar(assets_body,orient='vertical',command=self.simple_assets.yview)
        assets_scroll.pack(side='right',fill='y');self.simple_assets.configure(yscrollcommand=assets_scroll.set)
        self.simple_assets.bind("<<TreeviewSelect>>", self._simple_asset_selected)
        assets_xscroll = ttk.Scrollbar(center, orient='horizontal', command=self.simple_assets.xview)
        assets_xscroll.pack(fill='x'); self.simple_assets.configure(xscrollcommand=assets_xscroll.set)

        preview_header=ttk.Frame(detail)
        ttk.Label(preview_header,text='Preview',style='Title.TLabel').pack(side='left')
        ttk.Button(preview_header,text='Reset view',command=lambda:self.preview.reset_view()).pack(side='right')
        self.preview = ModelPreview(detail, height=300)
        self.preview.pack(fill="both", expand=True, pady=(6, 6))
        model_bar = ttk.Frame(detail); model_bar.pack(fill='x')
        self.model_choice = ttk.Combobox(model_bar,textvariable=self.model_choice_var,state='disabled',width=20)
        self.model_choice.pack(side='left',fill='x',expand=True)
        self.model_choice.bind('<<ComboboxSelected>>',lambda e:self._load_cosmetic_model())
        self.lod_choice = ttk.Combobox(model_bar,textvariable=self.lod_var,state='disabled',width=8)
        self.lod_choice.pack(side='left',padx=(4,0))
        self.lod_choice.bind('<<ComboboxSelected>>',lambda e:self._render_model())
        self.simple_info = tk.Text(detail, height=6, wrap="word", font=("Segoe UI", 9), state="disabled")
        self.simple_info.pack(fill="x")

        actions = ttk.Frame(detail)
        actions.pack(fill="x", pady=(6, 0))
        self.open_source_btn = ttk.Button(actions, text="Open Container Folder", command=lambda: self._open_selected_container("simple"))
        self.open_source_btn.pack(side="left")
        self.open_source_btn.state(["disabled"])
        self.animations_btn = ttk.Button(actions,text='Animations…',command=self._show_declared_animations,state='disabled')
        self.animations_btn.pack(side='left',padx=(4,0))
        playback=ttk.Frame(detail)
        ttk.Label(playback,textvariable=self.animation_name).pack(fill='x')
        self.play_btn=ttk.Button(playback,text='Play',command=self._toggle_animation,state='disabled')
        self.play_btn.pack(side='left')
        self.frame_slider=ttk.Scale(playback,variable=self.frame_var,command=self._seek_animation,state='disabled')
        self.frame_slider.pack(side='left',fill='x',expand=True,padx=4)
        self.animation_export_btn=ttk.Button(playback,text='Export animation…',command=self._export_animation,state='disabled')
        self.animation_export_btn.pack(side='left')
        export_bar = ttk.Frame(detail); export_bar.pack(fill='x',pady=(6,0))
        self.export_btn = ttk.Button(export_bar,text='Export model…',command=self._export_model,state='disabled',style='Accent.TButton')
        self.export_btn.pack(side='left')
        self.all_lods_check = ttk.Checkbutton(export_bar,text='All LODs',variable=self.all_lods_var)
        self.all_lods_check.pack(side='left',padx=6)
        self.include_animation_check=ttk.Checkbutton(export_bar,text='Include animation',variable=self.include_animation,state='disabled')
        self.include_animation_check.pack(side='left')
        folder = ttk.Frame(detail);folder.pack(fill='x',pady=(4,0))
        self.export_folder_entry = ttk.Entry(folder,textvariable=self.export_path_var)
        self.export_folder_entry.pack(side='left',fill='x',expand=True)
        self.export_folder_btn = ttk.Button(folder,text='Folder…',command=self._choose_export_folder)
        self.export_folder_btn.pack(side='left',padx=4)
        # Give the preview the remaining space after reserving room for actions.
        # Packing the preview first can clip export controls in compact layouts.
        for widget in detail.winfo_children(): widget.pack_forget()
        for row, widget in enumerate(detail.winfo_children()):
            widget.grid(row=row, column=0, sticky='nsew', pady=(3, 0))
        detail.columnconfigure(0, weight=1); detail.rowconfigure(1, weight=1)

    def _build_appearance(self):
        canvas = tk.Canvas(self.appearance_tab, highlightthickness=0)
        scrollbar = ttk.Scrollbar(self.appearance_tab, orient='vertical', command=canvas.yview)
        scrollbar.pack(side='right', fill='y'); canvas.pack(side='left', fill='both', expand=True)
        canvas.configure(yscrollcommand=scrollbar.set)
        body = ttk.Frame(canvas, padding=16)
        window = canvas.create_window((0,0), window=body, anchor='nw')
        body.bind('<Configure>', lambda event: canvas.configure(scrollregion=canvas.bbox('all')))
        canvas.bind('<Configure>', lambda event: canvas.itemconfigure(window, width=event.width))
        ttk.Label(body, text='Appearance', style='Title.TLabel').grid(row=0, column=0, columnspan=3, sticky='w', pady=(0, 12))
        self.theme_var = tk.StringVar(value=self.appearance['preset'])
        self.layout_var = tk.StringVar(value=self.appearance['layout'])
        self.mascot_var = tk.BooleanVar(value=self.appearance['show_mascot'])
        ttk.Label(body, text='Theme').grid(row=1, column=0, sticky='w', pady=5)
        preset = ttk.Combobox(body, textvariable=self.theme_var, values=tuple(appearance.PRESETS), state='readonly', width=24)
        preset.grid(row=1, column=1, sticky='w'); preset.bind('<<ComboboxSelected>>', self._choose_theme)
        ttk.Label(body, text='Layout').grid(row=2, column=0, sticky='w', pady=5)
        layout = ttk.Combobox(body, textvariable=self.layout_var, values=appearance.LAYOUTS, state='readonly', width=24)
        layout.grid(row=2, column=1, sticky='w'); layout.bind('<<ComboboxSelected>>', self._choose_layout)
        self.color_vars = {}; self.color_swatches = {}
        for row, (key, label) in enumerate([('background','Window background'), ('surface','Tables & inputs'), ('text','Text'), ('muted','Secondary text'), ('accent','Accent'), ('selection','Selected rows & tabs'), ('viewport','3D preview background')], start=4):
            ttk.Label(body, text=label).grid(row=row, column=0, sticky='w', pady=4)
            variable = tk.StringVar(value=self.appearance['colors'][key]); self.color_vars[key] = variable
            ttk.Entry(body, textvariable=variable, width=14).grid(row=row, column=1, sticky='w')
            swatch = tk.Label(body, width=3, background=variable.get(), relief='solid', borderwidth=1)
            swatch.grid(row=row, column=2, sticky='w', padx=(0, 10)); self.color_swatches[key] = swatch
            ttk.Button(body, text='Choose…', command=lambda k=key: self._pick_color(k)).grid(row=row, column=3, sticky='w')
        buttons = ttk.Frame(body); buttons.grid(row=11, column=0, columnspan=4, sticky='w', pady=12)
        ttk.Button(buttons, text='Apply colors', command=self._apply_custom_colors).pack(side='left')
        ttk.Button(buttons, text='Reset appearance', command=self._reset_appearance).pack(side='left', padx=8)
        ttk.Checkbutton(body, text='Show logo', variable=self.mascot_var, command=self._toggle_mascot).grid(row=12, column=0, columnspan=4, sticky='w')
        mascot_buttons = ttk.Frame(body); mascot_buttons.grid(row=13, column=0, columnspan=4, sticky='w', pady=8)
        ttk.Button(mascot_buttons, text='Change logo…', command=self._choose_mascot).pack(side='left')
        ttk.Button(mascot_buttons, text='Reset logo', command=self._restore_mascot).pack(side='left', padx=8)
        self.mascot_portrait = ttk.Label(body)
        self.mascot_portrait.grid(row=1, column=5, rowspan=13, sticky='ne', padx=(40, 0))
        self.appearance_status = ttk.Label(body, text='', style='Muted.TLabel')
        self.appearance_status.grid(row=15, column=0, columnspan=4, sticky='w', pady=8)

    def _apply_layout(self):
        pane = self.workspace; nav, center, detail = self.workspace_panels
        for panel in self.workspace_panels: panel.grid_forget()
        for column in range(3): pane.columnconfigure(column, weight=0, minsize=0, uniform='')
        for row in range(2): pane.rowconfigure(row, weight=0, minsize=0)
        layout = self.appearance['layout']
        self.preview.configure(height=150 if layout == 'Stacked Workspace' else 300)
        self.simple_info.configure(height=4 if layout == 'Stacked Workspace' else 6)
        self.simple_assets.configure(height=3 if layout == 'Stacked Workspace' else 10)
        if layout == 'Classic Columns':
            for i, panel in enumerate(self.workspace_panels): panel.grid(row=0, column=i, sticky='nsew')
            for i, weight in enumerate((2, 4, 5)): pane.columnconfigure(i, weight=weight, uniform='classic')
            pane.rowconfigure(0, weight=1)
        elif layout == 'Preview Focus':
            nav.grid(row=0, column=0, sticky='nsew'); center.grid(row=1, column=0, sticky='nsew')
            detail.grid(row=0, column=1, rowspan=2, sticky='nsew')
            pane.columnconfigure(0, weight=4, uniform='focus'); pane.columnconfigure(1, weight=6, uniform='focus')
            pane.rowconfigure(0, weight=2); pane.rowconfigure(1, weight=3)
        else:
            nav.grid(row=0, column=0, rowspan=2, sticky='nsew'); center.grid(row=0, column=1, sticky='nsew')
            detail.grid(row=1, column=1, sticky='nsew')
            pane.columnconfigure(0, weight=2, uniform='stack'); pane.columnconfigure(1, weight=8, uniform='stack')
            pane.rowconfigure(0, weight=2); pane.rowconfigure(1, weight=4)

    def _apply_appearance(self, save=True):
        self.appearance_status.configure(text='')
        appearance.apply(self, self.appearance); self._apply_layout(); self._load_mascot()
        if save:
            try:
                appearance.save(self.appearance_path, self.appearance)
            except OSError as exc: self.appearance_status.configure(text=f'Could not save settings: {exc}')

    def _choose_theme(self, _event=None):
        self.appearance['preset'] = self.theme_var.get()
        self.appearance['colors'] = dict(appearance.PRESETS[self.theme_var.get()])
        self._sync_color_controls(); self._apply_appearance()

    def _sync_color_controls(self):
        for key, color in self.appearance['colors'].items():
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
            self.appearance_status.configure(text='Enter a hex color, e.g. #ef6549.'); return
        self.appearance.update(preset='Custom', colors=colors); self.theme_var.set('Custom')
        self._sync_color_controls(); self._apply_appearance()

    def _reset_appearance(self):
        self.appearance = appearance.normalize({}); self.theme_var.set(self.appearance['preset'])
        self.layout_var.set(self.appearance['layout']); self.mascot_var.set(True)
        self._sync_color_controls(); self._apply_appearance()

    def _toggle_mascot(self):
        self.appearance['show_mascot'] = self.mascot_var.get(); self._apply_appearance()

    def _load_mascot(self):
        path = Path(self.appearance['mascot_path']) if self.appearance['mascot_path'] else Path(__file__).resolve().parents[1]/'resources'/'asuka.webp'
        try:
            with Image.open(path) as image:
                image = image.convert('RGBA')
                portrait = image.copy(); portrait.thumbnail((220, 315))
                self._mascot_portrait_image = ImageTk.PhotoImage(portrait)
                image.thumbnail((72, 50)); self._mascot_image = ImageTk.PhotoImage(image)
            self.mascot_portrait.configure(image=self._mascot_portrait_image)
            self.mascot_label.configure(image=self._mascot_image if self.appearance['show_mascot'] else '')
            if hasattr(self, '_icon_image'): return
            self._icon_image = self._mascot_image; self.iconphoto(True, self._icon_image)
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

    def _build_advanced(self):
        inner = ttk.Notebook(self.advanced_tab)
        inner.pack(fill="both", expand=True, padx=6, pady=6)
        assets_tab = ttk.Frame(inner)
        strings_tab = ttk.Frame(inner)
        inner.add(assets_tab, text="Assets")
        inner.add(strings_tab, text="Raw Strings")

        top = ttk.Frame(assets_tab, padding=(0, 0, 0, 6))
        top.pack(fill="x")
        ttk.Label(top, text="Search:").pack(side="left")
        entry = ttk.Entry(top, textvariable=self.search_var)
        entry.pack(side="left", fill="x", expand=True, padx=(6, 6))
        entry.bind("<Return>", lambda e: self.search_advanced())
        self.type_filter = ttk.Combobox(top, textvariable=self.type_filter_var, state="readonly", width=14)
        self.type_filter.pack(side="left", padx=(0, 6))
        self.type_filter.bind("<<ComboboxSelected>>", lambda e: self.search_advanced())
        ttk.Button(top, text="Search", command=self.search_advanced).pack(side="left")
        ttk.Button(top, text="Clear", command=self._clear_advanced_search).pack(side="left", padx=(5, 0))
        ttk.Label(top, textvariable=self.advanced_count_var, style="Muted.TLabel").pack(side="right", padx=(8, 0))

        asset_pane = ttk.Panedwindow(assets_tab, orient="vertical")
        asset_pane.pack(fill="both", expand=True)
        table_frame = ttk.Frame(asset_pane)
        detail_frame = ttk.Frame(asset_pane)
        asset_pane.add(table_frame, weight=4)
        asset_pane.add(detail_frame, weight=1)

        cols = ("type", "name", "guid", "ver", "hdr", "pak", "patch", "compression", "starpak")
        self.asset_table = ttk.Treeview(table_frame, columns=cols, show="headings", selectmode="browse")
        widths = {"type": 60, "name":250, "guid": 145, "ver": 45, "hdr": 55, "pak": 240, "patch": 45, "compression": 75, "starpak": 100}
        labels = {"type": "Type", "name":"Decoded name", "guid": "GUID", "ver": "Ver", "hdr": "Header", "pak": "Container", "patch": "Patch", "compression": "Compression", "starpak": "StarPak"}
        for c in cols:
            self.asset_table.heading(c, text=labels[c])
            self.asset_table.column(c, width=widths[c], stretch=c == "pak")
        self.asset_table.pack(fill="both", expand=True)
        scrollbar = ttk.Scrollbar(table_frame,orient='horizontal',command=self.asset_table.xview)
        scrollbar.pack(fill='x');self.asset_table.configure(xscrollcommand=scrollbar.set)
        self.asset_table.bind("<<TreeviewSelect>>", self._advanced_asset_selected)

        detail_header = ttk.Frame(detail_frame)
        detail_header.pack(fill="x")
        ttk.Label(detail_header, text="Selected asset", style="Title.TLabel").pack(side="left")
        self.advanced_open_btn = ttk.Button(detail_header, text="Open Container Folder", command=lambda: self._open_selected_container("advanced"))
        self.advanced_open_btn.pack(side="right")
        self.advanced_open_btn.state(["disabled"])
        self.advanced_preview_btn = ttk.Button(detail_header,text='Preview model',command=self._preview_advanced,state='disabled')
        self.advanced_preview_btn.pack(side='right',padx=4)
        self.asset_detail = tk.Text(detail_frame, height=8, font=("Consolas", 9), wrap="none", state="disabled")
        self.asset_detail.pack(fill="both", expand=True, pady=(6, 0))

        string_top = ttk.Frame(strings_tab, padding=(0, 0, 0, 6))
        string_top.pack(fill="x")
        ttk.Label(string_top, text="Search strings:").pack(side="left")
        string_entry = ttk.Entry(string_top, textvariable=self.string_search_var)
        string_entry.pack(side="left", fill="x", expand=True, padx=6)
        string_entry.bind("<Return>", lambda e: self.search_strings())
        ttk.Button(string_top, text="Search", command=self.search_strings).pack(side="left")
        ttk.Button(string_top, text="Clear", command=self._clear_string_search).pack(side="left", padx=(5, 0))

        string_cols = ("value", "container", "compression")
        self.string_table = ttk.Treeview(strings_tab, columns=string_cols, show="headings")
        self.string_table.heading("value", text="Value")
        self.string_table.heading("container", text="Container")
        self.string_table.heading("compression", text="Compression")
        self.string_table.column("value", width=700, stretch=True)
        self.string_table.column("container", width=360, stretch=True)
        self.string_table.column("compression", width=100, stretch=False)
        self.string_table.pack(fill="both", expand=True)

    def _build_diag(self):
        pane = ttk.Panedwindow(self.diag_tab, orient="vertical")
        pane.pack(fill="both", expand=True, padx=6, pady=6)
        summary_frame = ttk.Frame(pane)
        log_frame = ttk.Frame(pane)
        pane.add(summary_frame, weight=1)
        pane.add(log_frame, weight=3)

        self.summary_text = tk.Text(summary_frame, height=14, font=("Consolas", 9), wrap="none", state="disabled")
        self.summary_text.pack(fill="both", expand=True)

        buttons = ttk.Frame(log_frame)
        buttons.pack(fill="x")
        ttk.Button(buttons, text="Refresh Summary", command=self.refresh_summary).pack(side="left")
        ttk.Button(buttons, text="Show Failure Details", command=self.show_failures).pack(side="left", padx=5)
        ttk.Button(buttons, text="Save Diagnostic Report", command=self.save_report).pack(side="left")
        self.log_text = tk.Text(log_frame, font=("Consolas", 9), wrap="none")
        self.log_text.pack(fill="both", expand=True, pady=(6, 0))

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
                    label = f'{self._cosmetic["owner_name"]} — {self._cosmetic["name"]}' if self._cosmetic else Path(model.name).stem
                    self._set_simple_info(f'{label}\n{total:,} vertices • {len(model.bones)} bones • {len(model.lods)} LODs\n'+ '\n'.join(warnings+model.warnings))
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
                    else: self.preview.clear(f'Preview unavailable\n\n{error}')
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

    def refresh_simple_library(self):
        self.simple_tree.delete(*self.simple_tree.get_children())
        self.simple_assets.delete(*self.simple_assets.get_children())
        self._simple_sections.clear()
        if self.catalog.index_outdated:
            self.simple_header_var.set("Assets")
            self.preview.clear("No model selected")
            self._set_simple_info('');self.status_var.set('Scan required')
            return
        owners = self.catalog.cosmetic_owners()
        categories = {}
        if owners:
            iid = self.simple_tree.insert('', 'end',text=f'All cosmetics ({sum(o["count"] for o in owners):,})')
            self._simple_sections[iid] = ('owner',None)
        for owner in owners:
            category = owner['category']
            if category not in categories:
                categories[category] = self.simple_tree.insert('', 'end',text=category,open=True)
            iid = self.simple_tree.insert(categories[category],'end',text=f'{owner["owner_name"]} ({owner["count"]:,})')
            self._simple_sections[iid] = ('owner',owner['owner_guid'])
        sections = [s for s in self.catalog.simple_sections() if 'mdl_' in s['types']]
        if not sections and not owners:
            self.simple_header_var.set("Assets")
            self.preview.clear("No model selected")
            self._set_simple_info('')
            return

        for section in sections:
            iid = self.simple_tree.insert("", "end", text=f"{section['label']} ({section['count']:,})")
            self._simple_sections[iid] = ('raw',tuple(section["types"]))

        first = next(iter(self._simple_sections),None)
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
        label = self.simple_tree.item(iid, "text")
        self.simple_header_var.set(label)
        text = self.simple_search_var.get().strip()
        if spec[0] == 'owner':
            rows = self.catalog.search_cosmetics(text,owner_guid=spec[1])
        else:
            rows = self.catalog.search_assets(text,asset_type='mdl_',limit=2500)
        self.simple_assets.delete(*self.simple_assets.get_children())
        for r in rows:
            if spec[0] == 'owner':
                models = json.loads(r['details']).get('models',[])
                self.simple_assets.insert('', 'end',iid=f'cosmetic:{r["id"]}',values=(r['name'],r['quality'],'Model found' if any(m.get('pak_name') for m in models) else 'Model unresolved'))
            else:
                self.simple_assets.insert('', 'end',iid=f'simple:{r["id"]}',values=(r['name'] or f'Unnamed {r["guid"]}',r['type'],r['decode_status']))
        self.preview.clear("Select a model")
        self._set_simple_info(f"{len(rows):,} assets")
        self.open_source_btn.state(["disabled"])
        self._model = None
        self._animation=None;self._playing=False;self._animation_serial+=1
        self.animation_name.set('');self.play_btn.configure(text='Play')
        for widget in (self.play_btn,self.frame_slider,self.animation_export_btn,self.include_animation_check): widget.state(['disabled'])
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
            self._model_choices = json.loads(row['details']).get('models',[])
            self.model_choice.configure(values=[self._model_label(x) for x in self._model_choices],state='readonly' if self._model_choices else 'disabled')
            if self._model_choices:
                self.model_choice_var.set(self._model_label(self._model_choices[0]))
                self._load_cosmetic_model()
            else:
                self.preview.clear('Model relationship unresolved')
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
        self.simple_info.configure(state="normal",height=min(6,max(1,len(text.rstrip().splitlines()))))
        self.simple_info.delete("1.0", "end")
        self.simple_info.insert("1.0", text)
        self.simple_info.configure(state="disabled")

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
        window = tk.Toplevel(self); window.title('Animations')
        window.configure(background=self.appearance['colors']['background'])
        window.geometry('1180x700');window.minsize(950,550);window.transient(self);window.grab_set()
        query = tk.StringVar(); entry=ttk.Entry(window,textvariable=query);entry.pack(fill='x',padx=8,pady=4)
        body=ttk.Panedwindow(window,orient='horizontal');body.pack(fill='both',expand=True,padx=8,pady=4)
        frame=ttk.Frame(body);body.add(frame,weight=3)
        table=ttk.Treeview(frame,columns=('name','guid','link','source'),show='headings')
        for key,title,width in [('name','Sequence',420),('guid','GUID',150),('link','Link',130),('source','RPak',280)]:
            table.heading(key,text=title);table.column(key,width=width)
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
        right=ttk.Frame(body);body.add(right,weight=2)
        viewport=ModelPreview(right);viewport.pack(fill='both',expand=True)
        viewport.set_palette(self.appearance['colors']['viewport'],'','')
        viewport.set_model(self._model,int(self.lod_var.get().split()[-1]));viewport.set_textures(self._preview_pixels)
        info=tk.StringVar();ttk.Label(right,textvariable=info,wraplength=430).pack(fill='x',pady=4)
        controls=ttk.Frame(right);controls.pack(fill='x',pady=4)
        blend=tk.IntVar(value=0)
        ttk.Label(controls,text='Blend').pack(side='left')
        self._blend_choice=ttk.Spinbox(controls,from_=0,to=0,textvariable=blend,width=5)
        self._blend_choice.pack(side='left',padx=4)
        play=ttk.Button(controls,text='Play',state='disabled');play.pack(side='left',padx=4)
        position=tk.DoubleVar(value=0)
        timeline=ttk.Scale(right,variable=position,state='disabled');timeline.pack(fill='x',pady=4)
        footer=ttk.Frame(window);footer.pack(fill='x',padx=8,pady=8)
        details=tk.BooleanVar(value=False)
        ttk.Checkbutton(footer,text='Details',variable=details,
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
        ttk.Button(controls,text='Retry',command=load).pack(side='left')
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
