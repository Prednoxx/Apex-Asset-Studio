"""Apex Asset Studio main window: the header, status bar and page switching, the library scan, the background
event pump and session state. The pages live in library.py, advanced.py and settings.py (as mixins)."""
from __future__ import annotations

import json
import os
import queue
import sys
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from ..catalog import Catalog
from ..game_locator import find_apex_installations
from . import appearance, widgets
from .advanced import AdvancedPage
from .common import APP_NAME, APP_VERSION, friendly_error, gb, make_sortable
from .library import LibraryPage
from .settings import SettingsPage
from .splash import StartupSplash


class ApexAssetStudioApp(LibraryPage, AdvancedPage, SettingsPage, tk.Tk):
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
        self.appearance = appearance.load(self.appearance_path)
        appearance.ACTIVE.update(style=self.appearance['base'], scale=self.appearance['text_scale'],
                                 contrast=self.appearance['high_contrast'], reduce=self.appearance['reduce_effects'],
                                 mascot_accent=self._mascot_color())
        splash = StartupSplash(self, appearance.effective_colors(self.appearance), self.appearance['mascot_path'] or None,
                               APP_VERSION) if show_splash else None
        if splash: splash.stage('Opening index…')
        self.catalog = Catalog(catalog_path or appdata / "catalog.sqlite3")

        self.game_path = tk.StringVar()
        self.status_var = tk.StringVar(value="Ready")
        self.progress_var = tk.DoubleVar(value=0)
        self.session_path = self.appearance_path.with_name('session.json')
        self.session = self._load_session()
        self._apply_storage_settings()
        self._busy = False
        self._scan_label, self._scan_enabled = 'Scan library', True
        self.scan_stop = threading.Event()
        self.events: queue.Queue = queue.Queue()
        self._scan_thread: threading.Thread | None = None
        self._scanning = False
        self._init_library_state()
        self._init_advanced_state()

        if splash: splash.stage('Loading settings…')
        self._build_ui()
        self._apply_appearance(save=False)
        self._update_animation_display()
        self.after(100, self._poll_events)
        self.protocol('WM_DELETE_WINDOW', self._close)
        self._bind_shortcuts()
        if splash: splash.stage('Detecting Apex…')
        self._auto_detect()
        if splash: splash.stage('Loading library…')
        self.refresh_all_views()
        for tree in (self.simple_assets, self.asset_table, self.string_table): make_sortable(tree)
        if not self.catalog.index_outdated:  # one-time link table for libraries scanned by older versions
            threading.Thread(target=self.catalog.ensure_animation_links, daemon=True).start()
        self._restore_session()
        if splash: splash.finish(self)
        else: self.deiconify()

    # ------------------------------------------------------------------ shell
    PAGES = ('Library', 'Advanced', 'Settings')

    def _build_ui(self):
        self.headerbar = widgets.HeaderBar(self, self, pages=self._header_pages, on_page=lambda key: self.tabs.select(key),
                                           scan=self._header_scan, on_scan=self._scan_button_clicked, game=self._header_game,
                                           on_game=lambda: self._show_page(self.settings_tab))
        self.headerbar.pack(fill='x')
        self.game_path.trace_add('write', lambda *_: self._refresh_header())

        status = ttk.Frame(self, padding=(14, 5, 14, 6))
        status.pack(side='bottom', fill='x')
        ttk.Label(status, textvariable=self.status_var, style='Status.TLabel').pack(side='left')
        self.progress = ttk.Progressbar(status, variable=self.progress_var, maximum=100, length=260)
        self.busy_bar = ttk.Progressbar(status, mode='indeterminate', length=120)
        ttk.Frame(self, style='Hairline.TFrame', height=1).pack(side='bottom', fill='x')

        self.tabs = ttk.Notebook(self, style='Pages.TNotebook')
        self.tabs.pack(fill='both', expand=True)
        self.library_tab = ttk.Frame(self.tabs)
        self.advanced_tab = ttk.Frame(self.tabs)
        self.settings_tab = ttk.Frame(self.tabs)
        self.page_tabs = (self.library_tab, self.advanced_tab, self.settings_tab)
        for tab, label in zip(self.page_tabs, self.PAGES): self.tabs.add(tab, text=label)
        self.tabs.bind('<<NotebookTabChanged>>', lambda _e: self._refresh_header())
        self._build_library()
        self._build_advanced()
        self._build_settings()

    def _page_label(self, key=None):
        key = key or self.tabs.select()
        return next((label for tab, label in zip(self.page_tabs, self.PAGES) if str(tab) == str(key)), 'Library')

    def _header_pages(self):
        current = self.tabs.select()
        return [(str(tab), label, str(tab) == current) for tab, label in zip(self.page_tabs, self.PAGES)]

    def _header_scan(self):
        return self._scan_label, self._scan_enabled

    def _set_scan_button(self, label=None, enabled=None):
        if label is not None: self._scan_label = label
        if enabled is not None: self._scan_enabled = enabled
        self._refresh_header()

    def _header_game(self):
        path = self.game_path.get().strip(); found = bool(path) and Path(path).exists()
        return found, 'Apex Legends found' if found else 'Set Apex folder'

    def _refresh_header(self):
        if getattr(self, 'tokens', None): self.headerbar.redraw(self.tokens)

    def _show_page(self, tab):
        self.tabs.select(tab)

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

    def _section(self, parent, text, on='surface'):
        return widgets.SectionTag(parent, text, on=on, width=80)

    def _typing(self):
        widget = self.focus_get()
        return isinstance(widget, (ttk.Entry, tk.Entry, tk.Text, ttk.Combobox, ttk.Spinbox))

    def _bind_shortcuts(self):
        def page(i): return lambda _e: self.tabs.select(self.page_tabs[i])
        for i in range(len(self.page_tabs)): self.bind_all(f'<Control-Key-{i+1}>', page(i))
        self.bind_all('<Control-f>', lambda _e: (self.tabs.select(self.library_tab), self.simple_search_entry.focus_set(), 'break')[-1])
        self.bind_all('<Control-e>', lambda _e: self._export_model())
        self.bind_all('<Control-E>', lambda _e: self._export_animation())
        self.bind_all('<F5>', lambda _e: self._scan_button_clicked())
        for key in ('<Control-plus>', '<Control-equal>', '<Control-KP_Add>'): self.bind_all(key, lambda _e: self._step_text_size(1))
        for key in ('<Control-minus>', '<Control-KP_Subtract>'): self.bind_all(key, lambda _e: self._step_text_size(-1))
        self.bind_all('<Control-0>', lambda _e: self._step_text_size(0))
        def space(_e):
            if self._typing() or isinstance(self.focus_get(), (ttk.Button, ttk.Checkbutton, ttk.Radiobutton)): return None
            self._toggle_animation(); return 'break'
        self.bind_all('<space>', space)
        self.bind_all('<Key-r>', lambda _e: None if self._typing() else self.preview.reset_view())

    # ------------------------------------------------------------------ library scan
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
        if not self._scan_enabled: return
        if self._scanning:
            if not self.scan_stop.is_set():
                self.scan_stop.set()
                self._set_scan_button('Stopping…', False)
                self.status_var.set("Stopping scan after the current RPak…")
            return
        self.start_scan()

    def _set_scanning(self, scanning: bool):
        self._scanning = scanning
        for widget in (self.all_lods_check, self.export_folder_entry, self.export_folder_btn,
                       self.path_entry, self.detect_btn, self.browse_btn):
            widget.state(['disabled' if scanning else '!disabled'])
        if scanning:
            self._selection_serial += 1
            self._model = None
            self._animation=None;self._animation_serial+=1;self._playing=False;self.animation_name.set('')
            self.play_btn.configure(text='Play')
            for widget in (self.play_btn,self.frame_slider,self.animation_export_btn,self.include_animation_check,
                           self.export_btn,self.animations_btn,self.open_source_btn): widget.state(['disabled'])
            self.preview.clear('Scanning library…')
            self.model_choice.configure(state='disabled')
            self.lod_choice.configure(state='disabled')
            self.progress.pack(side="right")
            self._set_scan_button('Stop scan', True)
        else:
            self.progress.pack_forget()
            self.scan_stop.clear()
            self._set_scan_button('Scan library', True)

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
                    if serial != self._selection_serial:
                        continue
                    self._set_loading(False)
                    self._model = model
                    levels = model.lod_levels or sorted(model.lods)
                    self.lod_choice.configure(values=[f'LOD {x}' for x in levels],state='readonly')
                    wanted = getattr(self, '_wanted_lod', None)
                    level = wanted if wanted in model.lods else min(model.lods)
                    self._wanted_lod = None
                    self.lod_var.set(f'LOD {level}')
                    self._render_model()
                    self.export_btn.state(['!disabled'] if model.material_family_resolved else ['disabled'])
                    self.open_source_btn.state(['!disabled'])
                    self.animations_btn.state(['!disabled'])
                    total = sum(len(m.positions) for m in model.lods[min(model.lods)])
                    title = self._cosmetic['name'] if self._cosmetic else Path(model.name).stem
                    owner = f'{self._cosmetic["owner_name"]}  ·  {self.model_choice_var.get()}  ·  ' if self._cosmetic else ''
                    self._set_inspector(title, f'{owner}{total:,} vtx  ·  {len(model.bones)} bones  ·  {len(model.lod_levels or model.lods)} lod')
                    self._set_simple_info('\n'.join(warnings+model.warnings) + ('' if model.material_family_resolved else
                        "\nThis skin's materials can't be read yet, so it can't be exported. You can still preview it."))
                    self.status_var.set('Model loaded.' if model.material_family_resolved else "Model loaded. This skin can't be exported yet.")
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
                    if getattr(self, '_loading', False): self._set_loading(False)
                    message = friendly_error(error)
                    if self._model:
                        lod = int(self.lod_var.get().split()[-1])
                        if lod not in self._model.lods:
                            # the extra detail levels failed: stay on what is decoded and stop offering the rest,
                            # so picking the LOD again can't start the same failing load in a loop
                            self._wanted_lod = None
                            self._model.partial = False
                            self._model.lod_levels = sorted(self._model.lods)
                            self.lod_choice.configure(values=[f'LOD {x}' for x in self._model.lod_levels], state='readonly')
                            self.lod_var.set(f'LOD {min(self._model.lods)}')
                            message = f"Couldn't load LOD {lod}. {message}"
                        self.lod_choice.configure(state='readonly')
                        self._render_model()
                    else: self.preview.clear('Preview unavailable')
                    self._set_simple_info(message)
                    self.status_var.set(message)
                    self._log(error)
                elif event[0] == 'storage':
                    self._show_storage(*event[1:])
                elif event[0] == 'cache_cleared':
                    _, freed, skipped = event
                    self.clear_cache_btn.state(['!disabled'])
                    note = f' {skipped} file(s) in use were kept.' if skipped else ''
                    self.status_var.set(f'Cache cleared: {gb(freed)} freed.{note}')
                    self._preview_cache.clear(); self._measure_storage()
                elif event[0] == 'advanced_results':
                    self._show_advanced_results(*event[1:])
                elif event[0] == 'string_results':
                    self._show_string_results(*event[1:])
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
                        self.status_var.set(friendly_error(result)); self._log(result)
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
                    self._last_export = path.parent
                    partial = '' if manifest['status'] == 'decoded' else ' Some materials were incomplete; see the manifest.'
                    self.status_var.set(f'Exported to {path.parent.name}.{partial}{getattr(self, "_blender_note", "")}')
                    self.open_export_btn.state(['!disabled'])
                    self._log(f'Export manifest: {path}')
        except queue.Empty:
            pass
        except Exception as exc:  # never let one bad event stop the event pump
            import traceback
            self._log(''.join(traceback.format_exception(exc)))
            self.status_var.set(friendly_error(f'{type(exc).__name__}: {exc}'))
        self.after(100, self._poll_events)

    def refresh_all_views(self):
        self.refresh_summary()
        self.refresh_simple_library()
        self.refresh_type_filter()
        self.search_advanced()

    def _set_busy(self, busy):
        self._busy = busy
        if busy:
            self._playing=False; self.play_btn.configure(text='Play')
            if self._play_timer is not None: self.after_cancel(self._play_timer); self._play_timer=None
        state = 'disabled' if busy else '!disabled'
        for widget in (self.detect_btn,self.browse_btn,self.path_entry,self.simple_tree,self.simple_assets,
                       self.all_lods_check,self.export_folder_entry,self.export_folder_btn):
            widget.state([state])
        self._scan_enabled = not busy
        self.export_btn.state(['disabled'] if busy or self._model is None or not self._model.material_family_resolved else ['!disabled'])
        self.animations_btn.state(['disabled'] if busy or self._model is None else ['!disabled'])
        for widget in (self.play_btn,self.frame_slider,self.animation_export_btn,self.include_animation_check):
            widget.state(['disabled'] if busy or self._animation is None else ['!disabled'])
        self.model_choice.configure(state='readonly' if not busy and self._model_choices and self._cosmetic else 'disabled')
        self.lod_choice.configure(state='readonly' if not busy and self._model else 'disabled')
        self.advanced_preview_btn.state(['disabled'])
        self._refresh_header()

    @staticmethod
    def _default_export_folder():
        if getattr(sys, 'frozen', False): return Path(sys.executable).parent / 'Exports'
        source = Path(__file__).resolve().parents[2]
        master = source.parent / 'Exports'  # "Apex Studio Master\\Exports" when running from the master folder
        return master if master.is_dir() else source / 'Exports'

    # ------------------------------------------------------------------ session
    def _load_session(self):
        try:
            value = json.loads(self.session_path.read_text(encoding='utf-8'))
            return value if isinstance(value, dict) else {}
        except (OSError, ValueError):
            return {}

    def _save_session(self):
        if hasattr(self, 'hide_unavailable_var'): self.session['hide_unavailable'] = self.hide_unavailable_var.get()
        state = dict(self.session, geometry=self.geometry() if self.state() == 'normal' else self.session.get('geometry'),
                     zoomed=self.state() == 'zoomed', export_path=self.export_path_var.get(), page=self._page_label(),
                     formats=[ext for ext, var in getattr(self, 'format_vars', {}).items() if var.get()] or self.session.get('formats'))
        try:
            temp = self.session_path.with_suffix('.tmp'); temp.write_text(json.dumps(state, indent=2), encoding='utf-8'); temp.replace(self.session_path)
            self.session = state
        except OSError:
            pass

    def _restore_session(self):
        geometry = self.session.get('geometry')
        if isinstance(geometry, str) and 'x' in geometry: self.geometry(geometry)
        if self.session.get('zoomed'):
            try: self.state('zoomed')
            except tk.TclError: pass
        page = {'Explorer': 'Advanced', 'Diagnostics': 'Advanced'}.get(self.session.get('page'), self.session.get('page'))
        if page in self.PAGES and page != 'Settings': self.tabs.select(self.page_tabs[self.PAGES.index(page)])

    def _close(self):
        self._save_session()
        self.destroy()


def main():
    if os.name == 'nt':
        # Own taskbar identity, so Windows shows the app's icon instead of grouping it under python.exe.
        try:
            import ctypes
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID('ApexAssetStudio.Desktop')
        except (OSError, AttributeError):
            pass
    app = ApexAssetStudioApp()
    app.mainloop()
