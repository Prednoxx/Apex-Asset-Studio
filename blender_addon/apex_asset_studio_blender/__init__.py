"""Apex Asset Studio for Blender: import Apex Asset Studio exports (.aas.json) with their materials and animations,
and light them with one-click preset rigs."""
bl_info = {  # used by the legacy add-on installer; Blender 4.2+ reads blender_manifest.toml instead
    "name": "Apex Asset Studio",
    "author": "Apex Asset Studio",
    "version": (0, 4, 0),
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

from . import lighting
from .importer import build_manifest_materials, import_manifest


def _live(self, context):
    lighting.update_live(context, self)


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
                                  description="Swing the whole rig around the model, in degrees")
    world_strength: FloatProperty(name="Background", default=1.0, min=0.0, soft_max=3.0, update=_live,
                                  description="Brightness of the preset's sky / background")
    color_a: FloatVectorProperty(name="Color A", subtype='COLOR', size=3, min=0, max=1, default=(0.12, 0.78, 1.0), update=_live)
    color_b: FloatVectorProperty(name="Color B", subtype='COLOR', size=3, min=0, max=1, default=(1.0, 0.19, 0.5), update=_live)
    add_floor: BoolProperty(name="Shadow catcher floor", default=False,
                            description="Invisible floor that only catches shadows (Cycles)")
    add_camera: BoolProperty(name="Camera", default=False, description="Add a 50 mm camera framing the model from the front")


def _apply_preset(context, preset):
    return lighting.apply(context, preset, context.scene.aas_settings)


class AAS_OT_Import(Operator):
    """Import an Apex Asset Studio export with its materials (or an animation onto the selected model)"""
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
            if desc.get('kind') != 'animation' and settings.lighting_on_import != 'NONE':
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
    """Rebuild every material from the export file (picks up textures that were missing before)"""
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


class AAS_OT_ApplyLighting(Operator):
    """Light the model with the chosen preset (replaces any previous AAS lighting)"""
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
    """Remove the AAS lights, floor and camera and restore the previous world"""
    bl_idname = "aas.clear_lighting"
    bl_label = "Remove Lighting"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        lighting.clear(context)
        context.scene.pop('aas_lighting', None)
        return {"FINISHED"}


class AAS_OT_LookThrough(Operator):
    """Switch the 3D viewports to Rendered shading to see the lighting"""
    bl_idname = "aas.view_lighting"
    bl_label = "Preview Lighting"

    def execute(self, context):
        for area in context.screen.areas:
            if area.type == 'VIEW_3D':
                for space in area.spaces:
                    if space.type == 'VIEW_3D': space.shading.type = 'RENDERED'
        return {"FINISHED"}


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


class AAS_PT_Materials(Panel):
    bl_label = "Materials"
    bl_idname = "AAS_PT_materials"
    bl_parent_id = "AAS_PT_main"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "AAS"
    bl_options = {'DEFAULT_CLOSED'}

    def draw(self, context):
        layout = self.layout
        mats = [m for m in bpy.data.materials if m.get('aas_guid')]
        missing = [m for m in mats if m.get('aas_resolution_status') == 'missing_textures']
        col = layout.column(align=True)
        col.label(text=f"{len(mats)} Apex materials in this file", icon='MATERIAL')
        if missing:
            col.label(text=f"{len(missing)} with missing textures:", icon='ERROR')
            for mat in missing[:6]: col.label(text="   " + mat.name)
        layout.operator("aas.rebuild_materials", icon="FILE_REFRESH")


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
            col.label(text=f"Active: {lighting.PRESETS.get(active, ('Custom',))[0]}", icon='CHECKMARK')
            col.prop(settings, "light_intensity", slider=True)
            col.prop(settings, "light_rotation")
            col.prop(settings, "world_strength", slider=True)
            row = layout.row(align=True)
            row.operator("aas.view_lighting", icon='SHADING_RENDERED')
            row.operator("aas.clear_lighting", icon='X', text="Remove")


def _wrap(text, width):
    words, line, out = text.split(), '', []
    for word in words:
        if len(line) + len(word) + 1 > width and line: out.append(line); line = word
        else: line = f'{line} {word}'.strip()
    if line: out.append(line)
    return out


classes = (AASSettings, AAS_OT_Import, AAS_OT_Rebuild, AAS_OT_ApplyLighting, AAS_OT_ClearLighting, AAS_OT_LookThrough,
           AAS_PT_Main, AAS_PT_Materials, AAS_PT_Lighting)


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
