# Apex Asset Studio

A Windows app for browsing and exporting Apex Legends character and weapon skins: models, skeletons, materials, textures and animations.

- **Browse** every skin by Legend or weapon, preview it in 3D with textures, and play its animations.
- **Export** to GLB, glTF and/or CAST, with all detail levels (LODs), textures (DDS, PNG and the original game data) and an `.aas.json` manifest.
- **Import into Blender 5.2** with the bundled add-on, which rebuilds the materials.

No game files are included. The app reads your own Apex Legends install.

## Run

- **Portable build:** extract the ZIP and run `ApexAssetStudio.exe`. Keep the `_internal` folder beside it.
- **From source:** run `Run Apex Asset Studio.bat` in the master folder (or `RUN_TEST.bat` here). The first run sets up Python.

See `README.txt` for the step-by-step guide.

## Develop

| Task | How |
| --- | --- |
| Run tests | `RUN_TESTS.bat` |
| Build the portable app (and installer, if Inno Setup is installed) | `build_windows.bat` (runs the tests first) |
| Package release ZIPs | `python package_release.py --destination <folder>` |
| Version number | `apex_asset_studio/__init__.py` (the only place it is set) |

Code layout: `rpak/` reads game packages, `export/` writes GLB/glTF/CAST, `blender_addon/` is the Blender importer, and `ui/` is the desktop app:

| `ui/` file | Holds |
| --- | --- |
| `app.py` | Main window: header, status bar, scan, event pump, session |
| `library.py` | Library page: list, 3D preview, model/LOD loading, animation playback, export |
| `animations.py` | The animation browser dialog |
| `advanced.py` | Advanced page: asset explorer, string search, diagnostics |
| `settings.py` | Settings page and applying the appearance |
| `appearance.py` | Themes, color tokens, saved preferences, ttk styling |
| `gloss.py` | Generated art: glossy controls, glass, and each theme's backdrop |
| `widgets.py` | Header bar, section headings, primary button |
| `preview.py` | OpenGL viewport |

## Known limits

Some animation encodings (datapoint compression, IK, procedural motion) and blend shapes are not supported. A few skins whose material sets can't be read yet can be previewed but not exported. Blender materials approximate the game's shaders.

License: AGPL-3.0-or-later. Third-party credits: `THIRD_PARTY_NOTICES.md`.
