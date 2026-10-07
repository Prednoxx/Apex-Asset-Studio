"""Skeleton actions and poses."""
import bpy

POSE_PREFIX = 'AAS Pose · '


def target_rig(context):
    """Selected or last imported armature."""
    candidates = [context.active_object] + list(context.selected_objects)
    for obj in candidates:
        if obj is None: continue
        if obj.type == 'ARMATURE': return obj
        if obj.type == 'MESH':
            rig = next((m.object for m in obj.modifiers if m.type == 'ARMATURE' and m.object), None)
            if rig: return rig
    rigs = [o for o in context.scene.objects if o.type == 'ARMATURE' and o.get('aas_manifest')]
    return rigs[-1] if rigs else None


def fcurves(action):
    """Classic and slotted action curves."""
    curves = list(getattr(action, 'fcurves', []) or [])
    if curves: return curves
    for layer in getattr(action, 'layers', []) or []:
        for strip in layer.strips:
            for bag in getattr(strip, 'channelbags', []) or []: curves += list(bag.fcurves)
    return curves


_BONES = {}


def driven_bones(action):
    key = (action.name, len(fcurves(action)))
    if key not in _BONES:
        names = set()
        for curve in fcurves(action):
            path = curve.data_path
            if path.startswith('pose.bones["'): names.add(path[12:path.index('"]', 12)])
        _BONES[key] = names
    return _BONES[key]


def compatible(action, rig):
    """Check driven bones against skeleton."""
    if rig is None: return False
    if rig.get('aas_model_guid') and action.get('aas_model_guid') == rig.get('aas_model_guid'): return True
    bones = driven_bones(action)
    return bool(bones) and len(bones & set(rig.data.bones.keys())) >= max(1, len(bones) * .5)


def is_pose(action):
    return bool(action.get('aas_pose'))


def frames(action):
    start, end = action.frame_range
    return int(start), int(end)


def assign(rig, action):
    rig.animation_data_create()
    rig.animation_data.action = action
    slots = getattr(action, 'slots', None)
    if slots and hasattr(rig.animation_data, 'action_slot') and rig.animation_data.action_slot is None:
        rig.animation_data.action_slot = slots[0]


def play_action(context, rig, action):
    """Apply action and frame range."""
    assign(rig, action)
    start, end = frames(action)
    scene = context.scene
    if not is_pose(action):
        scene.frame_start, scene.frame_end = start, max(end, start + 1)
    scene.frame_set(start)


def bind_pose(rig):
    if rig.animation_data: rig.animation_data.action = None
    for bone in rig.pose.bones:
        bone.location = (0, 0, 0); bone.scale = (1, 1, 1)
        bone.rotation_quaternion = (1, 0, 0, 0); bone.rotation_euler = (0, 0, 0)


def save_pose(context, rig, name):
    """Store current pose as action."""
    context.view_layer.update()
    values = {}
    for bone in rig.pose.bones:
        values[bone.name] = (tuple(bone.location), tuple(bone.rotation_quaternion), tuple(bone.rotation_euler),
                             tuple(bone.scale), bone.rotation_mode)
    previous = rig.animation_data.action if rig.animation_data else None
    action = bpy.data.actions.new(POSE_PREFIX + name)
    action['aas_pose'] = True; action.use_fake_user = True
    if rig.get('aas_model_guid'): action['aas_model_guid'] = rig['aas_model_guid']
    rig.animation_data_create(); rig.animation_data.action = action
    for bone in rig.pose.bones:
        location, quaternion, euler, scale, mode = values[bone.name]
        bone.location, bone.scale = location, scale
        bone.keyframe_insert('location', frame=1, group=bone.name)
        bone.keyframe_insert('scale', frame=1, group=bone.name)
        if mode == 'QUATERNION':
            bone.rotation_quaternion = quaternion; bone.keyframe_insert('rotation_quaternion', frame=1, group=bone.name)
        elif mode != 'AXIS_ANGLE':
            bone.rotation_euler = euler; bone.keyframe_insert('rotation_euler', frame=1, group=bone.name)
    _BONES.clear()
    return action, previous
