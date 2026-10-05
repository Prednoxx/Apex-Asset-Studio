Apex Asset Studio 0.3.1

Extract the ZIP and run ApexAssetStudio.exe. Keep _internal beside it.

1. Select the Apex installation if it isn't detected, then click Scan Library.
2. Choose a model or skin. Drag to rotate; scroll to zoom. LOD 0 is the default.
   Middle/right drag or Shift+left drag pans in both directions. Reset view
   restores the camera.
3. Open Animations and select a sequence. It plays in that window. Use animation
   confirms the choice; Cancel keeps the previous choice. Blend selects a decoded
   variation. Play or scrub the confirmed animation in the main viewport.
4. Export model saves GLB, glTF, CAST, textures and an .aas.json manifest.
   Exports is beside the EXE. Existing asset folders require confirmation before
   replacement. Animation includes the selected clip; All LODs includes every
   decoded detail level. Export animation saves an .aas.json file and its GLB beside it.
   Import either a model or an animation through the same AAS addon. Select the
   model or armature before importing a separate animation. Previous actions are
   retained; no second addon is needed.
5. Install ApexAssetStudio_Blender_5.2.zip in Blender 5.2.2. Open the .aas.json
   through File > Import > Apex Asset Studio or the AAS sidebar. Materials build
   on import. Build / Rebuild Materials and Retry Materials update them in place.

Appearance contains color and layout settings. Advanced View contains internal
names, GUIDs, package versions and dependencies. Diagnostics contains errors.

DDS, original-channel PNGs, texture headers and compressed payloads are retained.
Converted normals are separate files. Material constant buffers, reflected
values, render states and shader bytecode are retained. Unsupported bindings stay in metadata.
Skin maps use physical subsurface scattering. Hair direction maps drive
anisotropic reflections. These are Blender rendering approximations.
CAST uses inches/Y-up; glTF and GLB use metres/Y-up.

Supported animation tracks: aseq 13/14 RLE with rig 7. Datapoint compression,
unknown bone flags, IK, autolayers and procedural motion aren't reconstructed.
Missing material sets disable model export. Blend shapes, additional shader
effects and some format versions aren't supported. Shader appearance hasn't
been compared pixel-for-pixel against the game.

First scans require time and space for decompressed packages. Preview textures use native mip levels and a 96 MiB session cache.
The decoded cache
targets 12 GiB, excluding packages in use.

License: AGPL-3.0-or-later. See THIRD_PARTY_NOTICES.md.
