# Apex Asset Studio

Browse, preview and export Apex Legends character and weapon skins from your own game install.

## Features

- Every skin by Legend or weapon, with search, rarity and season filters and sorting
- 3D preview with textures and animation playback
- Export to GLB, glTF or CAST: all LODs, skeleton, materials, textures (PNG and DDS) and animations
- Batch export and export presets
- Material and texture inspector
- Blender add-on: material setup and controls, animations and poses, recolor swap, lighting presets, turntable renders

## Requirements

- Windows 10 or 11 (64-bit)
- Apex Legends installed (Steam or EA app)
- GPU with OpenGL 2.1 or newer
- Blender 4.2 or newer for the add-on

## Install

1. Extract the ZIP.
2. Run `ApexAssetStudio.exe`. Keep the `_internal` folder next to it.
3. Click **Scan library**. The first scan takes a few minutes and can be stopped and resumed.

The build is not code-signed. If Windows SmartScreen appears, choose **More info › Run anyway**.

**Blender add-on:** Edit › Preferences › Get Extensions › ▾ › Install from Disk, then select `ApexAssetStudio_Blender_5.2.zip`. Import with File › Import › Apex Asset Studio (.aas.json). The add-on needs GLB or glTF in the export.

## Shortcuts

| Key | Action |
| --- | --- |
| Ctrl+1 / 2 / 3 | Library / Advanced / Settings |
| Ctrl+F | Search |
| Ctrl+E / Ctrl+Shift+E | Export model / animation |
| F5 | Scan library |
| Space | Play / pause |
| R | Reset view |
| Arrows, Shift+arrows, + / − | Rotate, pan, zoom (3D view focused) |
| Ctrl+A | Select all listed skins |
| Ctrl + / Ctrl − / Ctrl 0 | Text size |

## Data and privacy

The app makes no network connections and collects no telemetry. All data stays on your PC in `%LOCALAPPDATA%\ApexAssetStudio` (library index, file cache, settings, logs) unless you move the cache in Settings. Delete that folder to remove all app data. Bug reports are only created when you click **Save bug report…**; they are saved locally with your Windows user name removed.

## Limitations

- Some animation encodings (datapoint compression, IK, procedural motion) and blend shapes are not supported.
- A few skins can be previewed but not exported because their materials are not supported yet.
- Blender materials approximate the game's shaders.

## Building from source

Requires Python 3.11 or newer. `build_windows.bat` installs the dependencies, runs the tests, builds the app and writes the release ZIPs to `Releases`.

## Legal

Apex Asset Studio is a fan-made tool. It is not affiliated with, endorsed or sponsored by Electronic Arts Inc. or Respawn Entertainment. Apex Legends is a trademark of Electronic Arts Inc. No game files are included; the app reads the copy of the game installed on your PC. Exported game content remains the property of its owners.

Mascot: Ruka-tan (Ruka Sarashina) from *Rent-A-Girlfriend* (*Kanojo, Okarishimasu*) by Reiji Miyajima, published by Kodansha. The mascot artwork is not covered by the software license.

Licensed under the GNU Affero General Public License v3.0 or later (`LICENSE`). Third-party components and credits: `THIRD_PARTY_NOTICES.md`.
