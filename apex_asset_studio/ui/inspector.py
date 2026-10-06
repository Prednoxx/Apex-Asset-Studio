"""Materials & textures inspector for the loaded model.

Lists every material the model uses with its game name and whether it was fully understood, and under each one
its textures: role (base color, normal, gloss…), the shader slot it feeds, size, pixel format, which channels are
used, and anything unresolved. Picking a material highlights it in the 3D preview (everything else is dimmed);
picking a texture shows it. Answers "why does this look wrong in Blender" without digging through files."""
import queue
import tempfile
import threading
import tkinter as tk
from pathlib import Path
from tkinter import ttk

from PIL import Image, ImageTk

from ..repository import AssetRepository
from ..rpak.material import decode_material
from ..rpak.texture import extract_texture, texture_info
from .appearance import fonts

ROLE_NAMES = {'basecolor': 'Base color', 'normal': 'Normal', 'specular': 'Specular', 'gloss': 'Gloss', 'ao': 'Ambient occlusion',
              'cavity': 'Cavity', 'emission': 'Emission', 'alpha': 'Opacity', 'scatter_thickness': 'Skin scattering',
              'anisotropy_direction': 'Strand direction', 'normal_xy_unresolved': 'Normal (unresolved)'}
SUPPORTED = set(ROLE_NAMES) - {'normal_xy_unresolved'}


def _channels(entry):
    channels = entry.get('channels')
    if isinstance(channels, dict):
        used = [f'{c}: {v}' for c, v in channels.items() if v not in ('not sampled', 'unresolved')]
        return ', '.join(used) or '—'
    return str(channels or '—')


def close_material_inspector(app):
    """Close the inspector (a different model was loaded, so its contents no longer apply)."""
    window = getattr(app, '_inspector', None)
    if window is not None and window.winfo_exists():
        window._close()


def show_material_inspector(app):
    model = app._model
    if model is None:
        app.status_var.set('Load a model first.'); return
    if getattr(app, '_inspector', None) and app._inspector.winfo_exists():
        app._inspector.lift(); return
    t = app.tokens
    window = tk.Toplevel(app); app._inspector = window
    window.title(f'Materials · {app.inspector_title.get()}'); window.geometry('1240x640'); window.minsize(820, 420)
    window.configure(background=t['background']); window.transient(app)
    if hasattr(app, '_icon_image'): window.iconphoto(False, app._icon_image)
    head = ttk.Frame(window, padding=(16, 14, 16, 8)); head.pack(fill='x')
    ttk.Label(head, text='Materials & textures', style='Title.TLabel').pack(side='left')
    status = tk.StringVar(value='Reading materials…')
    ttk.Label(head, textvariable=status, style='Muted.TLabel').pack(side='left', padx=(14, 0), pady=(6, 0))
    body = ttk.Panedwindow(window, orient='horizontal'); body.pack(fill='both', expand=True, padx=16, pady=(0, 16))
    left = ttk.Frame(body, style='Panel.TFrame'); body.add(left, weight=4)
    tree = ttk.Treeview(left, columns=('slot', 'size', 'format', 'channels', 'status'), show='tree headings')
    tree.heading('#0', text='Material / texture', anchor='w'); tree.column('#0', width=240)
    for key, title, width in (('slot', 'Shader slot', 130), ('size', 'Size', 100), ('format', 'Format', 90),
                              ('channels', 'Channels used', 170), ('status', 'Status', 150)):
        tree.heading(key, text=title, anchor='w'); tree.column(key, width=width, anchor='w', stretch=key == 'channels')
    scroll = ttk.Scrollbar(left, orient='vertical', command=tree.yview); tree.configure(yscrollcommand=scroll.set)
    scroll.pack(side='right', fill='y'); tree.pack(fill='both', expand=True)
    tree.tag_configure('problem', foreground=t['warn']); tree.tag_configure('material', font=fonts(app)['strong'])
    right = ttk.Frame(body, style='Panel.TFrame', padding=12); body.add(right, weight=2)
    picture = ttk.Label(right, style='Panel.TLabel', anchor='center'); picture.pack(fill='both', expand=True)
    detail = tk.StringVar(value='Select a material or texture.')
    ttk.Label(right, textvariable=detail, style='Panel.TLabel', wraplength=380, justify='left').pack(fill='x', pady=(8, 0))

    results = queue.Queue(); entries = {}; root = app.game_path.get(); source = model.source
    used = sorted({m.material for meshes in model.lods.values() for m in meshes})
    cache = Path(tempfile.gettempdir()) / 'aas_inspector'

    def read_materials():
        try:
            with AssetRepository(app.catalog, root) as repo:
                for index in used:
                    guid = model.materials[index] if index < len(model.materials) else None
                    if guid is None:
                        results.put(('material', index, None, 'Material set unresolved')); continue
                    try:
                        desc = decode_material(repo, guid, source)
                    except Exception as exc:
                        results.put(('material', index, {'guid': guid, 'game_name': guid}, f'{type(exc).__name__}: {exc}')); continue
                    for entry in desc['textures']:
                        try:
                            archive, asset = repo.asset(entry['guid'], source)
                            entry['info'] = texture_info(archive, asset)
                        except Exception as exc:
                            entry['info_error'] = str(exc)
                    results.put(('material', index, desc, None))
        except Exception as exc:
            results.put(('error', f'{type(exc).__name__}: {exc}'))
        results.put(('done',))

    def pump():
        if not window.winfo_exists(): return
        try:
            while True:
                item = results.get_nowait()
                if item[0] == 'material': add_material(*item[1:])
                elif item[0] == 'texture': show_texture(*item[1:])
                elif item[0] == 'error': status.set(item[1])
                elif item[0] == 'done':
                    problems = sum(any('problem' in tree.item(i, 'tags') for i in (m, *tree.get_children(m))) for m in tree.get_children())
                    status.set(f'{len(used)} materials' + (f' · {problems} with problems' if problems else ' · no issues'))
        except queue.Empty:
            pass
        window.after(100, pump)

    def add_material(index, desc, error):
        name = (desc or {}).get('game_name', f'Material {index}').rsplit('/', 1)[-1]
        unsupported = (desc or {}).get('unsupported_inputs', [])
        state = error or (f'{len(unsupported)} input(s) unsupported' if unsupported else 'OK')
        iid = tree.insert('', 'end', text=f'{index}  {name}', values=('', '', '', f"{len((desc or {}).get('textures', []))} textures", state),
                          open=True, tags=('material',) + (('problem',) if error or unsupported else ()))
        entries[iid] = ('material', index, desc, error)
        for entry in (desc or {}).get('textures', []):
            info = entry.get('info') or {}
            role = entry.get('role', 'unknown')
            ok = role in SUPPORTED and not entry.get('info_error')
            child = tree.insert(iid, 'end', text=ROLE_NAMES.get(role, role.replace('_', ' ').capitalize()),
                                values=(entry.get('shader_resource') or f"slot {entry.get('slot')}",
                                        f"{info['width']}×{info['height']}" if info else '—', info.get('format', '—'),
                                        _channels(entry), 'Exported' if ok else (entry.get('info_error') or 'Not exported')),
                                tags=() if ok else ('problem',))
            entries[child] = ('texture', index, entry, None)

    def show_texture(iid, path, error):
        if error: detail.set(error); return
        with Image.open(path) as image:
            image = image.convert('RGBA'); image.thumbnail((380, 380), Image.Resampling.LANCZOS)
        window._photo = ImageTk.PhotoImage(image, master=window)
        picture.configure(image=window._photo)

    def selected(_event=None):
        sel = tree.selection()
        if not sel or sel[0] not in entries: return
        kind, index, data, error = entries[sel[0]]
        app.preview.set_highlight(index)
        if kind == 'material':
            picture.configure(image=''); window._photo = None
            lines = [f"Material {index}: {(data or {}).get('game_name', '')}", f"GUID {(data or {}).get('guid', '')}"]
            if error: lines.append(error)
            unsupported = (data or {}).get('unsupported_inputs', [])
            if unsupported: lines.append('Not exported yet: ' + ', '.join(unsupported))
            for warning in (data or {}).get('warnings', []): lines.append(warning)
            detail.set('\n'.join(lines))
            return
        info = data.get('info') or {}
        detail.set('\n'.join(x for x in (
            f"{ROLE_NAMES.get(data.get('role'), data.get('role'))} · {data.get('shader_resource') or ''}",
            f"{info.get('width', '?')}×{info.get('height', '?')} · {info.get('format', '?')} · {info.get('mips', '?')} mips"
            + (' · sRGB' if info.get('srgb') else ''),
            f"Channels: {_channels(data)}", f"GUID {data['guid']}", data.get('role_evidence', '')) if x))
        target = cache / data['guid']
        def extract():
            try:
                png = target / 'Texture.png'
                if not png.exists():
                    with AssetRepository(app.catalog, root) as repo:
                        archive, asset = repo.asset(data['guid'], source)
                        extracted = extract_texture(archive, asset, target, 'Texture', preview_size=512)
                    png = target / extracted['png']
                results.put(('texture', sel[0], png, None))
            except Exception as exc:
                results.put(('texture', sel[0], None, f"Can't show this texture: {exc}"))
        threading.Thread(target=extract, daemon=True).start()

    def close():
        app.preview.set_highlight(None); app._inspector = None; window.destroy()
    window._close = close

    tree.bind('<<TreeviewSelect>>', selected)
    window.protocol('WM_DELETE_WINDOW', close); window.bind('<Escape>', lambda _e: close())
    threading.Thread(target=read_materials, daemon=True).start()
    pump()
