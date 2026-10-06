"""Library page: the category sidebar, the item list, the 3D preview with model/LOD pickers, animation playback
and export. Mixed into ApexAssetStudioApp."""
from __future__ import annotations

import json
import threading
import time
import tkinter as tk
from collections import OrderedDict
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
from tkinter import font as tkfont
from PIL import Image

from ..repository import AssetRepository
from ..rpak.animation import decode_animation
from ..rpak.material import safe_name, decode_material
from ..rpak.model import decode_model
from ..rpak.oodle_stream import ScanCancelled
from ..rpak.texture import extract_texture
from ..export.package import export_package, export_animation
from . import appearance, widgets
from .animations import show_animation_picker
from .common import asset_lines, open_folder, sort_tree
from .inspector import show_material_inspector
from .preview import ModelPreview


class LibraryPage:
    def _init_library_state(self):
        self.simple_header_var = tk.StringVar(value="Library")
        self.list_count_var = tk.StringVar(value="")
        self.inspector_title = tk.StringVar(value="Nothing selected")
        self.inspector_meta = tk.StringVar(value="")
        self.frame_text = tk.StringVar(value="")
        self.animation_display = tk.StringVar(value="")
        self.simple_search_var = tk.StringVar()
        self.model_choice_var = tk.StringVar()
        self.lod_var = tk.StringVar()
        self.export_path_var = tk.StringVar(value=self.session.get('export_path') or str(self._default_export_folder()))
        self.all_lods_var = tk.BooleanVar(value=True)
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
        self.export_kind = tk.StringVar(value='model')
        self.animation_name.trace_add('write', self._update_animation_display)
        self.frame_var.trace_add('write', self._update_frame_text)
        self._animation_picker = None
        self._preview_pixels = {}; self._preview_cache = OrderedDict()
        self._simple_sections: dict[str, tuple[str, ...]] = {}

    def _viewport_hint(self, inside):
        hint = 'Drag to rotate  ·  Shift-drag or right-drag to pan  ·  Scroll to zoom  ·  R resets the view'
        if inside:
            self._status_before_hint = self.status_var.get(); self.status_var.set(hint)
        elif self.status_var.get() == hint:
            self.status_var.set(getattr(self, '_status_before_hint', ''))

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
        self.inspector_title.set(str(title))
        self.inspector_meta.set(str(subtitle))

    SORTS = {'Name A–Z': ('name', False), 'Name Z–A': ('name', True), 'Rarity (best first)': ('quality', True),
             'Season (newest first)': ('season', True), 'Season (oldest first)': ('season', False), 'Source': ('source', False)}

    def _apply_sort(self, remember=True):
        column, reverse = self.SORTS.get(self.sort_var.get(), ('name', False))
        if self.session.get('sort_column') and not remember:  # a heading click from earlier wins until the dropdown is used
            column, reverse = self.session['sort_column'], self.session.get('sort_reverse', False)
        if remember: self.session['sort'] = self.sort_var.get(); self.session.pop('sort_column', None)
        if column in self.simple_assets['columns']: sort_tree(self.simple_assets, column, reverse)

    def _remember_column_sort(self, column, reverse):
        self.session['sort_column'] = column; self.session['sort_reverse'] = reverse

    @staticmethod
    def _season_code(label):
        return f"S{label.split()[-1]}" if label.startswith('Season ') else '—'

    def _update_season_choices(self, seasons):
        numbers = sorted((int(s[1:]) for s in seasons if s.startswith('S')), reverse=True)
        values = ['All seasons'] + [f'Season {n}' for n in numbers] + (['No season'] if '—' in seasons else [])
        self.season_filter.configure(values=values)
        if self.season_filter_var.get() not in values: self.season_filter_var.set('All seasons')

    def _update_frame_text(self, *_):
        clip = self._animation
        if clip is None: self.frame_text.set('')
        else: self.frame_text.set(f'{int(self.frame_var.get())+1:,} / {clip["frames"]:,}')

    def _update_animation_display(self, *_):
        name = self.animation_name.get()
        self.animation_display.set(name or 'Bind pose. Browse animations to pick a clip.')
        self._update_frame_text()
        self._update_badge()

    @staticmethod
    def _clip_title(clip):
        return Path(str(clip.get('name') or 'Animation')).stem.replace('_', ' ').strip().title()

    def _update_badge(self):
        """Name, length and play state of the current animation, shown in the corner of the 3D view."""
        if not hasattr(self, 'preview'): return
        clip = self._animation
        text = ''
        if clip is not None:
            seconds = clip['frames'] / max(clip['fps'], 1)
            text = f"{'Playing' if self._playing else 'Paused'}  ·  {self._clip_title(clip)}  ·  {seconds:.1f} s"
        self.preview.set_badge(text)
        if clip is None and self.export_kind.get() == 'animation': self.export_kind.set('model')
        self._refresh_export_controls()

    def _refresh_export_controls(self):
        """Export button label and which options apply, for 'Model' or 'Animation only'."""
        if not hasattr(self, 'export_btn'): return
        animation_only = self.export_kind.get() == 'animation'
        batch = 0 if animation_only else self._batch_size()
        self.export_btn.text = 'Export animation' if animation_only else f'Export {batch:,} skins' if batch else 'Export model'
        idle = not self._busy and not self._scanning and not getattr(self, '_loading', False)
        model_ready = bool(self._model and self._model.material_family_resolved)
        enabled = idle and (bool(batch) or self._model is not None and (self._animation is not None if animation_only else model_ready))
        self.export_btn.state(['!disabled'] if enabled else ['disabled'])
        for widget in self._model_export_options:
            widget.state(['disabled'] if animation_only or not idle else ['!disabled'])
        self.include_animation_check.state(['!disabled'] if idle and not animation_only and self._animation is not None else ['disabled'])
        self.animation_export_btn.state(['!disabled'] if self._animation is not None and idle else ['disabled'])

    # Columns hidden first when the list is too narrow to show them all (Name and Rarity always stay).
    OPTIONAL_COLUMNS = ('state', 'source', 'season')

    def _fit_list_columns(self, event=None):
        """Show as many columns as fit the list's width, so none are cut off. Hidden ones still sort."""
        tree = self.simple_assets
        available = tree.winfo_width()
        if available <= 1: return
        shown = list(tree['columns'])
        def needed(columns):
            return (int(tree.column('#0', 'width')) if 'tree' in str(tree.cget('show')) else 0) + \
                int(tree.column('name', 'minwidth')) + 40 + sum(int(tree.column(c, 'width')) for c in columns if c != 'name')
        for column in self.OPTIONAL_COLUMNS:
            if needed(shown) <= available: break
            shown.remove(column)
        if tuple(shown) != tuple(tree.cget('displaycolumns')) and not (tree.cget('displaycolumns') in (('#all',), '#all') and shown == list(tree['columns'])):
            tree.configure(displaycolumns=shown)

    def _build_library(self):
        f = appearance.fonts(self)
        pane = ttk.Frame(self.library_tab, style='Hairline.TFrame')
        pane.pack(fill='both', expand=True)
        self.workspace = pane
        nav = ttk.Frame(pane, padding=(8, 16, 4, 10))
        center = ttk.Frame(pane, style='Panel.TFrame', padding=(18, 16, 10, 10))
        detail = ttk.Frame(pane, style='Panel.TFrame', padding=(18, 16, 18, 16))
        self.workspace_panels = nav, center, detail

        # Sidebar: categories and owners with right-aligned counts
        self._section(nav, 'Library', on='background').pack(fill='x', padx=(10, 6), pady=(0, 10))
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
        entry = ttk.Entry(search, textvariable=self.simple_search_var); self.simple_search_entry = entry
        entry.pack(fill='x')
        entry.bind('<Return>', lambda _e: self._search_simple())
        entry.bind('<Escape>', lambda _e: self.simple_search_var.set(''))
        self._placeholder(entry, self.simple_search_var, 'Search this list')
        self.simple_search_var.trace_add('write', lambda *_: self._debounce_search())
        filters = widgets.Flow(center, gap=(12, 6)); filters.pack(fill='x', pady=(0, 8), padx=(0, 8))
        self.rarity_filter_var = tk.StringVar(value='All rarities')
        self.hide_unavailable_var = tk.BooleanVar(value=self.session.get('hide_unavailable', False))
        self.search_all_var = tk.BooleanVar(value=False)
        rarity = ttk.Combobox(filters, textvariable=self.rarity_filter_var, state='readonly', width=13,
                              values=('All rarities', 'Common', 'Rare', 'Epic', 'Legendary', 'Mythic'))
        filters.add(rarity); rarity.bind('<<ComboboxSelected>>', lambda _e: self._search_simple())
        self.season_filter_var = tk.StringVar(value='All seasons')
        self.season_filter = ttk.Combobox(filters, textvariable=self.season_filter_var, state='readonly', width=12, values=('All seasons',))
        filters.add(widgets.tip(self.season_filter, 'Show only skins released in one season (read from the game files; base and store '
                                                    'skins have no season).'))
        self.season_filter.bind('<<ComboboxSelected>>', lambda _e: self._search_simple())
        self.sort_var = tk.StringVar(value=self.session.get('sort', 'Name A–Z'))
        sort = ttk.Combobox(filters, textvariable=self.sort_var, state='readonly', width=18, values=tuple(self.SORTS))
        filters.add(widgets.tip(sort, 'Order of the list. You can also click a column heading (click again to reverse).'))
        sort.bind('<<ComboboxSelected>>', lambda _e: self._apply_sort())
        filters.add(widgets.tip(ttk.Checkbutton(filters, text='Hide unavailable', variable=self.hide_unavailable_var,
                    style='Panel.TCheckbutton', command=self._search_simple),
                    "Hide skins whose model isn't in your game files, so they can't be previewed or exported."))
        filters.add(widgets.tip(ttk.Checkbutton(filters, text='Search all skins', variable=self.search_all_var,
                    style='Panel.TCheckbutton', command=self._search_simple),
                    'Search every Legend and weapon at once instead of only the one picked on the left.'))
        self.thumbs_var = tk.BooleanVar(value=self.session.get('thumbnails', True))
        filters.add(widgets.tip(ttk.Checkbutton(filters, text='Pictures', variable=self.thumbs_var, style='Panel.TCheckbutton',
                    command=self._apply_thumbnail_mode),
                    'Show a picture next to each skin: your own skin images (Settings › Skin images) or a render the app '
                    'saves the first time you open a skin.'))
        assets_body = ttk.Frame(center, style='Panel.TFrame')
        assets_body.pack(fill='both', expand=True)
        cols = ('name', 'quality', 'season', 'source', 'state')
        # extended: Ctrl/Shift-click several skins to export them together; the clicked one is previewed
        self.simple_assets = ttk.Treeview(assets_body, columns=cols, show='headings', selectmode='extended')
        for column, title, width, stretch in (('name', 'Name', 140, True), ('quality', 'Rarity', 86, False), ('season', 'Season', 64, False),
                                              ('source', 'Source', 116, False), ('state', 'Model', 96, False)):
            self.simple_assets.heading(column, text=title, anchor='w')
            # Wide enough for the heading plus the sort arrow at any text size.
            needed = tkfont.Font(font=appearance.fonts(self)['strong']).measure(f'{title} ▼') + 24
            self.simple_assets.column(column, width=max(width, needed), minwidth=60, stretch=stretch, anchor='w')
        self.simple_assets.pack(side='left', fill='both', expand=True)
        assets_scroll = ttk.Scrollbar(assets_body, orient='vertical', command=self.simple_assets.yview)
        assets_scroll.pack(side='right', fill='y', padx=(4, 0))
        self.simple_assets.configure(yscrollcommand=lambda *a: (assets_scroll.set(*a), self._schedule_thumbnails()))
        self.simple_assets.bind('<Configure>', self._schedule_thumbnails, add='+')
        self.simple_assets.bind('<Configure>', self._fit_list_columns, add='+')
        self.simple_assets.on_sort = self._remember_column_sort
        self.simple_assets.bind('<<TreeviewSelect>>', self._swap_selection_tags)
        self.simple_assets.bind('<<TreeviewSelect>>', self._simple_asset_selected, add='+')
        self.simple_assets.bind('<<TreeviewSelect>>', lambda _e: self._refresh_export_controls(), add='+')
        self._held_tags = {}

        # Inspector
        head = ttk.Frame(detail, style='Panel.TFrame')
        titles = ttk.Frame(head, style='Panel.TFrame')
        titles.pack(side='left', fill='x', expand=True)
        ttk.Label(titles, textvariable=self.inspector_title, style='Title.Panel.TLabel', width=1).pack(fill='x')
        ttk.Label(titles, textvariable=self.inspector_meta, style='Data.Panel.TLabel', width=1).pack(fill='x', pady=(3, 0))
        widgets.tip(ttk.Button(head, text='Reset view', style='Ghost.Panel.TButton', command=lambda: self.preview.reset_view()),
                    'Put the camera back to the starting angle and zoom (R).').pack(side='right', anchor='n')
        widgets.tip(ttk.Button(head, text='Materials…', style='Ghost.Panel.TButton', command=lambda: show_material_inspector(self)),
                    'Every material and texture this model uses, what each texture is for, and anything that '
                    "couldn't be read. Picking a material highlights it in the preview.").pack(side='right', anchor='n')

        viewport = ttk.Frame(detail, style='Hairline.TFrame', padding=1)
        self.preview = ModelPreview(viewport, height=300)
        self.preview.pack(fill='both', expand=True)
        self.preview.bind('<Enter>', lambda _e: self._viewport_hint(True), add='+')
        self.preview.bind('<Leave>', lambda _e: self._viewport_hint(False), add='+')

        model_bar = ttk.Frame(detail, style='Panel.TFrame')
        ttk.Label(model_bar, text='Model', style='Section.Panel.TLabel').pack(side='left', padx=(0, 8))
        self.model_choice = ttk.Combobox(model_bar, textvariable=self.model_choice_var, state='disabled', width=20)
        self.model_choice.pack(side='left', fill='x', expand=True)
        self.model_choice.bind('<<ComboboxSelected>>', lambda _e: self._load_cosmetic_model())
        widgets.tip(self.model_choice, 'Which model of this skin to show: full body, first-person arms, and so on.')
        ttk.Label(model_bar, text='LOD', style='Section.Panel.TLabel').pack(side='left', padx=(16, 8))
        self.lod_choice = ttk.Combobox(model_bar, textvariable=self.lod_var, state='disabled', width=7)
        self.lod_choice.pack(side='left')
        widgets.tip(self.lod_choice, 'Level of detail. LOD 0 is the most detailed; higher numbers are the simpler meshes '
                                     'the game shows at a distance.')
        self.lod_choice.bind('<<ComboboxSelected>>', lambda _e: self._render_model())

        self.simple_info = tk.Text(detail, height=3, wrap='word', font=f['small'], state='disabled', cursor='arrow')
        self.simple_info.flush = True; self.simple_info.font_key = 'small'

        anim = ttk.Frame(detail, style='Panel.TFrame')
        self._section(anim, 'Animation').pack(fill='x')
        actions = widgets.Flow(anim, gap=(4, 2)); actions.pack(fill='x', pady=(2, 0))
        self.animations_btn = actions.add(widgets.tip(ttk.Button(actions, text='Browse animations…', style='Ghost.Panel.TButton',
                                          command=self._show_declared_animations, state='disabled'),
                                          'Pick one of the animations made for this model and play it here.'), gap=0)
        ttk.Label(anim, textvariable=self.animation_display, style='Panel.TLabel', width=1).pack(fill='x', pady=(2, 6))
        transport = ttk.Frame(anim, style='Panel.TFrame')
        transport.pack(fill='x')
        self.play_btn = ttk.Button(transport, text='Play', width=6, command=self._toggle_animation, state='disabled')
        self.play_btn.pack(side='left')
        ttk.Label(transport, textvariable=self.frame_text, style='Small.Panel.TLabel', width=12, anchor='e').pack(side='right')
        self.frame_slider = ttk.Scale(transport, variable=self.frame_var, command=self._seek_animation, state='disabled',
                                      style='Panel.Horizontal.TScale')
        self.frame_slider.pack(side='left', fill='x', expand=True, padx=(12, 8))

        export = ttk.Frame(detail, style='Panel.TFrame')
        self._section(export, 'Export').pack(fill='x')
        links = widgets.Flow(export, gap=(4, 2)); links.pack(fill='x', pady=(2, 0))
        self.open_source_btn = links.add(widgets.tip(ttk.Button(links, text='Show source file', style='Ghost.Panel.TButton',
                                         command=lambda: self._open_selected_container('simple')),
                                         'Open the game folder that holds the package this model comes from.'), gap=0)
        self.open_export_btn = links.add(widgets.tip(ttk.Button(links, text='Open last export', style='Ghost.Panel.TButton',
                                         command=self._open_last_export), 'Open the folder of the most recent export.'))
        links.add(widgets.tip(ttk.Button(links, text='Export whole list…', style='Ghost.Panel.TButton', command=self._export_list),
                              'Export every skin in the list on the left (after search and filters), one after another.'))
        self.batch_cancel_btn = widgets.tip(ttk.Button(links, text='Cancel batch', style='Ghost.Panel.TButton', command=self._cancel_batch),
                                            'Stop after the skin being exported now.')
        self._export_links = links
        self.open_source_btn.state(['disabled']); self.open_export_btn.state(['disabled'])
        folder = ttk.Frame(export, style='Panel.TFrame')
        folder.pack(fill='x', pady=(4, 10))
        self.export_folder_entry = ttk.Entry(folder, textvariable=self.export_path_var)
        self.export_folder_entry.pack(side='left', fill='x', expand=True)
        self.export_folder_btn = ttk.Button(folder, text='Browse…', command=self._choose_export_folder)
        self.export_folder_btn.pack(side='left', padx=(6, 0))
        presets = ttk.Frame(export, style='Panel.TFrame'); presets.pack(fill='x', pady=(0, 8))
        ttk.Label(presets, text='Preset', style='Muted.Panel.TLabel').pack(side='left', padx=(0, 10))
        self.preset_var = tk.StringVar(value='Custom')
        self.delete_preset_btn = ttk.Button(presets, text='Delete', style='Ghost.Panel.TButton', command=self._delete_export_preset)
        self.delete_preset_btn.pack(side='right')
        ttk.Button(presets, text='Save…', style='Ghost.Panel.TButton', command=self._save_export_preset).pack(side='right', padx=(6, 0))
        self.preset_choice = ttk.Combobox(presets, textvariable=self.preset_var, state='readonly', width=12)
        self.preset_choice.pack(side='left', fill='x', expand=True)
        self.preset_choice.bind('<<ComboboxSelected>>', lambda _e: self._apply_export_preset())
        widgets.tip(self.preset_choice, 'Saved combinations of formats and options. Changing any option switches to "Custom".')
        kinds = widgets.Flow(export, gap=(16, 6)); kinds.pack(fill='x', pady=(0, 6))
        kinds.add(ttk.Label(kinds, text='Export', style='Muted.Panel.TLabel'))
        kinds.add(widgets.tip(ttk.Radiobutton(kinds, text='Model', value='model', variable=self.export_kind, style='Panel.TRadiobutton',
                  command=self._refresh_export_controls), 'The skin with its skeleton, materials and textures.'), gap=12)
        self.animation_export_btn = kinds.add(widgets.tip(ttk.Radiobutton(kinds, text='Animation only', value='animation',
                                              variable=self.export_kind, style='Panel.TRadiobutton', state='disabled',
                                              command=self._refresh_export_controls),
                                              'Just the animation in the preview: a GLB with the skeleton and motion, plus an .aas.json '
                                              'for the Blender add-on. Pick an animation first.'))
        options = widgets.Flow(export, gap=(16, 6)); options.pack(fill='x', pady=(0, 10))
        self.all_lods_check = options.add(widgets.tip(ttk.Checkbutton(options, text='All detail levels', variable=self.all_lods_var,
                                          style='Panel.TCheckbutton'), 'Also export the lower-detail LOD meshes, not just LOD 0.'))
        self.include_animation_check = options.add(widgets.tip(ttk.Checkbutton(options, text='Include animation', variable=self.include_animation,
                                                   state='disabled', style='Panel.TCheckbutton'),
                                                   'Add the animation playing in the preview to the export.'))
        hints = {'.glb': 'One binary file with everything inside. Best for Blender.',
                 '.gltf': 'Text glTF with separate files. Same content as GLB.',
                 '.cast': 'CAST format for other tools. Uses inches; the Blender add-on needs GLB or glTF too.'}
        formats = ttk.Frame(options, style='Panel.TFrame')  # the format checkboxes wrap as one group
        options.add(formats)
        ttk.Label(formats, text='Formats', style='Muted.Panel.TLabel').pack(side='left', padx=(0, 8))
        self.format_vars = {}; self._model_export_options = [self.all_lods_check]
        for ext, label in (('.glb', 'GLB'), ('.gltf', 'glTF'), ('.cast', 'CAST')):
            var = tk.BooleanVar(value=ext in self.session.get('formats', ['.glb', '.cast']))
            var.trace_add('write', lambda *_: self._remember_formats())
            self.format_vars[ext] = var
            check = widgets.tip(ttk.Checkbutton(formats, text=label, variable=var, style='Panel.TCheckbutton'), hints[ext])
            check.pack(side='left', padx=(0, 12)); self._model_export_options.append(check)
        for variable in list(self.format_vars.values()) + [self.all_lods_var, self.include_animation]:
            variable.trace_add('write', lambda *_: self._detect_export_preset())
        self._refresh_export_presets(); self._detect_export_preset()
        self.export_btn = widgets.GlossButton(export, 'Export model', command=self._export, height=36, width=240)
        self.export_btn.state(['disabled'])
        self.export_btn.pack(fill='x')

        rows = ((head, (0, 12)), (viewport, (0, 10)), (model_bar, (0, 6)), (self.simple_info, (2, 4)),
                (ttk.Separator(detail), (8, 12)), (anim, (0, 0)), (ttk.Separator(detail), (14, 12)), (export, (0, 0)))
        for row, (widget, pady) in enumerate(rows):
            widget.grid(row=row, column=0, sticky='nsew', pady=pady)
        detail.columnconfigure(0, weight=1); detail.rowconfigure(1, weight=1)
        self._apply_thumbnail_mode()
        self.simple_info.grid_remove()

    def refresh_simple_library(self):
        self.simple_tree.delete(*self.simple_tree.get_children())
        self.simple_assets.delete(*self.simple_assets.get_children())
        self._simple_sections.clear()
        self.list_count_var.set('')
        if self.catalog.index_outdated:
            self.simple_header_var.set('Library')
            self.preview.clear('No library yet\n\nPress “Scan library” to index your Apex install.')
            self._set_inspector('Nothing selected'); self._set_simple_info('')
            self.status_var.set('Press Scan library to build your library. The first scan takes a while; you can stop and resume it.')
            return
        owners = self.catalog.cosmetic_owners()
        categories = {}
        if owners:
            iid = self.simple_tree.insert('', 'end', text='All cosmetics', values=(f'{sum(o["count"] for o in owners):,}',))
            self._simple_sections[iid] = ('owner', None)
        for owner in owners:
            category = owner['category']
            if category not in categories:
                categories[category] = self.simple_tree.insert('', 'end', text=str(category), open=True, tags=('category',))
            iid = self.simple_tree.insert(categories[category], 'end', text=owner['owner_name'], values=(f'{owner["count"]:,}',))
            self._simple_sections[iid] = ('owner', owner['owner_guid'])
        sections = [s for s in self.catalog.simple_sections() if 'mdl_' in s['types']]
        if not sections and not owners:
            self.simple_header_var.set('Library')
            self.preview.clear('No models in the index')
            self._set_inspector('Nothing selected'); self._set_simple_info('')
            return
        if sections:
            group = self.simple_tree.insert('', 'end', text='Raw assets', open=True, tags=('category',))
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
        if getattr(self, '_load_stop', None): self._load_stop.set()
        if getattr(self, '_loading', False): self._set_loading(False)
        label = self.simple_tree.item(iid, 'text')
        text = self.simple_search_var.get().strip()
        everywhere = bool(text) and self.search_all_var.get() and spec[0] == 'owner'
        if everywhere: label = f'Results for “{text}”'
        self.simple_header_var.set(label)
        rarity = self.rarity_filter_var.get().lower(); hide = self.hide_unavailable_var.get()
        season_filter = self.season_filter_var.get(); seasons = set()
        self.session['hide_unavailable'] = hide
        if spec[0] == 'owner':
            rows = self.catalog.search_cosmetics(text, owner_guid=None if everywhere else spec[1])
        else:
            rows = self.catalog.search_assets(text, asset_type='mdl_', limit=2500)
        self.simple_assets.delete(*self.simple_assets.get_children()); self._held_tags = {}
        self._clear_thumbnails(); self._previewed_iid = None
        shown = 0
        for r in rows:
            if spec[0] == 'owner':
                details = json.loads(r['details'])
                found = any(m.get('pak_name') for m in details.get('models', []))
                season = f"S{details['season']}" if details.get('season') else '—'
                seasons.add(season)
                if (rarity != 'all rarities' and str(r['quality']).lower() != rarity) or (hide and not found): continue
                if season_filter != 'All seasons' and season != self._season_code(season_filter): continue
                shown += 1
                self.simple_assets.insert('', 'end', iid=f'cosmetic:{r["id"]}', tags=(str(r['quality']).lower(),) if found else ('muted',),
                                          values=(r['name'], str(r['quality']).title(), season, details.get('obtained', ''),
                                                  'Ready' if found else 'Not available'))
                self._remember_thumb_row(f'cosmetic:{r["id"]}', r)
            else:
                self.simple_assets.insert('', 'end', iid=f'simple:{r["id"]}',
                                          values=(r['name'] or f'Unnamed {r["guid"]}', r['type'], '', '', r['decode_status']))
        self._update_season_choices(seasons)
        self._apply_sort(remember=False)
        self._schedule_thumbnails()
        count = shown if spec[0] == 'owner' else len(rows)
        self.list_count_var.set(f'{count:,} item' + ('' if count == 1 else 's'))
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
        focus = self.simple_assets.focus()
        item = focus if focus in sel else sel[-1]
        if item == getattr(self, '_previewed_iid', None) and len(sel) > 1: return  # extending a multi-selection
        self._previewed_iid = item; sel = (item,)
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
        self._show_asset_metadata(row)
        if row['type'] == 'mdl_':
            self._start_model_load(row['guid'],row['path'],None)

    def _show_asset_metadata(self, row):
        self._set_inspector(row['name'] or f'Unnamed {row["guid"]}', f'{row["type"]}  ·  {row["filename"]}')
        self.preview.clear('Loading model…' if row['type'] == 'mdl_' else f"No 3D preview for asset type {row['type']}")
        self._set_simple_info('\n'.join(asset_lines(row)))
        self.open_source_btn.state(['!disabled'])

    def _open_selected_container(self, source: str):
        if source == 'simple' and self._model:
            open_folder(Path(self._model.source).parent); return
        tree = self.simple_assets if source == 'simple' else self.asset_table
        sel = tree.selection()
        if not sel: return
        row = self.catalog.get_asset(int(sel[0].split(':', 1)[1]))
        if row is not None: open_folder(Path(row['path']).parent)

    def _set_simple_info(self, text: str):
        text = text.strip()
        self.simple_info.configure(state='normal', height=min(5, max(1, len(text.splitlines()))))
        self.simple_info.delete('1.0', 'end')
        self.simple_info.insert('1.0', text)
        self.simple_info.configure(state='disabled')
        if text: self.simple_info.grid()
        else: self.simple_info.grid_remove()

    def _search_simple(self):
        selected = self.simple_tree.selection()
        if selected:
            self._load_simple_section(selected[0])

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

    def _start_model_load(self,guid,preferred=None,family=None,full=False,keep_view=False):
        """Load a model in the background. Picking another item cancels this load; the list stays usable.
        Only the most detailed LOD is decoded for preview unless `full` (other LODs load when selected)."""
        if self._busy or self._scanning: return
        if getattr(self, '_load_stop', None): self._load_stop.set()
        stop = self._load_stop = threading.Event()
        self._model_source = (guid, preferred, family)
        if not keep_view:
            self._model = None
            self._playing=False; self._animation=None; self._animation_serial+=1
            self._preview_pixels={}
            self.animation_name.set(''); self.play_btn.configure(text='Play')
            self.preview.clear('Loading model…')
        self._set_loading(True)
        serial = self._selection_serial
        root = self.game_path.get()
        self.status_var.set('Loading all detail levels…' if full else 'Loading model…')
        def worker():
            try:
                with AssetRepository(self.catalog,root) as repo:
                    archive,asset = repo.asset(guid,preferred)
                    model = decode_model(archive,asset,family,stop=stop,allow_unresolved_family=True,first_lod_only=not full)
                    warnings = sorted(repo.warnings)
                if not stop.is_set(): self.events.put(('model_ready',serial,model,warnings))
            except ScanCancelled:
                pass
            except Exception as exc:
                if not stop.is_set(): self.events.put(('work_error',serial,f'{type(exc).__name__}: {exc}'))
        threading.Thread(target=worker,daemon=True).start()

    def _set_loading(self, loading):
        self._loading = loading
        if loading:
            for widget in (self.export_btn, self.animations_btn, self.play_btn, self.frame_slider,
                           self.animation_export_btn, self.include_animation_check):
                widget.state(['disabled'])
            self.model_choice.configure(state='disabled'); self.lod_choice.configure(state='disabled')
            if not self.busy_bar.winfo_ismapped(): self.busy_bar.pack(side='right', padx=(12, 0)); self.busy_bar.start(12)
        else:
            self.busy_bar.stop(); self.busy_bar.pack_forget()
            self.model_choice.configure(state='readonly' if self._model_choices and self._cosmetic else 'disabled')

    def _render_model(self):
        if not self._model: return
        lod = int(self.lod_var.get().split()[-1])
        if lod not in self._model.lods:  # first-LOD preview: decode the rest now, then show the chosen level
            if self._model.partial and getattr(self, '_model_source', None):
                self._wanted_lod = lod
                self._start_model_load(*self._model_source, full=True, keep_view=True)
            else:
                lod = min(self._model.lods); self.lod_var.set(f'LOD {lod}'); self.preview.set_model(self._model, lod)
            return
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
                self.preview.set_textures(textures);self.after(400,lambda:self._capture_thumbnail(serial));return
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

    def _apply_animation(self,clip):
        self._animation=clip;self.include_animation.set(True)
        self.animation_name.set(f'{clip["name"]} · {clip["frames"]} frames · {clip["fps"]:g} fps')
        self.frame_slider.configure(to=clip['frames']-1);self.frame_var.set(0)
        self.preview.set_pose(clip,0);self._set_busy(False);self._update_badge()

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
        self._update_badge()

    def _tick_animation(self):
        self._play_timer=None
        if not self._playing or self._animation is None: return
        clip=self._animation; frame=int((time.perf_counter()-self._play_start)*clip['fps'])
        if frame>=clip['frames']:
            if clip['loop']: frame%=clip['frames']
            else:
                frame=clip['frames']-1; self._playing=False; self.play_btn.configure(text='Play'); self._update_badge()
        if frame!=int(self.frame_var.get()): self.frame_var.set(frame); self.preview.set_pose(clip,frame)
        if self._playing: self._play_timer=self.after(max(1,int(1000/clip['fps'])),self._tick_animation)

    def _export(self):
        """The Export button: model or animation, depending on the choice in the Export section."""
        if self.export_kind.get() == 'animation': self._export_animation()
        elif self._batch_size(): self._export_batch()
        else: self._export_model()

    def _export_label(self):
        cosmetic = self._cosmetic
        return f'{cosmetic["owner_name"]} - {cosmetic["name"]} - {self.model_choice_var.get()}' if cosmetic else Path(self._model.name).stem

    def _export_animation(self):
        """Animation only: '<skin> - <animation>' folder in the export folder, holding a GLB (skeleton + motion)
        and the .aas.json the Blender add-on imports."""
        if self._animation is None or not self._model or self._busy or self._scanning: return
        self.export_kind.set('animation'); self._refresh_export_controls()
        title = self._clip_title(self._animation)
        folder = self._export_folder_for(self._cosmetic) / safe_name(f'{self._export_label()} - {title}')
        path = folder / (safe_name(title) + '.aas.json')
        if folder.exists() and not messagebox.askyesno('Replace export?', f'"{folder.name}" already exists in the export folder.\n\nReplace it?', parent=self):
            return
        model=self._model; clip=self._animation; serial=self._selection_serial
        self._blender_note = ''
        self._playing=False; self.play_btn.configure(text='Play'); self._set_busy(True); self._set_activity(f'exporting: {title}')
        def worker():
            try:
                folder.mkdir(parents=True,exist_ok=True)
                manifest_path,manifest=export_animation(model,clip,path)
                self.events.put(('export_ready',manifest_path,manifest))
            except Exception as exc: self.events.put(('work_error',serial,f'Export failed: {type(exc).__name__}: {exc}'))
        threading.Thread(target=worker,daemon=True).start()

    def _choose_export_folder(self):
        if self._busy: return
        path = filedialog.askdirectory(title='Choose export folder',initialdir=self.export_path_var.get())
        if path: self.export_path_var.set(path); self._save_session()

    def _export_model(self):
        if not self._model or not self._model.material_family_resolved or self._busy or self._scanning: return
        if self.export_kind.get() != 'model': self.export_kind.set('model'); self._refresh_export_controls()
        model = self._model
        cosmetic = self._cosmetic_for_export(self._cosmetic)
        label = self._export_label()
        root = self.game_path.get(); destination = self._export_folder_for(self._cosmetic)
        existing=Path(destination)/safe_name(label)
        overwrite=existing.exists()
        if overwrite and not messagebox.askyesno('Replace export?', f'"{existing.name}" already exists in the export folder.\n\nReplace it?', parent=self): return
        all_lods = self.all_lods_var.get(); serial = self._selection_serial
        animation=self._animation if self.include_animation.get() else None
        formats = [ext for ext, var in self.format_vars.items() if var.get()]
        if not formats:
            self.status_var.set('Pick at least one export format.'); return
        self._blender_note = '' if {'.glb', '.gltf'} & set(formats) else ' (CAST only: the Blender add-on needs GLB or glTF.)'
        self._playing=False; self.play_btn.configure(text='Play')
        self._set_busy(True); self._set_activity(f'exporting: {label}')
        source = getattr(self, '_model_source', None)
        def worker():
            try:
                export_model = model
                if all_lods and model.partial and source:
                    self.events.put(('work_progress', 'Decoding all detail levels…'))
                    with AssetRepository(self.catalog, root) as repo:
                        archive, asset = repo.asset(source[0], source[1])
                        export_model = decode_model(archive, asset, source[2], allow_unresolved_family=True)
                path,manifest = export_package(export_model,self.catalog,root,destination,label,cosmetic,all_lods,
                    lambda text:self.events.put(('work_progress',text)),overwrite=overwrite,animation=animation,formats=formats)
                self.events.put(('export_ready',path,manifest))
            except Exception as exc:
                self.events.put(('work_error',serial,f'Export failed: {type(exc).__name__}: {exc}'))
        threading.Thread(target=worker,daemon=True).start()

    BUILTIN_PRESETS = {
        'Blender (GLB, all LODs)': dict(formats=['.glb'], all_lods=True, animation=True),
        'Quick look (GLB, LOD 0)': dict(formats=['.glb'], all_lods=False, animation=False),
        'CAST tools (CAST, all LODs)': dict(formats=['.cast'], all_lods=True, animation=True),
        'Everything (GLB + glTF + CAST)': dict(formats=['.glb', '.gltf', '.cast'], all_lods=True, animation=True),
    }

    def _export_presets(self):
        presets = dict(self.BUILTIN_PRESETS); presets.update(self.session.get('export_presets', {}))
        return presets

    def _refresh_export_presets(self):
        self.preset_choice.configure(values=list(self._export_presets()) + ['Custom'])

    def _current_export_options(self):
        return dict(formats=sorted(ext for ext, var in self.format_vars.items() if var.get()),
                    all_lods=bool(self.all_lods_var.get()), animation=bool(self.include_animation.get()))

    def _detect_export_preset(self):
        if getattr(self, '_applying_preset', False) or not hasattr(self, 'preset_var'): return
        current = self._current_export_options()
        match = next((name for name, p in self._export_presets().items()
                      if sorted(p['formats']) == current['formats'] and p['all_lods'] == current['all_lods']
                      and p['animation'] == current['animation']), 'Custom')
        self.preset_var.set(match); self.session['export_preset'] = match
        self.delete_preset_btn.state(['!disabled'] if match in self.session.get('export_presets', {}) else ['disabled'])

    def _apply_export_preset(self):
        preset = self._export_presets().get(self.preset_var.get())
        if not preset: return
        self._applying_preset = True
        try:
            for ext, var in self.format_vars.items(): var.set(ext in preset['formats'])
            self.all_lods_var.set(preset['all_lods']); self.include_animation.set(preset['animation'])
        finally:
            self._applying_preset = False
        self._detect_export_preset()

    def _save_export_preset(self):
        from tkinter import simpledialog
        name = simpledialog.askstring('Save preset', 'Name for these export options:', parent=self)
        if not name or not name.strip(): return
        name = name.strip()
        if name in self.BUILTIN_PRESETS or name == 'Custom':
            self.status_var.set('That name is taken by a built-in preset. Pick another.'); return
        self.session.setdefault('export_presets', {})[name] = self._current_export_options()
        self._save_session(); self._refresh_export_presets(); self._detect_export_preset()
        self.status_var.set(f'Saved export preset "{name}".')

    def _delete_export_preset(self):
        name = self.preset_var.get()
        if name in self.session.get('export_presets', {}):
            del self.session['export_presets'][name]; self._save_session()
            self._refresh_export_presets(); self._detect_export_preset()

    def _remember_formats(self):
        self.session['formats'] = [ext for ext, var in self.format_vars.items() if var.get()]

    def _open_last_export(self):
        folder = getattr(self, '_last_export', None)
        if folder and Path(folder).exists(): open_folder(folder)

    def _show_declared_animations(self):
        show_animation_picker(self)
