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
from .common import asset_lines, open_folder
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

    def _update_frame_text(self, *_):
        clip = self._animation
        if clip is None: self.frame_text.set('')
        else: self.frame_text.set(f'{int(self.frame_var.get())+1:,} / {clip["frames"]:,}')

    def _update_animation_display(self, *_):
        name = self.animation_name.get()
        self.animation_display.set(name or 'Bind pose. Browse animations to pick a clip.')
        self._update_frame_text()

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
        filters = ttk.Frame(center, style='Panel.TFrame'); filters.pack(fill='x', pady=(0, 8), padx=(0, 8))
        self.rarity_filter_var = tk.StringVar(value='All rarities')
        self.hide_unavailable_var = tk.BooleanVar(value=self.session.get('hide_unavailable', False))
        self.search_all_var = tk.BooleanVar(value=False)
        rarity = ttk.Combobox(filters, textvariable=self.rarity_filter_var, state='readonly', width=13,
                              values=('All rarities', 'Common', 'Rare', 'Epic', 'Legendary', 'Mythic'))
        rarity.pack(side='left'); rarity.bind('<<ComboboxSelected>>', lambda _e: self._search_simple())
        ttk.Checkbutton(filters, text='Hide unavailable', variable=self.hide_unavailable_var, style='Panel.TCheckbutton',
                        command=self._search_simple).pack(side='left', padx=(12, 0))
        ttk.Checkbutton(filters, text='Search all skins', variable=self.search_all_var, style='Panel.TCheckbutton',
                        command=self._search_simple).pack(side='left', padx=(12, 0))
        assets_body = ttk.Frame(center, style='Panel.TFrame')
        assets_body.pack(fill='both', expand=True)
        cols = ('name', 'quality', 'state')
        self.simple_assets = ttk.Treeview(assets_body, columns=cols, show='headings', selectmode='browse')
        for column, title, width, stretch in (('name', 'Name', 140, True), ('quality', 'Rarity', 96, False), ('state', 'Model', 104, False)):
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
        self.preview.bind('<Enter>', lambda _e: self._viewport_hint(True), add='+')
        self.preview.bind('<Leave>', lambda _e: self._viewport_hint(False), add='+')

        model_bar = ttk.Frame(detail, style='Panel.TFrame')
        ttk.Label(model_bar, text='Model', style='Section.Panel.TLabel').pack(side='left', padx=(0, 8))
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
        self.open_export_btn = ttk.Button(export_top, text='Open last export', style='Ghost.Panel.TButton',
                                          command=self._open_last_export)
        self.open_export_btn.pack(side='right')
        self.open_export_btn.state(['disabled'])
        self.open_source_btn = ttk.Button(export_top, text='Show source file', style='Ghost.Panel.TButton',
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
        formats = ttk.Frame(export, style='Panel.TFrame'); formats.pack(fill='x', pady=(0, 6))
        ttk.Label(formats, text='Formats', style='Muted.Panel.TLabel').pack(side='left', padx=(0, 10))
        self.format_vars = {}
        for ext, label in (('.glb', 'GLB'), ('.gltf', 'glTF'), ('.cast', 'CAST')):
            var = tk.BooleanVar(value=ext in self.session.get('formats', ['.glb', '.cast']))
            var.trace_add('write', lambda *_: self._remember_formats())
            self.format_vars[ext] = var
            ttk.Checkbutton(formats, text=label, variable=var, style='Panel.TCheckbutton').pack(side='left', padx=(0, 14))
        self.all_lods_check = ttk.Checkbutton(bar, text='All detail levels', variable=self.all_lods_var, style='Panel.TCheckbutton')
        self.all_lods_check.pack(side='left')
        self.include_animation_check = ttk.Checkbutton(bar, text='Include animation', variable=self.include_animation,
                                                       state='disabled', style='Panel.TCheckbutton')
        self.include_animation_check.pack(side='left', padx=(18, 0))
        self.export_btn = widgets.GlossButton(bar, 'Export model', command=self._export_model, height=36, width=240)
        self.export_btn.state(['disabled'])
        self.export_btn.pack(side='right')

        rows = ((head, (0, 12)), (viewport, (0, 10)), (model_bar, (0, 6)), (self.simple_info, (2, 4)),
                (ttk.Separator(detail), (8, 12)), (anim, (0, 0)), (ttk.Separator(detail), (14, 12)), (export, (0, 0)))
        for row, (widget, pady) in enumerate(rows):
            widget.grid(row=row, column=0, sticky='nsew', pady=pady)
        detail.columnconfigure(0, weight=1); detail.rowconfigure(1, weight=1)
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
        self.session['hide_unavailable'] = hide
        if spec[0] == 'owner':
            rows = self.catalog.search_cosmetics(text, owner_guid=None if everywhere else spec[1])
        else:
            rows = self.catalog.search_assets(text, asset_type='mdl_', limit=2500)
        self.simple_assets.delete(*self.simple_assets.get_children()); self._held_tags = {}
        shown = 0
        for r in rows:
            if spec[0] == 'owner':
                models = json.loads(r['details']).get('models', [])
                found = any(m.get('pak_name') for m in models)
                if (rarity != 'all rarities' and str(r['quality']).lower() != rarity) or (hide and not found): continue
                shown += 1
                self.simple_assets.insert('', 'end', iid=f'cosmetic:{r["id"]}', tags=(str(r['quality']).lower(),) if found else ('muted',),
                                          values=(r['name'], r['quality'], 'Ready' if found else 'Not available'))
            else:
                self.simple_assets.insert('', 'end', iid=f'simple:{r["id"]}',
                                          values=(r['name'] or f'Unnamed {r["guid"]}', r['type'], r['decode_status']))
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

    def _choose_export_folder(self):
        if self._busy: return
        path = filedialog.askdirectory(title='Choose export folder',initialdir=self.export_path_var.get())
        if path: self.export_path_var.set(path); self._save_session()

    def _export_model(self):
        if not self._model or not self._model.material_family_resolved or self._busy or self._scanning: return
        model = self._model
        cosmetic = dict(self._cosmetic) if self._cosmetic else None
        label = f'{cosmetic["owner_name"]} - {cosmetic["name"]} - {self.model_choice_var.get()}' if cosmetic else Path(model.name).stem
        root = self.game_path.get(); destination = self.export_path_var.get()
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
        self._set_busy(True)
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

    def _remember_formats(self):
        self.session['formats'] = [ext for ext, var in self.format_vars.items() if var.get()]

    def _open_last_export(self):
        folder = getattr(self, '_last_export', None)
        if folder and Path(folder).exists(): open_folder(folder)

    def _show_declared_animations(self):
        show_animation_picker(self)
