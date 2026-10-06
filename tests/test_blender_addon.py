"""Blender add-on smoke test. Runs only where Blender's Python module is installed (pip install bpy), otherwise
skipped: every lighting preset builds, live tweaks apply, and removing the rig restores the scene."""
import sys
import unittest
from pathlib import Path

try:
    import bpy
except ImportError:
    bpy = None


@unittest.skipIf(bpy is None, 'Blender (bpy) is not installed')
class BlenderAddonTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'blender_addon'))
        import apex_asset_studio_blender as addon
        cls.addon = addon
        bpy.ops.wm.read_factory_settings(use_empty=True)
        addon.register()

    @classmethod
    def tearDownClass(cls):
        cls.addon.unregister()

    def test_presets(self):
        bpy.ops.mesh.primitive_cylinder_add(radius=.25, depth=1.8, location=(0, 0, .9))
        settings = bpy.context.scene.aas_settings
        for key in [k for k in self.addon.lighting.PRESETS if k != 'LOBBY']:
            with self.subTest(preset=key):
                self.assertEqual(bpy.ops.aas.apply_lighting(preset=key), {'FINISHED'})
                lights = [o for o in bpy.data.collections['AAS Lighting'].objects if o.type == 'LIGHT']
                self.assertEqual(len(lights), len(self.addon.lighting.PRESETS[key][2]))
        light = lights[0]; base = light.data['aas_base_energy']
        settings.light_intensity = 2.0
        self.assertAlmostEqual(light.data.energy, base * 2, places=3)
        bpy.ops.aas.clear_lighting()
        self.assertNotIn('AAS Lighting', bpy.data.collections)
        self.assertIsNone(bpy.context.scene.world)

    def test_scene_ready_and_turntable(self):
        import json, tempfile, os
        bpy.ops.mesh.primitive_cylinder_add(radius=.25, depth=1.8, location=(0, 0, .9))
        cylinder = bpy.context.object
        folder = tempfile.mkdtemp()
        manifest = os.path.join(folder, 'Test.aas.json')
        lights = {'Key': {'color': [1, .9, .8], 'brightness': 4, 'cone_degrees': 18, 'inner_cone_degrees': 15, 'shadows': True}}
        json.dump({'metadata': {'cosmetic': {'lobby_lighting': {'custom': True, 'lights': lights}}}}, open(manifest, 'w'))
        settings = bpy.context.scene.aas_settings
        settings.manifest_path = manifest; settings.lighting_preset = 'LOBBY'; settings.framing = 'PORTRAIT'
        self.assertEqual(bpy.ops.aas.scene_ready(), {'FINISHED'})
        self.assertEqual(bpy.context.scene.camera.name, 'AAS Camera')
        self.assertEqual((bpy.context.scene.render.resolution_x, bpy.context.scene.render.resolution_y), (1080, 1350))
        settings.turntable_seconds = 2
        self.assertEqual(bpy.ops.aas.turntable(), {'FINISHED'})
        self.assertEqual(cylinder.parent.name, 'AAS Turntable')
        self.assertEqual(bpy.ops.aas.apply_lighting(preset='RIM'), {'FINISHED'})  # relighting keeps the turntable
        self.assertIsNotNone(bpy.data.objects.get('AAS Turntable'))
        bpy.ops.aas.remove_turntable()
        self.assertIsNone(cylinder.parent)
        self.assertAlmostEqual(cylinder.matrix_world.translation.z, .9, places=4)

    def test_animations_and_poses(self):
        import mathutils
        anim = self.addon.anim
        bpy.ops.object.armature_add(); rig = bpy.context.object; rig['aas_model_guid'] = 'M1'
        action = bpy.data.actions.new('Wave'); rig.animation_data_create(); rig.animation_data.action = action
        bone = rig.pose.bones[0]; bone.rotation_mode = 'QUATERNION'
        for frame, angle in ((1, 0), (24, 1.0)):
            bone.rotation_quaternion = mathutils.Euler((angle, 0, 0)).to_quaternion(); bone.keyframe_insert('rotation_quaternion', frame=frame)
        self.assertTrue(anim.compatible(action, rig))
        settings = bpy.context.scene.aas_settings
        settings.anim_index = list(bpy.data.actions).index(action)
        self.assertEqual((bpy.context.scene.frame_start, bpy.context.scene.frame_end), (1, 24))
        bpy.context.scene.frame_set(24)
        self.assertEqual(bpy.ops.aas.save_pose(name='End'), {'FINISHED'})
        pose = next(a for a in bpy.data.actions if anim.is_pose(a))
        self.assertEqual(bpy.ops.aas.bind_pose(), {'FINISHED'})
        self.assertAlmostEqual(rig.pose.bones[0].rotation_quaternion[0], 1.0)
        settings.pose_index = list(bpy.data.actions).index(pose); bpy.context.view_layer.update()
        self.assertLess(rig.pose.bones[0].rotation_quaternion[0], .95)

    def test_material_controls(self):
        from apex_asset_studio_blender.materials import controls_group
        settings = bpy.context.scene.aas_settings
        settings.mat_roughness = .5
        self.assertAlmostEqual(controls_group().nodes['Roughness'].outputs[0].default_value, .5)
        bpy.ops.aas.reset_material_controls()
        self.assertAlmostEqual(controls_group().nodes['Roughness'].outputs[0].default_value, 1.0)


if __name__ == '__main__':
    unittest.main()
