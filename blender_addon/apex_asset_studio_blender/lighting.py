"""Preset light rigs for imported Apex models.

A rig is a set of lights placed on a sphere around the model (azimuth 0 = in front of the character, which faces
-Y after glTF import; positive azimuth = the character's left), a matching world background, and optionally a
shadow-catcher floor and a framed camera. Every light is parented to one empty ("AAS Light Target") at the model's
chest height and aims at it, so rotating that empty swings the whole rig around the model. Light power is
scaled with distance so a rig looks the same on a 2 m Legend and a 40 cm weapon.
"""
import math

import bpy
from mathutils import Vector

COLLECTION = 'AAS Lighting'
TARGET = 'AAS Light Target'

# Overall calibration against Blender's default AgX view transform (exposure 0): the preset numbers below are
# relative strengths; these bring a mid-grey surface to a mid-grey result under the key light.
AREA_EXPOSURE = .17
SUN_EXPOSURE = .35

WARM = (1.0, 0.9, 0.78)
COOL = (0.72, 0.84, 1.0)
WHITE = (1.0, 1.0, 1.0)


def _light(kind, azimuth, elevation, distance=2.4, energy=500, color=WHITE, size=1.0, role='', name=''):
    """distance and size are multiples of the model's height; energy is Watts for a 2 m model (Sun: W/m²)."""
    return dict(kind=kind, azimuth=azimuth, elevation=elevation, distance=distance, energy=energy, color=color,
                size=size, role=role, name=name)


def _world(zenith, horizon, ground, strength=1.0):
    return dict(zenith=zenith, horizon=horizon, ground=ground, strength=strength)


# name, description, lights, world
PRESETS = {
    'STUDIO': ('3-Point Studio', 'Classic key, fill and back light on a neutral grey studio', [
        _light('AREA', -35, 30, energy=650, color=WARM, size=.6, name='Key'),
        _light('AREA', 50, 12, energy=180, color=COOL, size=1.0, name='Fill'),
        _light('AREA', 160, 40, energy=550, size=.4, name='Back')],
        _world((.18, .18, .19), (.12, .12, .13), (.05, .05, .05), .6)),
    'RIM': ('Rim Light', 'Two strong back lights outline the silhouette, with a soft front fill', [
        _light('AREA', 135, 22, energy=900, size=.35, name='Rim Left'),
        _light('AREA', -135, 22, energy=900, size=.35, name='Rim Right'),
        _light('AREA', 0, 6, distance=3.0, energy=45, size=1.6, name='Front Fill')],
        _world((.02, .02, .025), (.015, .015, .02), (.005, .005, .005), .5)),
    'DUAL': ('Dual Color', 'Two colored keys from either side', [
        _light('AREA', -65, 15, energy=850, size=.5, role='A', name='Color A'),
        _light('AREA', 65, 15, energy=850, size=.5, role='B', name='Color B'),
        _light('AREA', 0, 70, energy=90, size=1.0, name='Top')],
        _world((.02, .02, .03), (.02, .02, .025), (.005, .005, .005), .5)),
    'SUNRISE': ('Sunrise', 'Low orange side sun under a pale blue dawn sky', [
        _light('SUN', -70, 6, energy=3.5, color=(1.0, .55, .28), size=3.0, name='Sun'),
        _light('AREA', 110, 30, energy=110, color=COOL, size=1.6, name='Sky Fill')],
        _world((.22, .32, .58), (1.0, .62, .38), (.08, .06, .05), .8)),
    'GOLDEN': ('Golden Hour', 'Warm late-afternoon sun from behind with a soft amber glow', [
        _light('SUN', 150, 14, energy=4.0, color=(1.0, .68, .38), size=2.0, name='Sun'),
        _light('AREA', -20, 15, distance=3.0, energy=160, color=(1.0, .82, .62), size=2.0, name='Bounce')],
        _world((.32, .42, .68), (1.0, .76, .5), (.12, .09, .06), .9)),
    'DAYLIGHT': ('Daylight', 'High midday sun and a clear blue sky', [
        _light('SUN', -30, 60, energy=5.0, color=(1.0, .97, .92), size=1.2, name='Sun')],
        _world((.25, .45, .9), (.72, .82, 1.0), (.22, .2, .18), .6)),
    'OVERCAST': ('Overcast Soft', 'Large soft light from above, almost no shadows', [
        _light('AREA', 0, 75, energy=320, size=3.0, name='Sky Panel')],
        _world((.62, .65, .7), (.75, .76, .78), (.3, .3, .3), .8)),
    'NIGHT': ('Moonlight', 'Cool blue moonlight with a warm lamp from the front', [
        _light('SUN', 120, 35, energy=.6, color=(.55, .66, 1.0), size=1.0, name='Moon'),
        _light('AREA', -40, 2, energy=180, color=(1.0, .6, .3), size=.5, name='Lamp')],
        _world((.01, .016, .04), (.02, .03, .06), (.005, .005, .01), .6)),
    'NEON': ('Neon', 'Pink and cyan rim lights with a purple top light', [
        _light('AREA', 120, 10, energy=950, color=(1.0, .15, .55), size=.35, name='Pink Rim'),
        _light('AREA', -120, 10, energy=950, color=(.1, .8, 1.0), size=.35, name='Cyan Rim'),
        _light('AREA', 0, 65, energy=180, color=(.55, .3, 1.0), size=1.0, name='Purple Top')],
        _world((.02, .005, .04), (.03, .01, .05), (.005, .002, .01), .5)),
    'DRAMATIC': ('Dramatic', 'One hard key from high on the side, deep shadows (Rembrandt style)', [
        _light('AREA', -50, 42, energy=1100, color=WARM, size=.25, name='Key'),
        _light('AREA', 70, 0, distance=3.0, energy=35, color=COOL, size=2.0, name='Fill')],
        _world((.005, .005, .006), (.004, .004, .005), (.002, .002, .002), .5)),
    'HIGH_KEY': ('High-Key Product', 'Bright, even white light on a white background', [
        _light('AREA', 0, 80, energy=520, size=2.5, name='Top Softbox'),
        _light('AREA', -30, 18, energy=300, size=2.0, name='Front Left'),
        _light('AREA', 30, 18, energy=300, size=2.0, name='Front Right')],
        _world((1.0, 1.0, 1.0), (1.0, 1.0, 1.0), (.9, .9, .9), .7)),
}

# The skin's own lobby lights, read from the export (Apex Asset Studio 0.4+ writes them into the .aas.json).
PRESETS['LOBBY'] = ('Apex Lobby', "The skin's lobby lighting from the game", [],
                    _world((.03, .03, .035), (.025, .025, .03), (.01, .01, .01), .5))
# where each lobby light sits (the game stores colors and strengths, not positions)
LOBBY_LAYOUT = {'Key': (-35, 25, 2.2), 'Fill': (45, 8, 2.4), 'RimL': (140, 30, 2.4), 'RimR': (-140, 30, 2.4)}
LOBBY_POWER = 330  # Watts per unit of the game's brightness, for a 2 m model

PRESET_ITEMS = [(key, name, description) for key, (name, description, _l, _w) in PRESETS.items()]


def preset_name(key):
    return PRESETS.get(key, ('Custom',))[0]


def lobby_lights(context):
    """Light specs for the 'Apex Lobby' preset from the imported export's lobby lighting."""
    import json
    from pathlib import Path
    path = Path(context.scene.aas_settings.manifest_path or '')
    try:
        manifest = json.loads(path.read_text(encoding='utf-8'))
    except (OSError, ValueError):
        raise ValueError('Import an Apex Asset Studio export first')
    data = ((manifest.get('metadata') or {}).get('cosmetic') or {}).get('lobby_lighting')
    if not data or not data.get('lights'):
        raise ValueError('No lobby lighting in this export. Re-export with Apex Asset Studio 0.4 or newer')
    specs = []
    for name, light in data['lights'].items():
        if name not in LOBBY_LAYOUT or light['brightness'] <= 0: continue
        azimuth, elevation, distance = LOBBY_LAYOUT[name]
        cone = light.get('cone_degrees') or 30
        specs.append(dict(kind='SPOT', azimuth=azimuth, elevation=elevation, distance=distance,
                          energy=light['brightness'] * LOBBY_POWER, color=tuple(light['color']), size=.15, role='',
                          name={'RimL': 'Rim Left', 'RimR': 'Rim Right'}.get(name, name),
                          cone=min(cone * 2, 170), blend=max(0., min(1., 1 - (light.get('inner_cone_degrees') or cone * .8) / cone)),
                          shadows=light.get('shadows', True)))
    return specs


# ---------------------------------------------------------------------------------------------- model bounds
def model_objects(context):
    """Meshes to light: the selection if it contains meshes (or an armature's meshes), otherwise the last imported
    Apex model, otherwise every visible mesh."""
    selected = [o for o in context.selected_objects if o.type in ('MESH', 'ARMATURE')]
    meshes = [o for o in selected if o.type == 'MESH']
    rigs = {o for o in selected if o.type == 'ARMATURE'}
    meshes += [o for o in context.scene.objects if o.type == 'MESH' and any(m.type == 'ARMATURE' and m.object in rigs for m in o.modifiers)]
    if meshes: return meshes
    manifest = context.scene.aas_settings.manifest_path
    imported = [o for o in context.scene.objects if o.type == 'MESH' and manifest and o.get('aas_manifest') == manifest]
    if imported: return imported
    return [o for o in context.scene.objects if o.type == 'MESH' and o.visible_get()
            and not o.name.startswith('AAS ') and COLLECTION not in [c.name for c in o.users_collection]]


def bounds(objects):
    corners = [o.matrix_world @ Vector(c) for o in objects for c in o.bound_box]
    if not corners: return Vector((0, 0, 1)), 2.0, 0.0
    low = Vector((min(c.x for c in corners), min(c.y for c in corners), min(c.z for c in corners)))
    high = Vector((max(c.x for c in corners), max(c.y for c in corners), max(c.z for c in corners)))
    size = max(high.x - low.x, high.y - low.y, high.z - low.z, .05)
    center = Vector(((low.x + high.x) / 2, (low.y + high.y) / 2, low.z + (high.z - low.z) * .6))
    return center, size, low.z


# ---------------------------------------------------------------------------------------------- rig
def _collection(context):
    collection = bpy.data.collections.get(COLLECTION)
    if collection is None:
        collection = bpy.data.collections.new(COLLECTION)
    if collection.name not in context.scene.collection.children:
        context.scene.collection.children.link(collection)
    return collection


def clear(context, restore_world=True):
    collection = bpy.data.collections.get(COLLECTION)
    if collection:
        for obj in list(collection.objects):
            if not obj.get('aas_rig'): continue  # the turntable and the Scene-ready camera stay
            data = obj.data
            bpy.data.objects.remove(obj, do_unlink=True)
            if data is not None and data.users == 0:
                if isinstance(data, bpy.types.Light): bpy.data.lights.remove(data)
                elif isinstance(data, bpy.types.Mesh): bpy.data.meshes.remove(data)
                elif isinstance(data, bpy.types.Camera): bpy.data.cameras.remove(data)
        if not collection.objects:
            bpy.data.collections.remove(collection)
    scene = context.scene
    if restore_world and 'aas_previous_world' in scene:
        name = scene['aas_previous_world']
        scene.world = bpy.data.worlds.get(name) if name else None
        del scene['aas_previous_world']


def _place(target, size, azimuth, elevation, distance):
    radius = distance * size
    a, e = math.radians(azimuth), math.radians(elevation)
    return Vector((math.sin(a) * math.cos(e), -math.cos(a) * math.cos(e), math.sin(e))) * radius


def _set_world(context, name, spec, strength):
    scene = context.scene
    if 'aas_previous_world' not in scene and not (scene.world and scene.world.name.startswith('AAS ')):
        scene['aas_previous_world'] = scene.world.name if scene.world else ''
    world = bpy.data.worlds.get('AAS ' + name) or bpy.data.worlds.new('AAS ' + name)
    world.use_nodes = True
    tree = world.node_tree; tree.nodes.clear()
    coords = tree.nodes.new('ShaderNodeTexCoord'); coords.location = (-900, 0)
    split = tree.nodes.new('ShaderNodeSeparateXYZ'); split.location = (-700, 0)
    remap = tree.nodes.new('ShaderNodeMapRange'); remap.location = (-500, 0)
    remap.inputs['From Min'].default_value = -1.0; remap.inputs['From Max'].default_value = 1.0
    ramp = tree.nodes.new('ShaderNodeValToRGB'); ramp.location = (-300, 0)
    stops = ramp.color_ramp.elements
    stops[0].position = .44; stops[0].color = (*spec['ground'], 1)
    stops[1].position = 1.0; stops[1].color = (*spec['zenith'], 1)
    horizon = stops.new(.5); horizon.color = (*spec['horizon'], 1)
    background = tree.nodes.new('ShaderNodeBackground'); background.location = (0, 0)
    background.inputs['Strength'].default_value = spec['strength'] * strength
    output = tree.nodes.new('ShaderNodeOutputWorld'); output.location = (200, 0)
    tree.links.new(coords.outputs['Generated'], split.inputs[0])
    tree.links.new(split.outputs['Z'], remap.inputs['Value'])
    tree.links.new(remap.outputs['Result'], ramp.inputs['Fac'])
    tree.links.new(ramp.outputs['Color'], background.inputs['Color'])
    tree.links.new(background.outputs['Background'], output.inputs['Surface'])
    world['aas_base_strength'] = spec['strength']
    scene.world = world


def apply(context, preset, settings):
    """Build the rig for `preset` around the model. Returns (number of lights, model height)."""
    name, _description, lights, world = PRESETS[preset]
    if preset == 'LOBBY': lights = lobby_lights(context)
    objects = model_objects(context)
    center, size, floor = bounds(objects)
    clear(context, restore_world=False)
    collection = _collection(context)
    target = bpy.data.objects.new(TARGET, None)
    target.empty_display_type = 'SPHERE'; target.empty_display_size = size * .05
    target.location = center; target.rotation_euler.z = math.radians(settings.light_rotation)
    target['aas_preset'] = preset; target['aas_size'] = size; target['aas_rig'] = True
    collection.objects.link(target)
    scale = (size / 2.0) ** 2 * AREA_EXPOSURE  # distances scale with the model, so power scales with its size²
    for spec in lights:
        data = bpy.data.lights.new(f"AAS {spec['name']}", spec['kind'])
        color = spec['color']
        if spec['role'] == 'A': color = tuple(settings.color_a)
        if spec['role'] == 'B': color = tuple(settings.color_b)
        data.color = color
        if spec['kind'] == 'SUN':
            base = spec['energy'] * SUN_EXPOSURE
            data.energy = base * settings.light_intensity
            data.angle = math.radians(spec['size'])
        else:
            base = spec['energy'] * scale
            data.energy = base * settings.light_intensity
            if spec['kind'] == 'AREA':
                data.shape = 'DISK'; data.size = spec['size'] * size
            else:
                data.shadow_soft_size = spec['size'] * size * .5
                if spec['kind'] == 'SPOT':
                    data.spot_size = math.radians(spec.get('cone', 60)); data.spot_blend = spec.get('blend', .2)
            if hasattr(data, 'use_shadow'): data.use_shadow = spec.get('shadows', True)
        data['aas_base_energy'] = base; data['aas_role'] = spec['role']
        light = bpy.data.objects.new(f"AAS {spec['name']}", data); light['aas_rig'] = True
        collection.objects.link(light)
        light.parent = target
        light.location = _place(target, size, spec['azimuth'], spec['elevation'], spec['distance'])
        aim = light.constraints.new('TRACK_TO'); aim.target = target
        aim.track_axis = 'TRACK_NEGATIVE_Z'; aim.up_axis = 'UP_Y'
    _set_world(context, name, world, settings.world_strength)
    if settings.add_floor: _floor(collection, center, size, floor)
    if settings.add_camera: _camera(context, collection, center, size)
    context.scene['aas_lighting'] = preset
    return len(lights), size


def _floor(collection, center, size, floor):
    mesh = bpy.data.meshes.new('AAS Floor')
    half = size * 3
    mesh.from_pydata([(-half, -half, 0), (half, -half, 0), (half, half, 0), (-half, half, 0)], [], [(0, 1, 2, 3)])
    obj = bpy.data.objects.new('AAS Floor', mesh); obj['aas_rig'] = True
    obj.location = (center.x, center.y, floor)
    obj.is_shadow_catcher = True  # Cycles keeps only the shadows; the plane itself stays invisible in renders
    collection.objects.link(obj)


def _camera(context, collection, center, size):
    if bpy.data.objects.get('AAS Camera'): return  # keep the Scene-ready camera
    data = bpy.data.cameras.new('AAS Camera'); data.lens = 50
    camera = bpy.data.objects.new('AAS Camera', data); camera['aas_rig'] = True
    collection.objects.link(camera)
    # front, slightly above, far enough that the whole model fits a 50 mm frame with some margin
    distance = size * 2.6
    camera.location = center + Vector((0, -distance, size * .15))
    aim = camera.constraints.new('TRACK_TO'); aim.target = bpy.data.objects.get(TARGET)
    aim.track_axis = 'TRACK_NEGATIVE_Z'; aim.up_axis = 'UP_Y'
    context.scene.camera = camera


# ---------------------------------------------------------------------------------------------- live tweaks
def update_live(context, settings):
    """Apply the intensity, rotation, world strength and dual colors to an existing rig without rebuilding it."""
    collection = bpy.data.collections.get(COLLECTION)
    if not collection: return
    for obj in collection.objects:
        if obj.type == 'LIGHT' and 'aas_base_energy' in obj.data:
            obj.data.energy = obj.data['aas_base_energy'] * settings.light_intensity
            if obj.data.get('aas_role') == 'A': obj.data.color = tuple(settings.color_a)
            if obj.data.get('aas_role') == 'B': obj.data.color = tuple(settings.color_b)
        elif obj.name.startswith(TARGET):
            obj.rotation_euler.z = math.radians(settings.light_rotation)
    world = context.scene.world
    if world and world.name.startswith('AAS ') and world.use_nodes:
        background = next((n for n in world.node_tree.nodes if n.type == 'BACKGROUND'), None)
        if background: background.inputs['Strength'].default_value = world.get('aas_base_strength', 1.0) * settings.world_strength
