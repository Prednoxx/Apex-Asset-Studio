"""'Scene ready' (camera, render settings and lighting in one click) and turntables.

Scene ready frames the model with a camera (full body or a head-and-shoulders portrait), applies the chosen
lighting preset and sets sensible render settings. A turntable spins the model once around its feet over the
chosen length while the lights stay put, and sets the output to an MP4 next to the export."""
import math
from pathlib import Path

import bpy
from mathutils import Vector

from . import lighting

CAMERA = 'AAS Camera'
TURNTABLE = 'AAS Turntable'


def _head_point(objects):
    """World position of the head bone (the game's skeletons name it like 'def_c_head'), if there is one."""
    rigs = {m.object for o in objects if o.type == 'MESH' for m in o.modifiers if m.type == 'ARMATURE' and m.object}
    for rig in rigs:
        bone = next((b for b in rig.data.bones if 'head' in b.name.lower() and 'headset' not in b.name.lower()), None)
        if bone: return rig.matrix_world @ bone.head_local
    return None


def frame_camera(context, framing='BODY', lens=50.0):
    """Create or move the AAS camera to frame the model. Returns the camera object."""
    objects = lighting.model_objects(context)
    center, size, floor = lighting.bounds(objects)
    scene = context.scene
    camera = bpy.data.objects.get(CAMERA)
    if camera is None:
        camera = bpy.data.objects.new(CAMERA, bpy.data.cameras.new(CAMERA))
        lighting._collection(context).objects.link(camera)
    camera.constraints.clear()
    if 'aas_rig' in camera: del camera['aas_rig']  # owned by Scene ready now, not by the lighting rig
    camera.data.lens = lens; camera.data.sensor_fit = 'AUTO'
    width, height = scene.render.resolution_x, scene.render.resolution_y
    if framing == 'PORTRAIT':
        head = _head_point(objects) or Vector((center.x, center.y, floor + size * .9))
        aim = head + Vector((0, 0, size * .02)); extent = size * .32  # head and shoulders
    else:
        aim = Vector((center.x, center.y, floor + size / 2)); extent = size * 1.12  # whole body with a margin
    # vertical field of view for the current aspect (AUTO fit uses the longer side for the 36 mm sensor)
    sensor = camera.data.sensor_width
    vertical = sensor if height >= width else sensor * height / width
    fov = 2 * math.atan(vertical / 2 / lens)
    distance = (extent / 2) / math.tan(fov / 2)
    camera.location = aim + Vector((0, -distance, extent * .08))  # in front of the character (it faces -Y)
    direction = aim - camera.location
    camera.rotation_euler = direction.to_track_quat('-Z', 'Y').to_euler()
    scene.camera = camera
    return camera


def render_settings(context, engine='CYCLES', transparent=False, width=1920, height=1080):
    scene = context.scene
    if engine == 'CYCLES':
        scene.render.engine = 'CYCLES'
        scene.cycles.samples = 128; scene.cycles.use_denoising = True
        scene.cycles.transparent_max_bounces = max(16, scene.cycles.transparent_max_bounces)  # layered hair cards
    else:
        scene.render.engine = 'BLENDER_EEVEE' if 'BLENDER_EEVEE' in [e.identifier for e in scene.render.bl_rna.properties['engine'].enum_items] else 'BLENDER_EEVEE_NEXT'
    scene.render.resolution_x, scene.render.resolution_y = width, height
    scene.render.resolution_percentage = 100
    scene.render.film_transparent = transparent


def scene_ready(context, settings):
    """Lighting + camera + render settings. Returns a short description."""
    portrait = settings.framing == 'PORTRAIT'
    width, height = (1080, 1350) if portrait else (1920, 1080)
    render_settings(context, settings.render_engine, settings.transparent_background, width, height)
    keep_camera = settings.add_camera; settings.add_camera = False  # the camera is framed separately below
    try:
        lighting.apply(context, settings.lighting_preset, settings)
    finally:
        settings.add_camera = keep_camera
    frame_camera(context, settings.framing)
    return f"{lighting.preset_name(settings.lighting_preset)}, {'portrait' if portrait else 'full body'} camera, {width}×{height}"


# ---------------------------------------------------------------------------------------------- turntable
def _model_roots(context):
    objects = lighting.model_objects(context)
    rigs = {m.object for o in objects if o.type == 'MESH' for m in o.modifiers if m.type == 'ARMATURE' and m.object}
    roots = set()
    for obj in list(objects) + list(rigs):
        while obj.parent and obj.parent.name != TURNTABLE: obj = obj.parent
        if obj.parent is None: roots.add(obj)
    return [o for o in roots if not o.name.startswith('AAS ')]


def remove_turntable(context):
    table = bpy.data.objects.get(TURNTABLE)
    if not table: return False
    for child in list(table.children):
        world = child.matrix_world.copy(); child.parent = None; child.matrix_world = world
    bpy.data.objects.remove(table, do_unlink=True)
    return True


def turntable(context, seconds=8.0, clockwise=False):
    """Spin the model once around its feet. Lights and camera stay still. Returns the number of frames."""
    remove_turntable(context)
    scene = context.scene
    objects = lighting.model_objects(context)
    center, size, floor = lighting.bounds(objects)
    roots = _model_roots(context)
    if not roots: raise ValueError('No model to turn. Import or select one first')
    table = bpy.data.objects.new(TURNTABLE, None)
    table.empty_display_type = 'CIRCLE'; table.empty_display_size = size * .4
    table.location = (center.x, center.y, floor)
    lighting._collection(context).objects.link(table)
    for obj in roots:
        world = obj.matrix_world.copy(); obj.parent = table; obj.matrix_parent_inverse = table.matrix_world.inverted()
        obj.matrix_world = world
    frames = max(2, round(seconds * scene.render.fps / scene.render.fps_base))
    scene.frame_start, scene.frame_end = 1, frames
    turn = -2 * math.pi if clockwise else 2 * math.pi
    table.rotation_euler.z = 0; table.keyframe_insert('rotation_euler', index=2, frame=1)
    table.rotation_euler.z = turn; table.keyframe_insert('rotation_euler', index=2, frame=frames + 1)  # seamless loop
    _make_linear(table)
    return frames


def _make_linear(obj):
    """Constant speed: linear interpolation on the turntable's keys (works with both the classic and the
    layered action APIs)."""
    action = obj.animation_data.action if obj.animation_data else None
    if action is None: return
    curves = list(getattr(action, 'fcurves', []) or [])
    if not curves:
        for layer in getattr(action, 'layers', []):
            for strip in layer.strips:
                for bag in getattr(strip, 'channelbags', []): curves += list(bag.fcurves)
    for curve in curves:
        for key in curve.keyframe_points: key.interpolation = 'LINEAR'


def video_output(context, path, width=1920, height=1080):
    """MP4 (H.264) at `path` (without extension; Blender adds it)."""
    scene = context.scene; image = scene.render.image_settings
    if hasattr(image, 'media_type'): image.media_type = 'VIDEO'
    image.file_format = 'FFMPEG'
    scene.render.ffmpeg.format = 'MPEG4'; scene.render.ffmpeg.codec = 'H264'
    scene.render.ffmpeg.constant_rate_factor = 'HIGH'
    scene.render.resolution_x, scene.render.resolution_y = width, height
    scene.render.filepath = str(path)


def default_video_path(context):
    manifest = context.scene.aas_settings.manifest_path
    if manifest and Path(manifest).exists():
        stem = Path(manifest).name.replace('.aas.json', '')
        return str(Path(manifest).parent / f'{stem} turntable')
    return '//turntable'
