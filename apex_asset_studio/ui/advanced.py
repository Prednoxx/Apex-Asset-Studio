"""Advanced page: the full asset explorer, raw string search, and diagnostics (index summary, failures and the
log). Mixed into ApexAssetStudioApp."""
import threading
import tkinter as tk
from pathlib import Path
from tkinter import ttk

from ..rpak.rtech import OodleRuntime
from . import appearance, widgets
from .common import APP_NAME, APP_VERSION, asset_lines


class AdvancedPage:
    def _init_advanced_state(self):
        self.search_var = tk.StringVar()
        self.string_search_var = tk.StringVar()
        self.type_filter_var = tk.StringVar(value="All types")
        self.advanced_count_var = tk.StringVar(value="")

    def _build_advanced(self):
        """Advanced page: every indexed asset, raw string search, and diagnostics (index summary and log)."""
        page = ttk.Frame(self.advanced_tab, padding=(18, 14, 18, 14))
        page.pack(fill='both', expand=True)
        inner = self.advanced_tabs = ttk.Notebook(page)
        inner.pack(fill='both', expand=True)
        assets_tab = ttk.Frame(inner, padding=(0, 4, 0, 0))
        strings_tab = ttk.Frame(inner, padding=(0, 4, 0, 0))
        self.diag_tab = ttk.Frame(inner, padding=(0, 4, 0, 0))
        inner.add(assets_tab, text='Assets')
        inner.add(strings_tab, text='Strings')
        inner.add(self.diag_tab, text='Diagnostics')

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
        self.advanced_more_btn = ttk.Button(top, text='Show more', style='Ghost.TButton', command=lambda: self.search_advanced(more=True))
        self.advanced_more_btn.pack(side='right'); self.advanced_more_btn.state(['disabled'])
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
        labels = {'type': 'Type', 'name': 'Name', 'guid': 'GUID', 'ver': 'Ver', 'hdr': 'Header', 'pak': 'Container',
                  'patch': 'Patch', 'compression': 'Compression', 'starpak': 'StarPak'}
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
        self.advanced_open_btn = ttk.Button(detail_header, text='Show source file', style='Ghost.Panel.TButton',
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
        self.string_more_btn = ttk.Button(string_top, text='Show more', style='Ghost.TButton', command=lambda: self.search_strings(more=True))
        self.string_more_btn.pack(side='right'); self.string_more_btn.state(['disabled'])

        string_frame = ttk.Frame(strings_tab, style='Panel.TFrame')
        string_frame.pack(fill='both', expand=True)
        string_cols = ('value', 'container', 'compression')
        self.string_table = ttk.Treeview(string_frame, columns=string_cols, show='headings')
        for key, title, width, stretch in (('value', 'Value', 700, True), ('container', 'Container', 360, True), ('compression', 'Compression', 110, False)):
            self.string_table.heading(key, text=title, anchor='w')
            self.string_table.column(key, width=width, stretch=stretch, anchor='w')
        string_scroll = ttk.Scrollbar(string_frame, orient='vertical', command=self.string_table.yview)
        string_scroll.pack(side='right', fill='y'); self.string_table.configure(yscrollcommand=string_scroll.set)
        self.string_table.pack(fill='both', expand=True)
        self._build_diagnostics()

    def _build_diagnostics(self):
        page = self.diag_tab
        header = ttk.Frame(page)
        header.pack(fill='x', pady=(0, 12))
        ttk.Label(header, text='', style='Muted.TLabel').pack(side='left')
        widgets.tip(ttk.Button(header, text='Save bug report…', command=self.save_bug_report),
                    'Logs, problems, settings and system info in one ZIP').pack(side='right')
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
        problems_frame = ttk.Frame(pane, style='Panel.TFrame', padding=(14, 12, 14, 8))
        pane.add(problems_frame, weight=1)
        top = ttk.Frame(problems_frame, style='Panel.TFrame'); top.pack(fill='x')
        self._section(top, 'Problems').pack(side='left', fill='x', expand=True)
        self.problems_count_var = tk.StringVar(value='')
        ttk.Label(top, textvariable=self.problems_count_var, style='Muted.Panel.TLabel').pack(side='left', padx=(8, 8))
        ttk.Button(top, text='Clear', style='Ghost.Panel.TButton', command=self._clear_problems).pack(side='right')
        ttk.Label(problems_frame, text='',
                  style='Muted.Panel.TLabel').pack(anchor='w', pady=(2, 6))
        table_frame = ttk.Frame(problems_frame, style='Panel.TFrame'); table_frame.pack(fill='both', expand=True)
        self.problems_table = ttk.Treeview(table_frame, columns=('skin', 'reason', 'when'), show='headings', height=5)
        for key, title, width, stretch in (('skin', 'Skin', 240, False), ('reason', 'Reason', 520, True), ('when', 'When', 130, False)):
            self.problems_table.heading(key, text=title, anchor='w'); self.problems_table.column(key, width=width, stretch=stretch, anchor='w')
        scroll = ttk.Scrollbar(table_frame, orient='vertical', command=self.problems_table.yview)
        scroll.pack(side='right', fill='y'); self.problems_table.configure(yscrollcommand=scroll.set)
        self.problems_table.pack(fill='both', expand=True)
        self._show_problems()
        summary_frame = ttk.Frame(pane, style='Panel.TFrame', padding=(14, 12, 14, 0))
        log_frame = ttk.Frame(pane, style='Panel.TFrame', padding=(14, 12, 14, 0))
        pane.add(summary_frame, weight=1)
        pane.add(log_frame, weight=2)
        self._section(summary_frame, 'Index summary').pack(fill='x')
        self.summary_text = tk.Text(summary_frame, height=14, font=mono, wrap='none', state='disabled')
        self.summary_text.flush = True; self.summary_text.font_key = 'mono'
        self.summary_text.pack(fill='both', expand=True, pady=(8, 0))
        self._section(log_frame, 'Log').pack(fill='x')
        self.log_text = tk.Text(log_frame, font=mono, wrap='none')
        self.log_text.flush = True; self.log_text.font_key = 'mono'
        self.log_text.pack(fill='both', expand=True, pady=(8, 0))

    def _advanced_asset_selected(self, _event=None):
        sel = self.asset_table.selection()
        if not sel:
            return
        asset_id = int(sel[0].split(":", 1)[1])
        row = self.catalog.get_asset(asset_id)
        if row is None:
            return
        lines = asset_lines(row) + [f'Name:              {row["name"] or "unresolved"}', f'Decode status:     {row["decode_status"]}',
                                    f'Decode error:      {row["decode_error"] or "none"}', row['details'] or '']
        edges = self.catalog.dependencies(row['id'])
        lines += ['', 'Registered GUID references (raw dependencies):']
        lines += [f'{e["guid"]}  page {e["page"]}+{e["offset"]}  {e["type"] or "unresolved"}  {e["name"] or ""}  {e["filename"] or ""}' for e in edges[:100]]
        self._set_asset_detail('\n'.join(lines))
        self.advanced_open_btn.state(['!disabled'])
        self.advanced_preview_btn.state(['!disabled'] if row['type'] == 'mdl_' and not self._busy else ['disabled'])

    def refresh_type_filter(self):
        values = ["All types", *self.catalog.asset_types()]
        self.type_filter.configure(values=values)
        if self.type_filter_var.get() not in values:
            self.type_filter_var.set("All types")

    PAGE = 2000

    def search_advanced(self, more=False):
        """Runs off the UI thread; results arrive a page at a time ("Show more" loads the next page)."""
        text = self.search_var.get().strip()
        chosen = self.type_filter_var.get()
        asset_type = None if chosen == "All types" else chosen
        if not more:
            self.asset_table.delete(*self.asset_table.get_children())
            self._advanced_offset = 0
            self._set_asset_detail('')
            self.advanced_open_btn.state(["disabled"]); self.advanced_preview_btn.state(['disabled'])
        self._advanced_serial = serial = getattr(self, '_advanced_serial', 0) + 1
        offset = self._advanced_offset
        self.advanced_count_var.set('Searching…'); self.advanced_more_btn.state(['disabled'])
        def worker():
            try:
                rows = self.catalog.search_assets(text, asset_type=asset_type, limit=self.PAGE, offset=offset)
                total = offset + len(rows) if len(rows) < self.PAGE else self.catalog.count_assets(text, asset_type)
                self.events.put(('advanced_results', serial, rows, total))
            except Exception as exc:
                self.events.put(('advanced_results', serial, [], f'{type(exc).__name__}: {exc}'))
        threading.Thread(target=worker, daemon=True).start()

    def _show_advanced_results(self, serial, rows, total):
        if serial != getattr(self, '_advanced_serial', 0): return
        if isinstance(total, str):
            self.advanced_count_var.set('Search failed'); self._log(total); return
        for r in rows:
            if self.asset_table.exists(f"asset:{r['id']}"): continue
            self.asset_table.insert(
                "", "end", iid=f"asset:{r['id']}",
                values=(
                    r["type"], r['name'] or '(unresolved)', r["guid"], r["version"], r["header_size"], r["filename"],
                    r["patch_count"], r["compression"], r["starpak_offset"] or "",
                ),
            )
        self._advanced_offset += len(rows)
        shown = self._advanced_offset
        capped = total > self.catalog.COUNT_CAP
        self.advanced_count_var.set(f"{shown:,} of {self.catalog.COUNT_CAP:,}+" if capped else f"{shown:,} of {total:,}")
        self.advanced_more_btn.state(['!disabled'] if shown < total else ['disabled'])

    def _clear_advanced_search(self):
        self.search_var.set("")
        self.type_filter_var.set("All types")
        self.search_advanced()

    def search_strings(self, more=False):
        query = self.string_search_var.get().strip()
        if not more:
            self.string_table.delete(*self.string_table.get_children()); self._string_offset = 0
        if not query:
            self.status_var.set("Type something to search for.")
            return
        self._string_serial = serial = getattr(self, '_string_serial', 0) + 1
        offset = self._string_offset
        self.status_var.set('Searching strings…'); self.string_more_btn.state(['disabled'])
        def worker():
            try: rows = self.catalog.search_strings(query, limit=self.PAGE, offset=offset)
            except Exception as exc: rows = f'{type(exc).__name__}: {exc}'
            self.events.put(('string_results', serial, rows))
        threading.Thread(target=worker, daemon=True).start()

    def _show_string_results(self, serial, rows):
        if serial != getattr(self, '_string_serial', 0): return
        if isinstance(rows, str):
            self.status_var.set('String search failed.'); self._log(rows); return
        for r in rows:
            self.string_table.insert("", "end", values=(r["value"], r["filename"], r["compression"]))
        self._string_offset += len(rows)
        more = len(rows) == self.PAGE
        self.string_more_btn.state(['!disabled'] if more else ['disabled'])
        self.status_var.set(f"{self._string_offset:,}{'+' if more else ''} strings found")

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

    def _set_asset_detail(self, text: str):
        self.asset_detail.configure(state="normal")
        self.asset_detail.delete("1.0", "end")
        self.asset_detail.insert("1.0", text)
        self.asset_detail.configure(state="disabled")

    def _preview_advanced(self):
        sel = self.asset_table.selection()
        if not sel or self._busy or self._scanning: return
        row = self.catalog.get_asset(int(sel[0].split(':')[1]))
        if not row or row['type'] != 'mdl_': return
        self._cosmetic = None
        self._model_choices = []
        self._selection_serial += 1
        self.tabs.select(self.library_tab)
        self._start_model_load(row['guid'],row['path'])

    def _log(self, text):
        self._file_log(text)
        self.log_text.insert("end", str(text) + "\n")
        self.log_text.see("end")
