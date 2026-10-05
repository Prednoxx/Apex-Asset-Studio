# Apex Asset Studio 0.3.1

Validation date: October 4, 2026.

The desktop uses a native OpenGL viewport. Airship Assassin at LOD 0 has 41,806
vertices, 66,541 triangles and 174 bones. The Intel Arc B580 measured approximately
1.4-1.7 ms per textured draw and 14-19 ms per animated pose. Preview textures use actual
material bindings; preview images are limited to 2048 pixels. Export textures
retain their native dimensions and original payloads.

Native aseq 13/14 RLE tracks decode against declared rig 7 links. The decoder
handles sectioned tracks, streaming, signed curves, packed quaternions and root
movement. It rejects unsupported compression and bone flags. Model-specific
unanimated bones retain their bind transforms. Playback, scrubbing, blend
selection and separate or combined CAST/glTF/GLB export are available.

The 98-frame Idle Pistol Akimbo clip and 24 additional declared Wraith/core clips
decoded, including movement and execution-victim tracks. Skeleton bind matrices
matched native inverse binds within 0.000015. Pose viewing exposed an authoring
basis mismatch, which was corrected before the final export checks.

Exports use stable folders under Exports beside the executable. Replacement
requires confirmation. Material names identify native material parts; texture
names identify reflected roles. Original GUIDs, RPaks, texture payloads, material
headers, shader bytecode and constant buffers remain in metadata or original files.
Non-finite unused constant values retain their raw bytes and use JSON null.

The Blender shader uses diffuse and GGX lobes with the decoded base color,
normal, specular, gloss, AO and cavity bindings. Gloss converts through the
reflected one-minus channel. Alpha and emission connect only when decoded.
It contains no Principled node. First import, rebuild and retry produce one
image per supported role. Unsupported texture bindings remain in the manifest.

23 unit tests passed. Airship Assassin's five LODs passed Khronos GLB/glTF
validation with zero errors or warnings. The independent CAST reader checked
animation curve lengths and rate. Blender 5.2.2 imported six meshes and 174 bones;
rebuild/retry preserved object count. The user's TestShaderExport scene was
prepared with all six material sets updated and its objects preserved.

The previous 99-configuration Wraith audit and 55-model sample remain separate
geometry evidence. Five Wraith material configurations remain unresolved:
Apex Voidshifter's three levels, Toxic Rush and Void Veil. Their geometry can be
previewed, but model export remains disabled. The complete installed catalog
has 4,583 RPaks, 953,264 raw rows, 5,763 cosmetics and 3,304,971 dependencies;
142 settings layouts remain unresolved. This revision did not repeat the scan.

Still unsupported: datapoint animation compression, unknown bone flags, IK,
autolayers, procedural motion, blend shapes, additional shader effects and some
format versions. Game-to-Blender pixel parity is unverified. Cosmetic thumbnails
remain unresolved. No game assets are bundled in the application ZIP.

Validation reports and pre-change backups are under the working chat's work
directory. Portable application, matching source and addon ZIPs are in outputs.

## Shader revision 2

The reflection lobe now uses multiscatter GGX with colored Fresnel from the
decoded specular data. Diffuse roughness follows the decoded gloss map.
Skin profile maps drive a Blender Random Walk Skin approximation with the
decoded scattering blend amount and a documented 5 mm radius scale.

The hair decoder recognizes an R-channel texture gather with wrapped angular
interpolation, turns-to-radians conversion and signed tangent sine/cosine.
It exports an additional tangent PNG while preserving the angle PNG and DDS.
Hair roughness axes use the decoded stretch constant and gloss map; Blender's
anisotropy range limits very extreme source ratios.

Material snapshot blend states are decoded and preserved. Eye overlays use
their actual opacity and packed alpha; reflected specular/gloss constants
provide inputs when no corresponding texture is present. Packed image channels
remain independent. All 29 Airship texture bindings now build in Blender.

Controlled before/after portrait renders show the skin, hair, eye overlays and
outfit materials. Geometry and animation validation remain separate checks;
the shader is a Blender rendering approximation, not verified game pixel parity.

## Workflow revision

Animation selection now loads and plays in the selection window. Use animation
commits the decoded clip; Cancel preserves the previous choice. The dialog has
its own scrubber, blend control and metadata view. Pan uses middle/right drag
or Shift+left drag; Reset view restores the camera.

Separate animation export defaults to an AAS manifest and GLB. The existing
addon imports it onto a selected compatible armature, verifies bone names,
parents and rest matrices, retains the previous action, and removes the
temporary imported skeleton. No additional importer is required. Combined
model exports already embed the selected animation in GLB/glTF.

Preview extraction decodes one native mip and skips DDS/original-payload writes.
Textures upload progressively. A bounded 96 MiB cache reuses ready pixels and
checks source RPak/StarPak sizes and timestamps. Full export extraction retains
all original mip data. GUI checks verified playback, confirm/cancel and pan;
Blender checks verified no duplicate geometry and preservation of the old action.
