APEX ASSET STUDIO
=================

Extract the ZIP and run ApexAssetStudio.exe. Keep the _internal folder beside it.

GETTING STARTED
1. Your Apex Legends install is detected automatically. If not, set it in
   Settings > Game.
2. Click "Scan library". The first scan takes a while and needs free disk
   space. You can stop it at any time; the next scan picks up where it left off.

BROWSE
- Pick a Legend or weapon on the left, then a skin in the list.
- Click a column heading to sort (Name, Rarity, Model). Ctrl+F searches.
- In the preview: drag to rotate, Shift-drag or right-drag to pan, scroll to
  zoom, R to reset the view.

ANIMATIONS
- "Browse animations" lists the clips that belong to the model. Pick one to
  play it, then "Use animation". "Variation" switches between versions of the
  same clip. Space plays and pauses.

EXPORT
- Choose formats: GLB, glTF and/or CAST. "All detail levels" also exports the
  lower-detail LOD meshes. "Include animation" adds the chosen clip.
- Exports go to the Exports folder (beside the EXE, or the master folder's
  Exports when run from source). "Open last export" opens the result.
- "Export animation" saves just the animation (an .aas.json plus a GLB).
- CAST uses inches; glTF and GLB use metres. All are Y-up.

BLENDER
- Install ApexAssetStudio_Blender_5.2.zip in Blender 5.2, then use
  File > Import > Apex Asset Studio (or the AAS sidebar) and pick the
  .aas.json file. Materials are built on import. To add an animation to a model
  you already imported, select its armature first. Blender import needs GLB or
  glTF in the export.

SETTINGS
- Theme, text size, high contrast, reduced effects, keyboard shortcuts and the
  mascot image are all in Settings.

LIMITS
- Not supported yet: some animation encodings (datapoint compression, IK,
  procedural motion), blend shapes, and a few skins whose materials can't be
  read (these can be previewed but not exported). Blender materials approximate
  the game's look.
- Decoded game packages are cached in %LOCALAPPDATA%\ApexAssetStudio\decoded_cache
  (up to about 12 GB). Deleting that folder is safe; it is rebuilt when needed.

License: AGPL-3.0-or-later. See THIRD_PARTY_NOTICES.md.
