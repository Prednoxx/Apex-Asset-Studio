# Third-party / format research notices

Apex Asset Studio uses public reverse-engineering work to interoperate with Respawn RPak/StarPak data.

- reSource Xtractor (RSX): https://github.com/r-ex/rsx — AGPL-3.0. The RTech decoder table/behavior in this test tree is derived from/publicly cross-checked against RSX, so this project is distributed under AGPL-3.0-or-later.
- pyooz: https://github.com/zao/pyooz — GPL-3.0-or-later. The packaged application bundles this open-source Python binding for Oodle-compatible decompression.
- ooz: https://github.com/powzix/ooz — GPL-3.0-or-later. pyooz wraps the open-source ooz decompressor.
- CAST format ecosystem: https://github.com/dtzxporter/cast
- Pillow: https://github.com/python-pillow/Pillow — HPND license; preview rendering and PNG output.
- texture2ddecoder: https://github.com/K0lb3/texture2ddecoder — MIT license; block texture decoding.
- PyInstaller: https://github.com/pyinstaller/pyinstaller — GPL with bootloader exception; standalone Windows packaging.
- NumPy: https://numpy.org — BSD-3-Clause; animation transforms and skinning.
- PyOpenGL: https://github.com/mcfletch/pyopengl — BSD-style license; GPU rendering.
- pyopengltk: https://github.com/jonwright/pyopengltk — BSD-2-Clause; Tk OpenGL context.
- Shader references reviewed: https://github.com/Kaiserouo/Apex-Legends-Titanfall-Auto-Shader-Blender-Addon and https://github.com/Gl2imm/Apex-Toolbox. Their Blender node groups and game assets are not bundled.
- DirectX Shader Compiler: https://github.com/microsoft/DirectXShaderCompiler — DXC 1.9.2609 compiler/reflection binaries. Bundled notices are in third_party/dxc. Used only for shader reflection; RPak/StarPak extraction stays in Apex Asset Studio.

No proprietary Oodle DLL is bundled by Apex Asset Studio. If pyooz is unavailable, the program can fall back to a compatible Oodle DLL already present on the user's system.

Apex Legends and related names/assets are property of their respective owners. This tool contains no Apex game assets.

Asuka artwork: Evangelion. Original artist uncredited; character and artwork rights remain with their respective owners. The image is excluded from the application's AGPL license. File provenance is in apex_asset_studio/resources/ARTWORK_SOURCE.md. Apex Asset Studio is not affiliated with Evangelion or khara.
