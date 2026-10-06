"""Keeping the app trustworthy when things go wrong.

- Every error, log line and crash traceback goes to logs/app.log in the app's data folder (kept under ~2 MB).
- A small marker file says what the app is doing (scan, export…). If the app closes without removing it, the next
  start says so, removes half-written export folders, and the scan simply resumes where it stopped.
- Skins that fail to load or export are remembered with the reason ("Problems" in Advanced › Diagnostics), so it's
  clear what can't be exported yet and why.
- "Save bug report…" packs the logs, problems, settings and system details into one ZIP to send.
Mixed into the app."""
import json
import os
import platform
import shutil
import sys
import threading
import time
import traceback
import zipfile
from pathlib import Path

from .common import APP_VERSION

LOG_LIMIT = 2 * 1024 * 1024


class Reliability:
    def _start_reliability(self, data_folder):
        self._data_folder = Path(data_folder)
        logs = self._data_folder / 'logs'; logs.mkdir(parents=True, exist_ok=True)
        self._log_path = logs / 'app.log'
        try:
            if self._log_path.exists() and self._log_path.stat().st_size > LOG_LIMIT:
                self._log_path.replace(logs / 'app.old.log')
        except OSError:
            pass
        self._log_lock = threading.Lock()
        self._marker = self._data_folder / 'running.json'
        self._previous_run = None
        try:
            if self._marker.exists():
                self._previous_run = json.loads(self._marker.read_text(encoding='utf-8'))
        except (OSError, ValueError):
            self._previous_run = {'activity': 'unknown'}
        self._set_activity('starting')
        self._problems_path = self._data_folder / 'problems.json'
        self._problems = self._load_problems()
        self._file_log(f'--- Apex Asset Studio {APP_VERSION} started ({platform.platform()}, Python {platform.python_version()})')
        sys.excepthook = self._uncaught
        threading.excepthook = lambda args: self._uncaught(args.exc_type, args.exc_value, args.exc_traceback, args.thread)

    # ------------------------------------------------------------------ logging
    def _file_log(self, text):
        try:
            with self._log_lock, open(self._log_path, 'a', encoding='utf-8') as handle:
                handle.write(time.strftime('%Y-%m-%d %H:%M:%S ') + str(text).rstrip() + '\n')
        except OSError:
            pass

    def _uncaught(self, kind, value, tb, thread=None):
        where = f' in thread {thread.name}' if thread is not None else ''
        self._file_log(f'Uncaught error{where}:\n' + ''.join(traceback.format_exception(kind, value, tb)))

    def report_callback_exception(self, kind, value, tb):
        """Tk calls this for errors in button handlers and timers: log it and keep the app running."""
        self._uncaught(kind, value, tb)
        try:
            from .common import friendly_error
            self.status_var.set(friendly_error(f'{kind.__name__}: {value}'))
            self._log(''.join(traceback.format_exception(kind, value, tb)))
        except Exception:
            pass

    # ------------------------------------------------------------------ unclean exits
    def _set_activity(self, activity):
        try:
            self._marker.write_text(json.dumps({'pid': os.getpid(), 'activity': activity, 'since': time.time(),
                                                'version': APP_VERSION}), encoding='utf-8')
        except OSError:
            pass

    def _finish_reliability(self):
        try: self._marker.unlink()
        except OSError: pass
        self._file_log('--- closed normally')

    def _report_previous_run(self):
        """Called once the window is up: mention an unexpected close and tidy up after it."""
        previous = self._previous_run
        if not previous: return
        activity = previous.get('activity', 'unknown')
        self._file_log(f'Previous run ended unexpectedly while: {activity}')
        removed = self._remove_partial_exports()
        note = {'scanning': 'The library scan will continue where it stopped.',
                'exporting': 'Half-written exports were removed; export again to finish them.'}.get(activity.split(':')[0], '')
        extra = f' Removed {removed} unfinished export folder(s).' if removed else ''
        self.status_var.set(f'Apex Asset Studio closed unexpectedly last time ({activity}). {note}{extra}'.strip())
        self._log(f'Previous run ended unexpectedly while {activity}.{extra}')

    def _remove_partial_exports(self):
        """Exports are written to a hidden '.export-…' folder first and moved into place at the end; any left
        over are from an interrupted export."""
        root = Path(self.export_path_var.get())
        removed = 0
        if not root.is_dir(): return 0
        for folder in [root] + [p for p in root.iterdir() if p.is_dir() and not p.name.startswith('.')]:
            try: entries = list(folder.glob('.export-*'))
            except OSError: continue
            for path in entries:
                shutil.rmtree(path, ignore_errors=True); removed += 1
        return removed

    # ------------------------------------------------------------------ problems
    def _load_problems(self):
        try:
            value = json.loads(self._problems_path.read_text(encoding='utf-8'))
            return value if isinstance(value, list) else []
        except (OSError, ValueError):
            return []

    def _record_problem(self, name, reason, guid='', owner=''):
        key = f'{owner}|{name}|{guid}'
        self._problems = [p for p in self._problems if p.get('key') != key]
        self._problems.insert(0, {'key': key, 'name': name, 'owner': owner, 'guid': guid, 'reason': str(reason)[:400],
                                  'when': time.strftime('%Y-%m-%d %H:%M'), 'version': APP_VERSION})
        del self._problems[500:]
        try: self._problems_path.write_text(json.dumps(self._problems, indent=1), encoding='utf-8')
        except OSError: pass
        if hasattr(self, 'problems_table'): self._show_problems()

    def _show_problems(self):
        table = self.problems_table
        table.delete(*table.get_children())
        for index, problem in enumerate(self._problems):
            label = f"{problem['owner']} - {problem['name']}" if problem.get('owner') else problem['name']
            table.insert('', 'end', iid=str(index), values=(label, problem['reason'], problem['when']))
        self.problems_count_var.set(f'{len(self._problems):,} remembered' if self._problems else 'None so far')

    def _clear_problems(self):
        self._problems = []
        try: self._problems_path.unlink()
        except OSError: pass
        self._show_problems()

    # ------------------------------------------------------------------ bug report
    def save_bug_report(self):
        from tkinter import filedialog
        out = filedialog.asksaveasfilename(title='Save bug report', defaultextension='.zip', filetypes=[('ZIP', '*.zip')],
                                           initialfile=f'ApexAssetStudio_{APP_VERSION}_bug_report_{time.strftime("%Y%m%d-%H%M")}.zip')
        if not out: return
        try:
            report = self._diagnostic_report()
            with zipfile.ZipFile(out, 'w', zipfile.ZIP_DEFLATED) as archive:
                archive.writestr('report.json', json.dumps(report, indent=2, default=str))
                archive.writestr('problems.json', json.dumps(self._problems, indent=1))
                archive.writestr('visible_log.txt', self.log_text.get('1.0', 'end'))
                for path in (self._log_path, self._log_path.with_name('app.old.log'), self.session_path, self.appearance_path):
                    if Path(path).exists(): archive.write(path, Path(path).name)
            self.status_var.set(f'Saved bug report: {out}')
        except Exception as exc:
            self.status_var.set(f'Could not save the bug report: {exc}')

    def _diagnostic_report(self):
        report = self.catalog.summary()
        report.update(app_version=APP_VERSION, game_path=self.game_path.get(), platform=platform.platform(),
                      python=platform.python_version(), frozen=bool(getattr(sys, 'frozen', False)),
                      gpu=getattr(self.preview, 'renderer', 'unknown'),
                      shader=('fixed-function fallback: ' + getattr(self.preview, 'shader_error', '')) if getattr(self.preview, '_shader_failed', False) else 'GLSL',
                      model=getattr(self._model, 'guid', None), skin=(self._cosmetic or {}).get('name'))
        try:
            from ..rpak.rtech import OodleRuntime
            report['oodle_backend'] = OodleRuntime(Path(self.game_path.get()) if self.game_path.get() else Path.cwd()).description
        except Exception as exc:
            report['oodle_backend'] = f'Backend check failed: {type(exc).__name__}: {exc}'
        report['failure_groups'] = [dict(r) for r in self.catalog.failure_groups()]
        report['failures'] = [dict(r) for r in self.catalog.failed_containers(3000)]
        try:
            import numpy, PIL, OpenGL
            report['libraries'] = {'numpy': numpy.__version__, 'Pillow': PIL.__version__, 'PyOpenGL': OpenGL.__version__}
        except Exception:
            pass
        return report
