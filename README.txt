APEX ASSET STUDIO
=================

Extract the ZIP and run ApexAssetStudio.exe. Keep the _internal folder beside it.

GETTING STARTED
1. Your Apex Legends install is detected automatically. If not, set it in
   Settings > Game.
2. Click "Scan library". The first scan takes a while and needs free disk
   space; the status bar shows about how long is left. You can stop it at any time; the next scan picks up where it left off.

BROWSE
- Pick a Legend or weapon on the left, then a skin in the list.
- Click a column heading to sort (Name, Rarity, Model). Ctrl+F searches.
- Filter by rarity, hide skins that can't be exported yet, or tick "Search all
  skins" to search every Legend and weapon at once.
- The 3D preview has soft lighting, a ground shadow and see-through hair and
  glass edges. The playing animation's name and length show in its corner.
- Pictures: tick "Pictures" to see a picture next to each skin. Put store
  cards or renders in the Skin images folder (Settings > Skin images) named
  "<Legend or weapon> - <Skin>.png", e.g. "Wraith - Airship Assassin.png".
  Skins without one get a render the first time you open them.
- Clicking another skin while one is loading cancels the first load. Only the
  most detailed LOD loads at first; other LODs load when you pick them.
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
  Exports when run from source), in a folder per Legend or weapon:
  Exports\Wraith\Wraith - Airship Assassin - Full body\
- Batch: Ctrl-click or Shift-click several skins and press "Export N skins",
  or use "Export whole list..." for everything listed. Each skin's main model
  (full body / world model) is exported with the current options; skins that
  were already exported are skipped, and you can cancel at any time.
- Skin exports also store the skin's lobby lighting (its light colors and
  strengths from the game) for the Blender add-on's "Apex Lobby" preset. "Open last export" opens the result.
- Export > "Animation only" saves just the animation in the preview (a GLB
  with the skeleton and motion plus an .aas.json), in a "<skin> - <animation>"
  folder next to your model exports. Ctrl+Shift+E does the same.
- CAST uses inches; glTF and GLB use metres. All are Y-up.

BLENDER
- Install ApexAssetStudio_Blender_5.2.zip in Blender 4.2 or newer:
  Edit > Preferences > Get Extensions > (menu, top right) Install from Disk,
  or drag the ZIP into Blender. Remove the old version first if you had one.
- File > Import > Apex Asset Studio (or the AAS tab in the 3D view sidebar),
  then pick the .aas.json file. Materials are built on import. To add an
  animation to a model you already imported, select its armature first.
  Blender import needs GLB or glTF in the export.
- Lighting (AAS tab > Lighting): pick a preset and click Apply Lighting:
  3-Point Studio, Rim Light, Dual Color (choose both colors), Sunrise,
  Golden Hour, Daylight, Overcast Soft, Moonlight, Neon, Dramatic and
  High-Key Product. Lights are sized to the model and aimed at it. After
  applying, Intensity, Rotate and Background adjust the rig live, and
  Remove takes it away and restores your previous world. Optional:
  a shadow-catcher floor (Cycles) and a framed camera. "Light on import"
  adds a preset automatically after every model import. "Apex Lobby" uses the
  skin's own lobby light colors from the export.
- Scene & Render: "Scene Ready" sets up the lighting preset, a framed camera
  (Full body 1920x1080 or Portrait 1080x1350) and render settings (Cycles or
  EEVEE, optional transparent background). "Scene ready on import" does this
  for every model you import.
- Turntable: "Make Turntable" spins the model once around its feet (8 s by
  default, lights stay still) and sets the output to an MP4 next to the
  export; "Render Turntable" renders it. "Remove" puts the model back.

SETTINGS
- Themes: Aero Night, Aero Day, Frutiger Aqua, Frutiger Eco, Frutiger Metro,
  Aurora, Sunburst and Sweetheart, each with its own background picture. The
  Aero themes take their accent color from the mascot.
- Text size, high contrast, reduced effects, keyboard shortcuts and the
  mascot image are also in Settings.

ADVANCED
- Assets: every indexed game asset, searchable by name, GUID or container.
- Strings: search readable text inside the game packages.
- Diagnostics: index health, failed packages, and the log of scans, loads and
  errors. Save report... writes it all to a file for bug reports.

LIMITS
- Not supported yet: some animation encodings (datapoint compression, IK,
  procedural motion), blend shapes, and a few skins whose materials can't be
  read (these can be previewed but not exported). Blender materials approximate
  the game's look.
- Unpacked game files are cached (12 GB limit by default). Settings > Storage
  shows the size and lets you change the limit, clear the cache or move it to
  another drive. Clearing is safe; it refills as needed.

License: AGPL-3.0-or-later. See THIRD_PARTY_NOTICES.md.
