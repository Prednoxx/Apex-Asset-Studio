"""Settings page: game folder, theme cards, accessibility, mascot, layout, custom colors and storage.
Also applies the appearance to the whole window. Mixed into ApexAssetStudioApp."""
import re
import shutil
import threading
import tkinter as tk
from pathlib import Path
from tkinter import colorchooser, filedialog, messagebox, ttk
from PIL import Image, ImageTk

from .. import repository
from ..repository import cache_files, default_cache_dir
from . import appearance, gloss, widgets
from .common import APP_VERSION, SHORTCUTS, folder_size, friendly_error, gb, open_folder


class SettingsPage:
    def _mascot_color(self):
        path = Path(self.appearance['mascot_path']) if self.appearance.get('mascot_path') else Path(__file__).resolve().parents[1]/'resources'/'asuka.webp'
        cache = getattr(self, '_mascot_color_cache', None)
        if cache and cache[0] == str(path): return cache[1]
        try:
            with Image.open(path) as image: color = gloss.accent_from_image(image)
        except (OSError, ValueError):
            color = None
        self._mascot_color_cache = (str(path), color)
        return color

    def _build_settings(self):
        canvas = tk.Canvas(self.settings_tab, highlightthickness=0); self.settings_canvas = canvas
        scrollbar = ttk.Scrollbar(self.settings_tab, orient='vertical', command=canvas.yview)
        scrollbar.pack(side='right', fill='y'); canvas.pack(side='left', fill='both', expand=True)
        canvas.configure(yscrollcommand=scrollbar.set)
        outer = ttk.Frame(canvas, padding=(48, 30, 48, 48))
        window = canvas.create_window((0, 0), window=outer, anchor='nw')
        outer.bind('<Configure>', lambda _e: canvas.configure(scrollregion=canvas.bbox('all')))
        canvas.bind('<Configure>', lambda event: canvas.itemconfigure(window, width=event.width))
        canvas.bind_all('<MouseWheel>', lambda e: canvas.yview_scroll(-1 if e.delta > 0 else 1, 'units')
                        if self.tabs.select() == str(self.settings_tab) else None, add='+')
        body = ttk.Frame(outer)
        body.pack(anchor='nw', fill='x')
        self.theme_var = tk.StringVar(value=self.appearance['preset'])
        self.layout_var = tk.StringVar(value=self.appearance['layout'])
        self.mascot_var = tk.BooleanVar(value=self.appearance['show_mascot'])

        ttk.Label(body, text='Settings', style='Title.TLabel').pack(anchor='w')
        ttk.Label(body, text='Changes apply immediately and are saved for next time.', style='Muted.TLabel').pack(anchor='w', pady=(4, 0))

        def section(title, hint=None):
            self._section(body, title, on='background').pack(fill='x', pady=(30, 0))
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

        themes = section('Theme', 'Glossy looks from the Frutiger Aero era. Click one to use it.')
        self.preset_cards = {}
        for index, name in enumerate(appearance.STYLE_ORDER):
            card = tk.Canvas(themes, width=self.CARD[0], height=self.CARD[1], highlightthickness=2, cursor='hand2', borderwidth=0)
            card.grid(row=index // 4, column=index % 4, padx=(0, 14), pady=(0, 14), sticky='w')
            card.bind('<Button-1>', lambda _e, n=name: self._choose_theme(n))
            self.preset_cards[name] = card
        self.custom_theme_label = ttk.Label(body, text='', style='Muted.TLabel')
        self.custom_theme_label.pack(anchor='w', pady=(8, 0))

        storage = section('Storage', 'Unpacked game files are cached so models open quickly. The cache is safe to clear; it refills as needed.')
        self.storage_text = tk.StringVar(value='Calculating…')
        ttk.Label(storage, textvariable=self.storage_text).pack(anchor='w')
        self.cache_dir_text = tk.StringVar(value=str(self._cache_dir()))
        ttk.Label(storage, textvariable=self.cache_dir_text, style='Muted.TLabel').pack(anchor='w', pady=(2, 10))
        limits = ttk.Frame(storage); limits.pack(anchor='w')
        ttk.Label(limits, text='Cache limit', width=16).pack(side='left')
        self.cache_limit_var = tk.StringVar(value=f"{self.session.get('cache_budget_gb', 12)} GB")
        limit = ttk.Combobox(limits, textvariable=self.cache_limit_var, state='readonly', width=8,
                             values=tuple(f'{n} GB' for n in (4, 8, 12, 24, 48)))
        limit.pack(side='left'); limit.bind('<<ComboboxSelected>>', lambda _e: self._set_cache_limit())
        ttk.Label(limits, text='Older files are removed automatically above this size.', style='Muted.TLabel').pack(side='left', padx=(12, 0))
        cache_buttons = ttk.Frame(storage); cache_buttons.pack(anchor='w', pady=(12, 0))
        self.clear_cache_btn = ttk.Button(cache_buttons, text='Clear cache', command=self._clear_cache)
        self.clear_cache_btn.pack(side='left')
        ttk.Button(cache_buttons, text='Open folder', style='Ghost.TButton', command=lambda: open_folder(self._cache_dir())).pack(side='left', padx=(8, 0))
        ttk.Button(cache_buttons, text='Move cache…', style='Ghost.TButton', command=self._move_cache).pack(side='left', padx=(4, 0))
        self.settings_canvas.bind('<Map>', lambda _e: self._measure_storage(), add='+')

        access = section('Accessibility', 'Text size applies everywhere, including lists and the startup screen.')
        self.text_scale_var = tk.DoubleVar(value=self.appearance['text_scale'])
        sizes = ttk.Frame(access); sizes.pack(anchor='w')
        ttk.Label(sizes, text='Text size', width=16).pack(side='left')
        for label, value in appearance.TEXT_SCALES:
            ttk.Radiobutton(sizes, text=label, value=value, variable=self.text_scale_var,
                            command=lambda: self._set_option('text_scale', self.text_scale_var.get())).pack(side='left', padx=(0, 14))
        self.contrast_var = tk.BooleanVar(value=self.appearance['high_contrast'])
        self.reduce_var = tk.BooleanVar(value=self.appearance['reduce_effects'])
        ttk.Checkbutton(access, text='High contrast text and dividers', variable=self.contrast_var,
                        command=lambda: self._set_option('high_contrast', self.contrast_var.get())).pack(anchor='w', pady=(10, 0))
        ttk.Checkbutton(access, text='Reduce visual effects (plain backgrounds, softer gloss)', variable=self.reduce_var,
                        command=lambda: self._set_option('reduce_effects', self.reduce_var.get())).pack(anchor='w', pady=(4, 0))
        keys = ttk.Frame(access); keys.pack(anchor='w', pady=(14, 0))
        ttk.Label(keys, text='Keyboard shortcuts', style='Strong.TLabel').grid(row=0, column=0, columnspan=4, sticky='w', pady=(0, 6))
        for i, (combo, action) in enumerate(SHORTCUTS):
            ttk.Label(keys, text=combo, style='Data.TLabel').grid(row=1 + i // 2, column=(i % 2) * 2, sticky='w', padx=(0, 12), pady=2)
            ttk.Label(keys, text=action, style='Muted.TLabel').grid(row=1 + i // 2, column=(i % 2) * 2 + 1, sticky='w', padx=(0, 40), pady=2)

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

        logo = section('Mascot', 'Shown in the header and on the startup screen. Any PNG or WebP works; transparent backgrounds look best.')
        self.mascot_portrait = ttk.Label(logo)
        self.mascot_portrait.pack(side='left', anchor='n')
        logo_controls = ttk.Frame(logo); logo_controls.pack(side='left', anchor='n', padx=(24, 0))
        self.mascot_accent_var = tk.BooleanVar(value=self.appearance['mascot_accent'])
        ttk.Button(logo_controls, text='Change mascot…', command=self._choose_mascot).pack(anchor='w')
        ttk.Button(logo_controls, text='Use original artwork', style='Ghost.TButton', command=self._restore_mascot).pack(anchor='w', pady=(6, 12))
        ttk.Checkbutton(logo_controls, text='Match accent color to mascot (Aero themes)', variable=self.mascot_accent_var,
                        command=lambda: self._set_option('mascot_accent', self.mascot_accent_var.get())).pack(anchor='w')
        ttk.Checkbutton(logo_controls, text='Show mascot in header', variable=self.mascot_var, command=self._toggle_mascot).pack(anchor='w', pady=(4, 0))
        self.appearance_status = ttk.Label(body, text='', style='Muted.TLabel')
        self.appearance_status.pack(anchor='w', pady=(18, 0))

    CARD = (264, 156)

    def _draw_preset_cards(self):
        """Each card is a miniature of its theme: its backdrop art, a glass panel, its fonts and button shape."""
        t = self.tokens; active = appearance.ACTIVE['style']; W, H = self.CARD
        self._card_images = {}
        for name, card in self.preset_cards.items():
            spec = appearance.STYLES[name]; chosen = name == self.appearance['preset']
            appearance.ACTIVE['style'] = name  # tokens() and fx() read the active theme
            try:
                p = appearance.tokens(spec['colors']); f = appearance.fonts(self, name); m = appearance.fx()
                image = gloss.backdrop(m['backdrop'], (W, H), p, base=p['background'], energy=.85)
                image = gloss.glass(image, (8, H - 70, W - 8, H - 8), p['surface'], radius=10, blur=8, tint_alpha=190)
                radius = None if m['radius'] is None else m['radius'] + 2
                for i, (width, color) in enumerate(((58, p['accent']), (44, gloss.shade(p['raised'], .1 if not p['light'] else -.03)), (50, gloss.shade(p['raised'], .1 if not p['light'] else -.03)))):
                    image.alpha_composite(gloss.pill(width, 20, color, radius=radius, dark=not p['light'], shine=m['shine']), (12 + i * 64 if i < 2 else 12 + 58 + 6 + 44 + 6, 12))
                button = gloss.pill(76, 24, p['accent'], radius=radius, dark=not p['light'], shine=m['shine'])
                image.alpha_composite(button, (W - 8 - 12 - 76, H - 8 - 12 - 24))
                self._card_images[name] = ImageTk.PhotoImage(image, master=card)
                card.delete('all')
                card.configure(background=p['background'], highlightbackground=t['accent'] if chosen else t['border'],
                               highlightcolor=t['accent'] if chosen else t['border'])
                card.create_image(0, 0, image=self._card_images[name], anchor='nw')
                card.create_text(20, H - 60, text=name, anchor='nw', fill=p['text'], font=f['strong'])
                card.create_text(20, H - 38, text=spec['blurb'], anchor='nw', width=W - 128, fill=p['muted'], font=f['small'])
                card.create_text(W - 20 - 38, H - 20 - 12, text='In use' if chosen else 'Use', fill=p['accent_text'], font=f['small'])
            finally:
                appearance.ACTIVE['style'] = active
        custom = self.appearance['preset'] == 'Custom'
        self.custom_theme_label.configure(text=f"Using custom colors on the {self.appearance['base']} theme. Pick a theme above to reset them." if custom else '')

    def _viewport_painter(self, w, h, message):
        """Backdrop art for the 3D viewport, with any empty-state message on a small glass card."""
        t = self.tokens
        image = gloss.backdrop(appearance.fx()['backdrop'], (w, h), t, base=t['viewport'], energy=.6)
        if message:
            headline, _, rest = message.partition('\n\n')
            image = gloss.caption(image, headline if rest else '', rest or headline, t, appearance.ACTIVE['scale'])
        return image

    def _apply_appearance(self, save=True):
        self.appearance_status.configure(text='')
        appearance.ACTIVE['mascot_accent'] = self._mascot_color()
        self.tokens = c = appearance.apply(self, self.appearance)
        f = appearance.fonts(self)
        self.simple_tree.tag_configure('category', foreground=c['muted'], font=f['strong'])
        self.simple_assets.tag_configure('muted', foreground=c['faint'])
        for rarity, color in appearance.rarity(c).items(): self.simple_assets.tag_configure(rarity, foreground=color)
        self.preview.set_palette(c['viewport']); self.preview.set_backdrop(self._viewport_painter)
        self._scale_columns()
        widgets.refresh(self, c)
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
        self._sync_color_controls(); self._apply_appearance()

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
        colors = {key: variable.get().strip() for key, variable in self.color_vars.items()}
        if any(not re.fullmatch(r'#[0-9a-fA-F]{6}', color) for color in colors.values()):
            self.appearance_status.configure(text='Enter colors as hex values, for example #e8503a.'); return
        if colors == self.appearance['colors']: return
        self.appearance.update(preset='Custom', colors=colors); self.theme_var.set('Custom')
        self._sync_color_controls(); self._apply_appearance()

    def _reset_appearance(self):
        keep = {k: self.appearance[k] for k in ('text_scale', 'high_contrast', 'reduce_effects', 'mascot_path', 'mascot_accent')}
        self.appearance = appearance.normalize(keep); self.theme_var.set(self.appearance['preset'])
        self.layout_var.set(self.appearance['layout']); self.mascot_var.set(True)
        self._sync_color_controls(); self._apply_appearance()

    def _scale_columns(self):
        """Grow fixed-width table columns with the text size so values never clip."""
        scale = self.appearance.get('text_scale', 1.0)
        if not hasattr(self, '_column_widths'):
            self._column_widths = {}
            for tree in (self.simple_tree, self.simple_assets, self.asset_table, self.string_table):
                for column in ('#0',) + tuple(tree['columns']):
                    self._column_widths[(str(tree), column)] = (tree, int(tree.column(column, 'width')), int(tree.column(column, 'minwidth')))
        for (_key, column), (tree, width, minimum) in self._column_widths.items():
            tree.column(column, width=int(width * scale), minwidth=int(minimum * scale))

    def _set_option(self, key, value):
        self.appearance[key] = value
        if key == 'text_scale': self.text_scale_var.set(value)
        self._apply_appearance()

    def _step_text_size(self, direction):
        values = [v for _l, v in appearance.TEXT_SCALES]
        current = self.appearance['text_scale']
        index = values.index(current) if current in values else 1
        if direction == 0: index = 1
        else: index = max(0, min(len(values) - 1, index + direction))
        self._set_option('text_scale', values[index])
        self.status_var.set(f'Text size: {appearance.TEXT_SCALES[index][0]}')

    def _toggle_mascot(self):
        self.appearance['show_mascot'] = self.mascot_var.get(); self._apply_appearance()

    def _load_mascot(self):
        path = Path(self.appearance['mascot_path']) if self.appearance['mascot_path'] else Path(__file__).resolve().parents[1]/'resources'/'asuka.webp'
        try:
            with Image.open(path) as image:
                image = image.convert('RGBA')
                portrait = image.copy(); portrait.thumbnail((180, 240), Image.Resampling.LANCZOS)
                self._mascot_portrait_image = ImageTk.PhotoImage(portrait)
                self._orb_image = ImageTk.PhotoImage(gloss.orb(42, appearance.face_crop(image, not self.appearance['mascot_path']), self.tokens['accent']))
                widgets.AVATAR['orb'] = self._orb_image if self.appearance['show_mascot'] else None
                widgets.AVATAR['version'] = APP_VERSION
            self.mascot_portrait.configure(image=self._mascot_portrait_image)
            self._refresh_header()
            self._set_window_icon(image)
        except (OSError, ValueError):
            self.appearance_status.configure(text='Mascot image not found or unsupported.')

    def _set_window_icon(self, image):
        """Title-bar and taskbar icon: the same round glass avatar as the header, at every size Windows asks for."""
        face = appearance.face_crop(image, not self.appearance['mascot_path'])
        key = (self.appearance['mascot_path'], self.tokens['accent'])
        if getattr(self, '_icon_key', None) == key: return
        self._icon_key = key
        icons = gloss.icon_set(face, self.tokens['accent'])
        self._icon_images = [ImageTk.PhotoImage(icons[size]) for size in (256, 128, 64, 48, 32, 16)]
        self._icon_image = self._icon_images[2]
        self.iconphoto(True, *self._icon_images)

    def _choose_mascot(self):
        path = filedialog.askopenfilename(parent=self, title='Choose mascot image', filetypes=[('Images','*.png *.jpg *.jpeg *.webp'), ('All files','*.*')])
        if not path: return
        try:
            with Image.open(path) as image: image.verify()
        except (OSError, ValueError):
            self.appearance_status.configure(text='Cannot open image.'); return
        self.appearance['mascot_path'] = path; self.appearance['show_mascot'] = True; self.mascot_var.set(True)
        self._apply_appearance()

    def _restore_mascot(self):
        self.appearance['mascot_path'] = ''; self.appearance['show_mascot'] = True; self.mascot_var.set(True)
        self._apply_appearance()

    # ---- storage ---------------------------------------------------------------------------------
    def _cache_dir(self):
        return Path(self.session.get('cache_dir') or default_cache_dir())

    def _apply_storage_settings(self):
        repository.SETTINGS['cache_dir'] = self.session.get('cache_dir') or None
        repository.SETTINGS['cache_budget'] = int(self.session.get('cache_budget_gb', 12)) * 1024**3

    def _preview_cache_dirs(self):
        base = self.appearance_path.parent
        return [base / 'preview_textures_v2', base / 'preview_textures']

    def _measure_storage(self):
        if getattr(self, '_measuring', False): return
        self._measuring = True
        catalog_file = Path(self.catalog.db_path)
        def worker():
            decoded = folder_size(self._cache_dir())
            previews = sum(folder_size(d) for d in self._preview_cache_dirs())
            library = sum(p.stat().st_size for p in catalog_file.parent.glob(catalog_file.name + '*') if p.is_file())
            self.events.put(('storage', decoded, previews, library))
        threading.Thread(target=worker, daemon=True).start()

    def _show_storage(self, decoded, previews, library):
        self._measuring = False
        limit = int(self.session.get('cache_budget_gb', 12))
        self.storage_text.set(f'Game file cache {gb(decoded)} of {limit} GB   ·   Preview textures {gb(previews)}   ·   Library index {gb(library)}')

    def _set_cache_limit(self):
        self.session['cache_budget_gb'] = int(self.cache_limit_var.get().split()[0])
        self._apply_storage_settings(); self._save_session(); self._measure_storage()

    def _clear_cache(self):
        if self._busy or self._scanning or getattr(self, '_loading', False):
            self.status_var.set('Wait for the current scan, load or export to finish, then clear the cache.'); return
        if not messagebox.askyesno('Clear cache?', 'Delete the cached game files and preview textures?\n\n'
                                   'Nothing is lost: they are rebuilt from the game when needed, so the next model you open may load more slowly.', parent=self):
            return
        self.clear_cache_btn.state(['disabled']); self.status_var.set('Clearing cache…')
        def worker():
            freed = 0; skipped = 0
            for path in cache_files(self._cache_dir()):
                try: size = path.stat().st_size; path.unlink(); freed += size
                except OSError: skipped += 1
            for folder in self._preview_cache_dirs():
                if folder.is_dir():
                    size = folder_size(folder)
                    shutil.rmtree(folder, ignore_errors=True)
                    freed += size - (folder_size(folder) if folder.exists() else 0)
            self.events.put(('cache_cleared', freed, skipped))
        threading.Thread(target=worker, daemon=True).start()

    def _move_cache(self):
        folder = filedialog.askdirectory(title='Choose a folder for the game file cache', initialdir=str(self._cache_dir().parent))
        if not folder: return
        target = Path(folder) / 'ApexAssetStudio cache' if Path(folder) != self._cache_dir() else Path(folder)
        try: target.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            self.status_var.set(friendly_error(str(exc))); return
        old = self._cache_dir()
        self.session['cache_dir'] = str(target); self._apply_storage_settings(); self._save_session()
        self.cache_dir_text.set(str(target)); self._measure_storage()
        self.status_var.set(f'Cache moved to {target}. Files in the old location ({old}) can be cleared or deleted.')
