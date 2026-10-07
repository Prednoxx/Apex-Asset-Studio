"""Batch export and folders."""
import json
import threading
from pathlib import Path
from tkinter import messagebox

from ..cosmetics import lobby_lighting
from ..export.package import export_package
from ..repository import AssetRepository
from ..rpak.material import safe_name
from ..rpak.model import decode_model
from ..rpak.oodle_stream import ScanCancelled
from .common import LOG_HINT

MAIN_MODEL = ('bodyModel', 'worldModel', 'viewModel', 'armsModel')  # Preferred main-model fields


class BatchExport:
    def _export_folder_for(self, cosmetic):
        root = Path(self.export_path_var.get())
        return root / safe_name(cosmetic['owner_name']) if cosmetic else root

    def _cosmetic_for_export(self, cosmetic):
        """Cosmetic metadata with lobby lighting."""
        if not cosmetic: return None
        cosmetic = dict(cosmetic)
        try:
            cosmetic['lobby_lighting'] = lobby_lighting(self.catalog.settings_values(cosmetic['skin_guid']),
                                                        self.catalog.settings_values(cosmetic['owner_guid']))
        except Exception:  # Optional lighting must not block
            cosmetic['lobby_lighting'] = None
        return cosmetic

    def _selected_cosmetic_ids(self):
        return [int(iid.split(':')[1]) for iid in self.simple_assets.selection() if iid.startswith('cosmetic:')]

    def _listed_cosmetic_ids(self):
        return [int(iid.split(':')[1]) for iid in self.simple_assets.get_children('') if iid.startswith('cosmetic:')]

    def _batch_size(self):
        ids = self._selected_cosmetic_ids()
        return len(ids) if len(ids) > 1 else 0

    def _batch_job(self, row):
        """Resolve skin export or failure."""
        cosmetic = dict(row)
        models = json.loads(cosmetic['details']).get('models', [])
        available = [m for m in models if m.get('pak_name')]
        choice = next((m for field in MAIN_MODEL for m in available if m['field'] == field), None)
        label = f"{cosmetic['owner_name']} - {cosmetic['name']}"
        if choice is None:
            return dict(label=label, skip='not in the game files')
        root = Path(self.game_path.get())
        return dict(label=f"{label} - {self._model_label(choice)}", guid=choice['guid'],
                    preferred=root / 'paks' / 'Win64' / choice['pak_name'],
                    family=json.loads(cosmetic['details']).get('skin_family'), cosmetic=cosmetic)

    def _export_list(self):
        """Export current filtered list."""
        ids = self._listed_cosmetic_ids()
        if not ids:
            self.status_var.set('No skins to export.'); return
        self._export_batch(ids)

    def _export_batch(self, ids=None):
        ids = ids or self._selected_cosmetic_ids()
        if not ids or self._busy or self._scanning: return
        formats = [ext for ext, var in self.format_vars.items() if var.get()]
        if not formats:
            self.status_var.set('Select at least one export format.'); return
        destination = Path(self.export_path_var.get())
        if not messagebox.askyesno('Export skins', f'Export {len(ids):,} skins to\n{destination}?\n\n'
                                   'Skins already exported are skipped.', parent=self):
            return
        rows = [self.catalog.get_cosmetic(i) for i in ids]
        jobs = [self._batch_job(r) for r in rows if r is not None]
        all_lods = self.all_lods_var.get(); root = self.game_path.get()
        stop = self._batch_stop = threading.Event()
        self._playing = False; self.play_btn.configure(text='Play')
        self._set_busy(True); self._batch_running = True; self._set_activity(f'exporting: batch of {len(jobs)}')
        self.progress_var.set(0); self.progress.pack(side='right')
        self.batch_cancel_btn.state(['!disabled']); self._show_batch_cancel(True)

        def worker():
            done, skipped, failed = [], [], []
            for index, job in enumerate(jobs):
                if stop.is_set(): break
                self.events.put(('batch_progress', index, len(jobs), job['label']))
                if 'skip' in job:
                    skipped.append(f"{job['label']}: {job['skip']}"); continue
                cosmetic = job['cosmetic']
                folder = destination / safe_name(cosmetic['owner_name'])
                if (folder / safe_name(job['label'])).exists():
                    skipped.append(f"{job['label']}: already exported"); continue
                try:
                    with AssetRepository(self.catalog, root) as repo:
                        archive, asset = repo.asset(job['guid'], job['preferred'])
                        model = decode_model(archive, asset, job['family'], stop=stop, allow_unresolved_family=True,
                                             first_lod_only=not all_lods)
                    if not model.material_family_resolved:
                        skipped.append(f"{job['label']}: materials not supported")
                        self.events.put(('problem', cosmetic['name'], 'Materials not supported', cosmetic['skin_guid'], cosmetic['owner_name']))
                        continue
                    export_package(model, self.catalog, root, folder, job['label'], self._cosmetic_for_export(cosmetic),
                                   all_lods, None, overwrite=False, formats=formats)
                    done.append(job['label'])
                except ScanCancelled:
                    break
                except Exception as exc:
                    failed.append(f"{job['label']}: {type(exc).__name__}: {exc}")
                    self.events.put(('problem', cosmetic['name'], f'{type(exc).__name__}: {exc}', cosmetic['skin_guid'], cosmetic['owner_name']))
            self.events.put(('batch_done', done, skipped, failed, stop.is_set(), destination))
        threading.Thread(target=worker, daemon=True).start()

    def _cancel_batch(self):
        if getattr(self, '_batch_stop', None): self._batch_stop.set()
        self.batch_cancel_btn.state(['disabled'])
        self.status_var.set('Stopping after the current skin…')

    def _batch_progress(self, index, total, label):
        self.progress_var.set(index / max(total, 1) * 100)
        self.status_var.set(f'Exporting {index + 1:,} of {total:,}: {label}')

    def _batch_done(self, done, skipped, failed, cancelled, destination):
        self._batch_running = False; self._set_activity('idle')
        self.progress.pack_forget(); self._show_batch_cancel(False)
        self._set_busy(False)
        self._last_export = destination; self.open_export_btn.state(['!disabled'])
        for line in skipped: self._log(f'Batch skipped: {line}')
        for line in failed: self._log(f'Batch failed: {line}')
        parts = [f'{len(done):,} exported']
        if skipped: parts.append(f'{len(skipped):,} skipped')
        if failed: parts.append(f'{len(failed):,} failed')
        head = 'Batch cancelled' if cancelled else 'Batch done'
        self.status_var.set(f"{head}: {', '.join(parts)}." + (f' {LOG_HINT}' if skipped or failed else ''))

    def _show_batch_cancel(self, show):
        btn = self.batch_cancel_btn
        if show and not btn.winfo_ismapped(): btn._flow_hidden = False; self._export_links.add(btn)
        elif not show and btn in [w for w, _g in self._export_links.items]:
            self._export_links.items = [(w, g) for w, g in self._export_links.items if w is not btn]
            btn.place_forget(); self._export_links._schedule()
