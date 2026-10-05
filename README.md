# Apex Asset Studio

A Windows model browser and exporter for Apex Legends. Exports GLB, glTF and CAST with skeletons, weights, UVs, normals, tangents, LODs and material assignments. Texture output includes DDS, PNG and original game payloads.

Extract the portable ZIP and run ApexAssetStudio.exe. See README.txt for scanning, export and Blender import instructions. The Blender addon supports Blender 5.2.2.

The desktop preview is untextured. Animation playback/export, full shader reproduction and blend shapes are not supported. Unsupported formats produce an error; missing material sets disable export.

For development, run RUN_TEST.bat. Run build_windows.bat to build the portable application. RPak and StarPak handling is in apex_asset_studio/rpak. Dependencies and artwork credits are listed in THIRD_PARTY_NOTICES.md.
