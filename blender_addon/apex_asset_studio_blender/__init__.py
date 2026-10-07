"""Apex Asset Studio addon."""
bl_info = {  # Legacy addon installer metadata
    "name": "Apex Asset Studio",
    "author": "Prednoxx",
    "version": (0, 6, 0),
    "blender": (4, 2, 0),
    "location": "File > Import, and View3D > Sidebar > AAS",
    "description": "Import models, materials and animations from Apex Asset Studio, with preset lighting",
    "category": "Import-Export",
}

import json
from pathlib import Path

import bpy
from bpy.props import BoolProperty, EnumProperty, FloatProperty, FloatVectorProperty, StringProperty
from bpy.types import Operator, Panel, PropertyGroup

from . import anim, lighting, scene
from .importer import build_manifest_materials, import_manifest, swap_skin
from .materials import set_control


def _live(self, context):
    lighting.update_live(context, self)


def _control(name, attribute):
    return lambda self, context: set_control(name, getattr(self, attribute))


def _pick_action(attribute):
    def update(self, context):
        index = getattr(self, attribute)
        rig = anim.target_rig(context)
        if rig is None or not (0 <= index < len(bpy.data.actions)): return
        anim.play_action(context, rig, bpy.data.actions[index])
    return update


class AASSettings(PropertyGroup):
    manifest_path: StringProperty(name="Export file", subtype="FILE_PATH",
                                  description="The .aas.json file written by Apex Asset Studio")
    lighting_on_import: EnumProperty(name="Light on import", description="Lighting rig to add after each model import",
                                     items=[('NONE', "Don't add lights", "Keep the scene's lighting as it is")] + lighting.PRESET_ITEMS,
                                     default='NONE')
    lighting_preset: EnumProperty(name="Preset", items=lighting.PRESET_ITEMS, default='STUDIO')
    light_intensity: FloatProperty(name="Intensity", default=1.0, min=0.0, soft_max=3.0, update=_live,
                                   description="Multiplies the power of every light in the rig")
    light_rotation: FloatProperty(name="Rotate (°)", default=0.0, min=-180.0, max=180.0, update=_live,
                                  description="Rotate the lighting rig around the model (degrees)")
    world_strength: FloatProperty(name="Background", default=1.0, min=0.0, soft_max=3.0, update=_live,
                                  description="Brightness of the preset's sky / background")
    color_a: FloatVectorProperty(name="Color A", subtype='COLOR', size=3, min=0, max=1, default=(0.12, 0.78, 1.0), update=_live)
    color_b: FloatVectorProperty(name="Color B", subtype='COLOR', size=3, min=0, max=1, default=(1.0, 0.19, 0.5), update=_live)
    add_floor: BoolProperty(name="Shadow catcher floor", default=False,
                            description="Invisible floor that only catches shadows (Cycles)")
    add_camera: BoolProperty(name="Camera", default=False, description="Add a 50 mm camera framing the model")
    scene_ready_on_import: BoolProperty(name="Scene ready on import", default=False,
                                        description="Set up lighting, camera and render settings after import")
    framing: EnumProperty(name="Framing", items=[('BODY', "Full body", "The whole model, 1920×1080"),
                                                 ('PORTRAIT', "Portrait", "Head and shoulders, 1080×1350")], default='BODY')
    render_engine: EnumProperty(name="Engine", items=[('CYCLES', "Cycles", "Path traced: best quality, slower"),
                                                      ('EEVEE', "EEVEE", "Real time: fast previews")], default='CYCLES')
    transparent_background: BoolProperty(name="Transparent background", default=False,
                                         description="Render the model on transparency (PNG) instead of the preset's sky")
    mat_normal: FloatProperty(name="Normal strength", default=1.0, min=0.0, soft_max=3.0, update=_control('Normal Strength', 'mat_normal'),
                              description="Depth of the surface detail from the normal maps")
    mat_specular: FloatProperty(name="Specular", default=1.0, min=0.0, soft_max=3.0, update=_control('Specular', 'mat_specular'),
                                description="Strength of reflections")
    mat_roughness: FloatProperty(name="Roughness", default=1.0, min=0.0, soft_max=3.0, update=_control('Roughness', 'mat_roughness'),
                                 description="Below 1 makes surfaces glossier, above 1 more matte")
    mat_emission: FloatProperty(name="Glow", default=1.0, min=0.0, soft_max=20.0, update=_control('Emission', 'mat_emission'),
                                description="Brightness of glowing parts (emissive textures)")
    mat_skin: FloatProperty(name="Skin scattering", default=1.0, min=0.0, soft_max=2.0, update=_control('Skin', 'mat_skin'),
                            description="Softness of light through skin")
    mat_hue: FloatProperty(name="Hue", default=0.5, min=0.0, max=1.0, update=_control('Hue', 'mat_hue'),
                           description="Shift every color around the color wheel (0.5 = unchanged)")
    mat_saturation: FloatProperty(name="Saturation", default=1.0, min=0.0, soft_max=2.0, update=_control('Saturation', 'mat_saturation'))
    mat_brightness: FloatProperty(name="Brightness", default=1.0, min=0.0, soft_max=2.0, update=_control('Brightness', 'mat_brightness'))
    anim_index: bpy.props.IntProperty(default=-1, update=_pick_action('anim_index'))
    pose_index: bpy.props.IntProperty(default=-1, update=_pick_action('pose_index'))
    turntable_seconds: FloatProperty(name="Length (s)", default=8.0, min=1.0, soft_max=30.0)
    turntable_clockwise: BoolProperty(name="Clockwise", default=False)
    turntable_width: bpy.props.IntProperty(name="Width", default=1920, min=64, max=8192)
    turntable_height: bpy.props.IntProperty(name="Height", default=1080, min=64, max=8192)


def _apply_preset(context, preset):
    return lighting.apply(context, preset, context.scene.aas_settings)


class AAS_OT_Import(Operator):
    """Import model or compatible animation"""
    bl_idname = "aas.import_asset"
    bl_label = "Import Apex Asset"
    bl_options = {"REGISTER", "UNDO"}
    filepath: StringProperty(subtype="FILE_PATH")
    filter_glob: StringProperty(default='*.aas.json', options={'HIDDEN'})

    def execute(self, context):
        settings = context.scene.aas_settings
        path = Path(self.filepath or settings.manifest_path)
        if not path.exists():
            self.report({"ERROR"}, "Select a valid .aas.json export file")
            return {"CANCELLED"}
        try:
            settings.manifest_path = str(path)
            desc, mats = import_manifest(path)
            note = ''
            if desc.get('kind') != 'animation' and settings.scene_ready_on_import:
                note = ' · scene ready: ' + scene.scene_ready(context, settings)
            elif desc.get('kind') != 'animation' and settings.lighting_on_import != 'NONE':
                _apply_preset(context, settings.lighting_on_import)
                note = f" · {lighting.PRESETS[settings.lighting_on_import][0]} lighting"
            if desc.get('kind') == 'animation':
                self.report({"INFO"}, f"Imported animation {desc.get('display_name', '')}")
            else:
                missing = sum(len(json.loads(m.get('aas_missing_textures', '[]'))) for m in mats)
                warn = f" · {missing} texture(s) missing" if missing else ''
                self.report({"WARNING" if missing else "INFO"},
                            f"Imported {desc.get('display_name', 'Apex asset')} · {len(mats)} materials{warn}{note}")
            return {"FINISHED"}
        except Exception as exc:
            self.report({"ERROR"}, str(exc))
            return {"CANCELLED"}

    def invoke(self, context, event):
        context.window_manager.fileselect_add(self)
        return {"RUNNING_MODAL"}


class AAS_OT_Rebuild(Operator):
    """Rebuild exported materials"""
    bl_idname = "aas.rebuild_materials"
    bl_label = "Rebuild Materials"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        path = Path(context.scene.aas_settings.manifest_path)
        if not path.exists():
            self.report({"ERROR"}, "Select an .aas.json export file first")
            return {"CANCELLED"}
        try:
            desc, mats = build_manifest_materials(path)
            self.report({"INFO"}, f"Rebuilt {len(mats)} materials")
            return {"FINISHED"}
        except Exception as exc:
            self.report({"ERROR"}, str(exc))
            return {"CANCELLED"}


class AAS_OT_SwapSkin(Operator):
    """Apply compatible skin materials"""
    bl_idname = "aas.swap_skin"
    bl_label = "Swap Skin (Recolor)…"
    bl_options = {"REGISTER", "UNDO"}
    filepath: StringProperty(subtype="FILE_PATH")
    filter_glob: StringProperty(default='*.aas.json', options={'HIDDEN'})

    def invoke(self, context, event):
        context.window_manager.fileselect_add(self)
        return {"RUNNING_MODAL"}

    def execute(self, context):
        try:
            desc, swapped = swap_skin(context, Path(self.filepath))
        except Exception as exc:
            self.report({"ERROR"}, str(exc)); return {"CANCELLED"}
        context.scene.aas_settings.manifest_path = self.filepath
        self.report({"INFO"}, f"Applied {desc.get('display_name', 'the new skin')} ({swapped} material slots)")
        return {"FINISHED"}


class AAS_OT_ResetControls(Operator):
    """Reset material controls"""
    bl_idname = "aas.reset_material_controls"
    bl_label = "Reset"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        settings = context.scene.aas_settings
        for name in ('mat_normal', 'mat_specular', 'mat_roughness', 'mat_emission', 'mat_skin', 'mat_hue', 'mat_saturation', 'mat_brightness'):
            settings.property_unset(name); setattr(settings, name, getattr(settings, name))
        return {"FINISHED"}


class AAS_OT_ApplyLighting(Operator):
    """Replace AAS lighting preset"""
    bl_idname = "aas.apply_lighting"
    bl_label = "Apply Lighting"
    bl_options = {"REGISTER", "UNDO"}
    preset: EnumProperty(name="Preset", items=lighting.PRESET_ITEMS)

    def invoke(self, context, event):
        self.preset = context.scene.aas_settings.lighting_preset
        return self.execute(context)

    def execute(self, context):
        try:
            count, size = _apply_preset(context, self.preset)
        except Exception as exc:
            self.report({"ERROR"}, str(exc))
            return {"CANCELLED"}
        context.scene.aas_settings.lighting_preset = self.preset
        self.report({"INFO"}, f"{lighting.PRESETS[self.preset][0]}: {count} lights around a {size:.2f} m model")
        return {"FINISHED"}


class AAS_OT_ClearLighting(Operator):
    """Remove lighting; restore previous world"""
    bl_idname = "aas.clear_lighting"
    bl_label = "Remove Lighting"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        lighting.clear(context)
        context.scene.pop('aas_lighting', None)
        return {"FINISHED"}


class AAS_OT_LookThrough(Operator):
    """Enable rendered viewport shading"""
    bl_idname = "aas.view_lighting"
    bl_label = "Preview Lighting"

    def execute(self, context):
        for area in context.screen.areas:
            if area.type == 'VIEW_3D':
                for space in area.spaces:
                    if space.type == 'VIEW_3D': space.shading.type = 'RENDERED'
        return {"FINISHED"}


class AAS_OT_SceneReady(Operator):
    """Set lighting, camera and rendering"""
    bl_idname = "aas.scene_ready"
    bl_label = "Scene Ready"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        try:
            text = scene.scene_ready(context, context.scene.aas_settings)
        except Exception as exc:
            self.report({"ERROR"}, str(exc)); return {"CANCELLED"}
        self.report({"INFO"}, "Scene ready: " + text)
        return {"FINISHED"}


class AAS_OT_FrameCamera(Operator):
    """Frame model with AAS camera"""
    bl_idname = "aas.frame_camera"
    bl_label = "Reframe Camera"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        scene.frame_camera(context, context.scene.aas_settings.framing)
        return {"FINISHED"}


class AAS_OT_Turntable(Operator):
    """Create full model rotation"""
    bl_idname = "aas.turntable"
    bl_label = "Make Turntable"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        settings = context.scene.aas_settings
        try:
            frames = scene.turntable(context, settings.turntable_seconds, settings.turntable_clockwise)
            if not context.scene.camera: scene.frame_camera(context, settings.framing)
            scene.video_output(context, scene.default_video_path(context), settings.turntable_width, settings.turntable_height)
        except Exception as exc:
            self.report({"ERROR"}, str(exc)); return {"CANCELLED"}
        self.report({"INFO"}, f"Turntable: {frames} frames")
        return {"FINISHED"}


class AAS_OT_RenderTurntable(Operator):
    """Render turntable video"""
    bl_idname = "aas.render_turntable"
    bl_label = "Render Turntable"

    def execute(self, context):
        if not bpy.data.objects.get(scene.TURNTABLE):
            self.report({"ERROR"}, "No turntable in the scene"); return {"CANCELLED"}
        bpy.ops.render.render('INVOKE_DEFAULT', animation=True)
        return {"FINISHED"}


class AAS_OT_RemoveTurntable(Operator):
    """Remove turntable rotation"""
    bl_idname = "aas.remove_turntable"
    bl_label = "Remove Turntable"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        scene.remove_turntable(context)
        return {"FINISHED"}


class AAS_UL_actions(bpy.types.UIList):
    """Compatible actions and saved poses"""
    def filter_items(self, context, data, propname):
        actions = getattr(data, propname)
        rig = anim.target_rig(context)
        want_poses = self.list_id == 'poses'
        flags = [self.bitflag_filter_item if anim.compatible(a, rig) and anim.is_pose(a) == want_poses
                 and (not self.filter_name or self.filter_name.lower() in a.name.lower()) else 0 for a in actions]
        order = bpy.types.UI_UL_list.sort_items_by_name(actions, 'name') if self.use_filter_sort_alpha else []
        return flags, order

    def draw_item(self, context, layout, data, item, icon, active_data, active_propname, index):
        if anim.is_pose(item):
            layout.label(text=item.name[len(anim.POSE_PREFIX):] if item.name.startswith(anim.POSE_PREFIX) else item.name, icon='ARMATURE_DATA')
        else:
            start, end = anim.frames(item)
            fps = context.scene.render.fps / context.scene.render.fps_base
            row = layout.row(); row.label(text=item.name, icon='ACTION')
            row.label(text=f"{(end - start + 1) / fps:.1f} s")


class AAS_OT_PlayToggle(Operator):
    """Play or pause animation"""
    bl_idname = "aas.play_toggle"
    bl_label = "Play / Pause"

    def execute(self, context):
        bpy.ops.screen.animation_play()
        return {"FINISHED"}


class AAS_OT_BindPose(Operator):
    """Restore skeleton bind pose"""
    bl_idname = "aas.bind_pose"
    bl_label = "Bind Pose"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        rig = anim.target_rig(context)
        if rig is None:
            self.report({"ERROR"}, "Select the model or its armature"); return {"CANCELLED"}
        anim.bind_pose(rig)
        settings = context.scene.aas_settings
        settings['anim_index'] = -1; settings['pose_index'] = -1
        return {"FINISHED"}


class AAS_OT_SavePose(Operator):
    """Save current pose"""
    bl_idname = "aas.save_pose"
    bl_label = "Save Pose"
    bl_options = {"REGISTER", "UNDO"}
    name: StringProperty(name="Name", default="Pose")

    def invoke(self, context, event):
        rig = anim.target_rig(context)
        action = rig.animation_data.action if rig and rig.animation_data else None
        if action and not anim.is_pose(action): self.name = f"{action.name} @ {context.scene.frame_current}"
        return context.window_manager.invoke_props_dialog(self)

    def execute(self, context):
        rig = anim.target_rig(context)
        if rig is None:
            self.report({"ERROR"}, "Select the model or its armature"); return {"CANCELLED"}
        action, _previous = anim.save_pose(context, rig, self.name.strip() or 'Pose')
        context.scene.aas_settings['pose_index'] = list(bpy.data.actions).index(action)
        self.report({"INFO"}, f"Saved pose {self.name}")
        return {"FINISHED"}


class AAS_OT_DeletePose(Operator):
    """Delete selected saved pose"""
    bl_idname = "aas.delete_pose"
    bl_label = "Delete Pose"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        settings = context.scene.aas_settings; index = settings.pose_index
        if not (0 <= index < len(bpy.data.actions)) or not anim.is_pose(bpy.data.actions[index]):
            self.report({"ERROR"}, "Select a pose"); return {"CANCELLED"}
        action = bpy.data.actions[index]
        rig = anim.target_rig(context)
        if rig and rig.animation_data and rig.animation_data.action == action: anim.bind_pose(rig)
        bpy.data.actions.remove(action); settings['pose_index'] = -1
        return {"FINISHED"}


class AAS_PT_Animation(Panel):
    bl_label = "Animations & Poses"
    bl_idname = "AAS_PT_animation"
    bl_parent_id = "AAS_PT_main"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "AAS"

    def draw(self, context):
        layout = self.layout
        settings = context.scene.aas_settings
        rig = anim.target_rig(context)
        if rig is None:
            layout.label(text="Import a model or select its armature", icon='INFO'); return
        layout.label(text=rig.name, icon='OUTLINER_OB_ARMATURE')
        layout.label(text="Animations")
        layout.template_list("AAS_UL_actions", "animations", bpy.data, "actions", settings, "anim_index", rows=4)
        row = layout.row(align=True)
        playing = context.screen.is_animation_playing if context.screen else False
        row.operator("aas.play_toggle", text="Pause" if playing else "Play", icon='PAUSE' if playing else 'PLAY')
        row.operator("aas.bind_pose", icon='ARMATURE_DATA')
        layout.operator("aas.import_asset", text="Add animation (.aas.json)…", icon='IMPORT')
        layout.separator()
        layout.label(text="Poses")
        layout.template_list("AAS_UL_actions", "poses", bpy.data, "actions", settings, "pose_index", rows=3)
        row = layout.row(align=True)
        row.operator("aas.save_pose", icon='ADD')
        row.operator("aas.delete_pose", icon='REMOVE', text="Delete")


class AAS_PT_Main(Panel):
    bl_label = "Apex Asset Studio"
    bl_idname = "AAS_PT_main"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "AAS"

    def draw(self, context):
        layout = self.layout
        settings = context.scene.aas_settings
        layout.operator("aas.import_asset", icon="IMPORT")
        layout.prop(settings, "manifest_path", text="")
        layout.prop(settings, "lighting_on_import")
        layout.prop(settings, "scene_ready_on_import")


class AAS_PT_Materials(Panel):
    bl_label = "Materials"
    bl_idname = "AAS_PT_materials"
    bl_parent_id = "AAS_PT_main"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "AAS"

    def draw(self, context):
        layout = self.layout
        mats = [m for m in bpy.data.materials if m.get('aas_guid')]
        missing = [m for m in mats if m.get('aas_resolution_status') == 'missing_textures']
        col = layout.column(align=True)
        col.label(text=f"{len(mats)} Apex materials in this file", icon='MATERIAL')
        if missing:
            col.label(text=f"{len(missing)} with missing textures:", icon='ERROR')
            for mat in missing[:6]: col.label(text="   " + mat.name)
        if any(m.get('aas_shader_revision', 0) < 3 for m in mats):
            layout.label(text="Rebuild materials to enable controls", icon='INFO')
        layout.operator("aas.rebuild_materials", icon="FILE_REFRESH")
        layout.operator("aas.swap_skin", icon="BRUSHES_ALL")
        settings = context.scene.aas_settings
        col = layout.column(align=True)
        for name in ('mat_normal', 'mat_specular', 'mat_roughness', 'mat_emission', 'mat_skin'):
            col.prop(settings, name, slider=True)
        col = layout.column(align=True); col.label(text="Color grade")
        for name in ('mat_hue', 'mat_saturation', 'mat_brightness'):
            col.prop(settings, name, slider=True)
        layout.operator("aas.reset_material_controls", icon='LOOP_BACK')


class AAS_PT_Lighting(Panel):
    bl_label = "Lighting"
    bl_idname = "AAS_PT_lighting"
    bl_parent_id = "AAS_PT_main"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "AAS"

    def draw(self, context):
        layout = self.layout
        settings = context.scene.aas_settings
        layout.prop(settings, "lighting_preset", text="")
        description = lighting.PRESETS[settings.lighting_preset][1]
        box = layout.box(); box.scale_y = .8
        for line in _wrap(description, 34): box.label(text=line)
        if settings.lighting_preset == 'DUAL':
            row = layout.row(align=True); row.prop(settings, "color_a", text=""); row.prop(settings, "color_b", text="")
        row = layout.row(align=True)
        row.prop(settings, "add_floor", toggle=True, icon='MESH_PLANE')
        row.prop(settings, "add_camera", toggle=True, icon='CAMERA_DATA')
        layout.operator("aas.apply_lighting", icon='LIGHT_AREA')
        active = context.scene.get('aas_lighting')
        if active:
            col = layout.column(align=True)
            col.label(text=f"Active: {lighting.preset_name(active)}", icon='CHECKMARK')
            col.prop(settings, "light_intensity", slider=True)
            col.prop(settings, "light_rotation")
            col.prop(settings, "world_strength", slider=True)
            row = layout.row(align=True)
            row.operator("aas.view_lighting", icon='SHADING_RENDERED')
            row.operator("aas.clear_lighting", icon='X', text="Remove")


class AAS_PT_Scene(Panel):
    bl_label = "Scene & Render"
    bl_idname = "AAS_PT_scene"
    bl_parent_id = "AAS_PT_main"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "AAS"

    def draw(self, context):
        layout = self.layout
        settings = context.scene.aas_settings
        row = layout.row(align=True); row.prop(settings, "framing", expand=True)
        row = layout.row(align=True); row.prop(settings, "render_engine", expand=True)
        layout.prop(settings, "transparent_background")
        layout.operator("aas.scene_ready", icon='SCENE')
        layout.operator("aas.frame_camera", icon='CAMERA_DATA')
        box = layout.box()
        box.label(text="Turntable", icon='FILE_MOVIE')
        col = box.column(align=True)
        col.prop(settings, "turntable_seconds")
        row = col.row(align=True); row.prop(settings, "turntable_width"); row.prop(settings, "turntable_height")
        col.prop(settings, "turntable_clockwise")
        box.operator("aas.turntable", icon='DRIVER_ROTATIONAL_DIFFERENCE')
        if bpy.data.objects.get(scene.TURNTABLE):
            row = box.row(align=True)
            row.operator("aas.render_turntable", icon='RENDER_ANIMATION')
            row.operator("aas.remove_turntable", icon='X', text="Remove")


def _wrap(text, width):
    words, line, out = text.split(), '', []
    for word in words:
        if len(line) + len(word) + 1 > width and line: out.append(line); line = word
        else: line = f'{line} {word}'.strip()
    if line: out.append(line)
    return out


classes = (AASSettings, AAS_OT_Import, AAS_OT_Rebuild, AAS_OT_ApplyLighting, AAS_OT_ClearLighting, AAS_OT_LookThrough,
           AAS_OT_SceneReady, AAS_OT_FrameCamera, AAS_OT_Turntable, AAS_OT_RenderTurntable, AAS_OT_RemoveTurntable,
           AAS_OT_SwapSkin, AAS_OT_ResetControls, AAS_UL_actions, AAS_OT_PlayToggle, AAS_OT_BindPose, AAS_OT_SavePose, AAS_OT_DeletePose,
           AAS_PT_Main, AAS_PT_Animation, AAS_PT_Materials, AAS_PT_Lighting, AAS_PT_Scene)


def menu_func_import(self, context):
    self.layout.operator(AAS_OT_Import.bl_idname, text="Apex Asset Studio (.aas.json)")


def register():
    for cls in classes:
        bpy.utils.register_class(cls)
    bpy.types.Scene.aas_settings = bpy.props.PointerProperty(type=AASSettings)
    bpy.types.TOPBAR_MT_file_import.append(menu_func_import)


def unregister():
    bpy.types.TOPBAR_MT_file_import.remove(menu_func_import)
    del bpy.types.Scene.aas_settings
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
