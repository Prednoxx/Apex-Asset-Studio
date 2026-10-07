# Third-party notices

Apex Asset Studio, copyright (C) 2026 Prednoxx, is licensed under the GNU Affero General Public License v3.0 or later. It includes or is built with the components below, under their own licenses. License texts for the bundled packages are in the `third_party_licenses` folder of the release.

## Bundled software

| Component | License | Source |
| --- | --- | --- |
| Python | PSF-2.0 | https://www.python.org |
| Tcl/Tk | Tcl/Tk license (BSD-style) | https://www.tcl.tk |
| NumPy | BSD-3-Clause | https://numpy.org |
| Pillow | MIT-CMU (HPND) | https://github.com/python-pillow/Pillow |
| PyOpenGL | BSD-3-Clause | https://github.com/mcfletch/pyopengl |
| pyopengltk | MIT | https://github.com/jonwright/pyopengltk |
| texture2ddecoder | MIT | https://github.com/K0lb3/texture2ddecoder |
| pyooz | GPL-3.0-or-later | https://github.com/zao/pyooz |
| ooz (wrapped by pyooz) | GPL-3.0-or-later | https://github.com/powzix/ooz |
| DirectX Shader Compiler 1.9.2609 (`dxc.exe`, `dxcompiler.dll`) | See `LICENSE-LLVM.txt`, `LICENSE-MS.txt`, `LICENCE-MIT.txt` in `third_party/dxc` | https://github.com/microsoft/DirectXShaderCompiler |
| PyInstaller bootloader | GPL-2.0 with bootloader exception | https://github.com/pyinstaller/pyinstaller |

No proprietary Oodle library is included. If pyooz is unavailable, the app can use a compatible Oodle DLL already present on the system.

## Format research

- reSource Xtractor (RSX), AGPL-3.0: https://github.com/r-ex/rsx. The RTech decoding is derived from and cross-checked against RSX, which is why this project is AGPL-3.0-or-later.
- CAST format: https://github.com/dtzxporter/cast
- Shader research references (nothing from these projects is bundled): https://github.com/Kaiserouo/Apex-Legends-Titanfall-Auto-Shader-Blender-Addon, https://github.com/Gl2imm/Apex-Toolbox

## Fonts

No font files are included. The app uses fonts installed with Windows (Segoe UI, Trebuchet MS, Consolas or Cascadia Mono).

## Artwork

- Mascot: Lumi-tan, from "Free Anime Girl Character Sprite" by blackbunney (https://blackbunney.itch.io/free-anime-girl-character-sprite). Licensed for personal and commercial projects; the sprite may not be resold on its own. It is not covered by this project's license and may not be extracted and redistributed as a standalone asset. Files: `resources/lumi.webp`, `resources/lumi_avatar.png` (cropped, on a gradient background), `resources/app_icon.ico`.
- Theme backgrounds (`resources/backgrounds`): royalty-free images supplied by the author, resized. `metro.jpg` is "Glass-covered facade" from Unsplash (Unsplash License). The center of `aurora.jpg` was retouched.

## Trademarks

Apex Legends is a trademark of Electronic Arts Inc. Apex Asset Studio is not affiliated with, endorsed or sponsored by Electronic Arts Inc. or Respawn Entertainment, and contains no game files.
