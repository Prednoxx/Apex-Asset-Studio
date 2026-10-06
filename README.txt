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
- Sort by: Name, Rarity, Season (newest or oldest first) or Source, from the
  sort list above the skins or by clicking a column heading. Remembered.
  Ctrl+F searches.
- Season and Source (Battle Pass, Collection Event, Store, Bundle, Base...)
  come from the game's own data. Skins the game doesn't tag show "—" and sort
  last. Filter by season, by rarity, hide skins that can't be exported yet, or
  tick "Search all skins" to search every Legend and weapon at once.
- Materials... (above the preview) lists every material and texture the model
  uses: what each texture is for, the shader slot it feeds, size, format, the
  channels used, and anything that couldn't be read. Pick a material to
  highlight it in the preview (the rest go grey), or a texture to see it.
- The 3D preview has soft lighting, a ground shadow and see-through hair and
  glass edges. The playing animation's name and length show in its corner.
- Clicking another skin while one is loading cancels the first load. Only the
  most detailed LOD loads at first; other LODs load when you pick them.
- In the preview: drag to rotate, Shift-drag or right-drag to pan, scroll to
  zoom, R to reset the view. With the keyboard: Tab to the preview (it gets a
  colored outline), then arrow keys rotate, Shift+arrows pan and + / - zoom.

ANIMATIONS
- "Browse animations" lists the clips that belong to the model. Pick one to
  play it, then "Use animation". "Variation" switches between versions of the
  same clip. Space plays and pauses.

EXPORT
- Choose formats: GLB, glTF and/or CAST. "All detail levels" also exports the
  lower-detail LOD meshes. "Include animation" adds the chosen clip.
- Presets: pick one from "Preset" (Blender, Quick look, CAST tools,
  Everything) to set formats and options in one go. "Save..." stores your
  current options as your own preset; "Delete" removes it. The list shows
  "Custom" when your options don't match any preset.
- Exports go to the Exports folder beside the EXE (the master folder's
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
- Animations & Poses (AAS tab): every animation that fits the selected
  model, with its length. Click one to play it (the frame range fits it), or
  Play / Pause. Poses: "Save Pose" keeps the current pose (any frame, or your
  own posing) under a name; click a pose to apply it, "Bind Pose" goes back
  to the default stance. Poses are saved in the .blend.
- Materials (AAS tab): sliders for Normal strength, Specular, Roughness, Glow,
  Skin scattering, Hue, Saturation and Brightness change every material of
  the model at once; Reset puts them back. "Swap Skin (Recolor)..." switches
  the model to another skin of the same model (pick that skin's .aas.json
  export) without re-importing, keeping its pose, animation and lighting.
  Skins with a different model need a normal import.
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
  Aero themes take their accent color from Ruka-tan's ribbon (can be
  turned off in Settings > Mascot).
- Text size, high contrast, reduced effects and keyboard shortcuts are also
  in Settings. The mascot is Ruka-tan.

KEYBOARD AND ACCESSIBILITY
- Everything can be reached with Tab / Shift+Tab; hovering or tabbing to a
  control shows its hint. Down arrow in the search box jumps into the list;
  Ctrl+A in the list selects every listed skin (for a batch export).
- Theme cards: Tab to a card and press Enter or Space to use it.
- Ctrl+1/2/3 switch pages, Ctrl+F searches, F5 scans, Ctrl+E exports,
  Ctrl + / Ctrl - change the text size, Space plays or pauses.
- Text meets WCAG AA contrast (AAA with High contrast) in every theme,
  including rarity colors, warnings, button labels and messages drawn over
  the background pictures.

ADVANCED
- Assets: every indexed game asset, searchable by name, GUID or container.
- Strings: search readable text inside the game packages.
- Diagnostics: index health, failed packages, and the log of scans, loads and
  errors. "Problems" lists skins that failed to load or export and why.
  "Save bug report..." writes a ZIP with the log, problems and settings to
  attach to a bug report.
- Everything is also logged to logs\app.log in the app's data folder. If the
  app closed unexpectedly, it says so at the next start and cleans up any
  half-finished export.

LIMITS
- Not supported yet: some animation encodings (datapoint compression, IK,
  procedural motion), blend shapes, and a few skins whose materials can't be
  read (these can be previewed but not exported). Blender materials approximate
  the game's look.
- Unpacked game files are cached (12 GB limit by default). Settings > Storage
  shows the size and lets you change the limit, clear the cache or move it to
  another drive. Clearing is safe; it refills as needed.

License: AGPL-3.0-or-later. See THIRD_PARTY_NOTICES.md.
