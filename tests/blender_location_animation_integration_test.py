"""Blender-side integration check for sampled transform animation."""

from __future__ import annotations

import importlib.util
import math
import sys

sys.dont_write_bytecode = True

import tempfile  # noqa: E402
from pathlib import Path  # noqa: E402

import bpy  # noqa: E402
from bpy.props import (  # noqa: E402
    BoolProperty,
    FloatProperty,
    FloatVectorProperty,
    PointerProperty,
)
from mathutils import Matrix  # noqa: E402


SOURCE = Path(__file__).resolve().parents[1]
PACKAGE_NAME = "io_scene_vrml2_export_location_animation_test"


def load_extension():
    spec = importlib.util.spec_from_file_location(
        PACKAGE_NAME,
        SOURCE / "__init__.py",
        submodule_search_locations=[str(SOURCE)],
    )
    extension = importlib.util.module_from_spec(spec)
    sys.modules[PACKAGE_NAME] = extension
    spec.loader.exec_module(extension)
    return extension


class Operator:
    def report(self, _levels, message):
        self.message = message


class TestVRML2MaterialProperties(bpy.types.PropertyGroup):
    initialized: BoolProperty(default=False)
    enabled: BoolProperty(default=True)
    diffuse_color: FloatVectorProperty(size=3, default=(0.8, 0.8, 0.8))
    emissive_color: FloatVectorProperty(size=3, default=(0.0, 0.0, 0.0))
    specular_color: FloatVectorProperty(size=3, default=(0.0, 0.0, 0.0))
    ambient_intensity: FloatProperty(default=0.2)
    shininess: FloatProperty(default=0.2)
    transparency: FloatProperty(default=0.0)


def clear_scene():
    for existing_object in list(bpy.data.objects):
        bpy.data.objects.remove(existing_object, do_unlink=True)


def export(extension, path, **keywords):
    keywords.setdefault("use_mesh_modifiers", False)
    keywords.setdefault("use_color", False)
    keywords.setdefault("use_uv", False)
    keywords.setdefault("geometry_reuse", "OFF")
    result = extension.export_vrml2.save(
        Operator(),
        bpy.context,
        filepath=str(path),
        global_matrix=Matrix.Identity(4),
        **keywords,
    )
    assert result == {"FINISHED"}, result
    return path.read_text(encoding="utf-8")


def main():
    extension = load_extension()
    bpy.utils.register_class(TestVRML2MaterialProperties)
    bpy.types.Material.vrml2_material = PointerProperty(
        type=TestVRML2MaterialProperties
    )
    clear_scene()
    scene = bpy.context.scene
    scene.frame_start = 1
    scene.frame_end = 25
    scene.render.fps = 24
    scene.render.fps_base = 1.0

    mesh = bpy.data.meshes.new("Location Animation Mesh")
    mesh.from_pydata(
        [(0.0, 0.0, 0.0), (1.0, 0.0, 0.0), (0.0, 1.0, 0.0)],
        [],
        [(0, 1, 2)],
    )
    obj = bpy.data.objects.new("Moving Triangle", mesh)
    scene.collection.objects.link(obj)
    rotating_obj = bpy.data.objects.new("Rotating Triangle", mesh)
    scene.collection.objects.link(rotating_obj)
    rotating_obj.location = (-2.0, 0.0, 0.0)
    static_obj = bpy.data.objects.new("Static Triangle", mesh)
    scene.collection.objects.link(static_obj)
    static_obj.location = (0.0, -2.0, 0.0)

    shape_mesh = bpy.data.meshes.new("Shape Key Animation Mesh")
    shape_mesh.from_pydata(
        [
            (-1.0, -1.0, -1.0),
            (-1.0, -1.0, 1.0),
            (-1.0, 1.0, -1.0),
            (-1.0, 1.0, 1.0),
            (1.0, -1.0, -1.0),
            (1.0, -1.0, 1.0),
            (1.0, 1.0, -1.0),
            (1.0, 1.0, 1.0),
        ],
        [],
        [
            (0, 4, 6, 2),
            (1, 3, 7, 5),
            (0, 1, 5, 4),
            (2, 6, 7, 3),
            (0, 2, 3, 1),
            (4, 5, 7, 6),
        ],
    )
    shape_obj = bpy.data.objects.new("Deforming Triangle", shape_mesh)
    scene.collection.objects.link(shape_obj)
    shape_obj.location = (4.0, 0.0, 0.0)
    shape_obj.shape_key_add(name="Basis")
    lift_key = shape_obj.shape_key_add(name="Lift")
    lift_key.data[7].co = (1.5, 4.5, 3.0)
    lift_key.value = 0.0
    lift_key.keyframe_insert(data_path="value", frame=1)
    lift_key.value = 1.0
    lift_key.keyframe_insert(data_path="value", frame=25)

    armature_data = bpy.data.armatures.new("Animation Armature")
    armature_obj = bpy.data.objects.new("Animation Armature", armature_data)
    scene.collection.objects.link(armature_obj)
    bpy.context.view_layer.objects.active = armature_obj
    armature_obj.select_set(True)
    bpy.ops.object.mode_set(mode="EDIT")
    bone = armature_data.edit_bones.new("Bone")
    bone.head = (0.0, 0.0, 0.0)
    bone.tail = (0.0, 0.0, 2.0)
    bpy.ops.object.mode_set(mode="OBJECT")

    armature_mesh = bpy.data.meshes.new("Armature Animation Mesh")
    armature_mesh.from_pydata(
        [(0.0, 0.0, 0.0), (1.0, 0.0, 0.0), (0.0, 0.0, 1.0)],
        [],
        [(0, 1, 2)],
    )
    armature_mesh_obj = bpy.data.objects.new("Armature Triangle", armature_mesh)
    scene.collection.objects.link(armature_mesh_obj)
    armature_mesh_obj.location = (7.0, 0.0, 0.0)
    vertex_group = armature_mesh_obj.vertex_groups.new(name="Bone")
    vertex_group.add([0, 1, 2], 1.0, "REPLACE")
    armature_modifier = armature_mesh_obj.modifiers.new("Armature", "ARMATURE")
    armature_modifier.object = armature_obj
    pose_bone = armature_obj.pose.bones["Bone"]
    pose_bone.rotation_mode = "XYZ"
    pose_bone.rotation_euler = (0.0, 0.0, 0.0)
    pose_bone.keyframe_insert(data_path="rotation_euler", frame=1)
    pose_bone.rotation_euler = (0.0, 0.0, math.pi / 2.0)
    pose_bone.keyframe_insert(data_path="rotation_euler", frame=25)

    color_mesh = bpy.data.meshes.new("Diffuse Color Animation Mesh")
    color_mesh.from_pydata(
        [(0.0, 0.0, 0.0), (1.0, 0.0, 0.0), (0.0, 1.0, 0.0)],
        [],
        [(0, 1, 2)],
    )
    color_obj = bpy.data.objects.new("Color Changing Triangle", color_mesh)
    scene.collection.objects.link(color_obj)
    color_obj.location = (10.0, 0.0, 0.0)
    color_material = bpy.data.materials.new("Animated Diffuse Material")
    color_obj.data.materials.append(color_material)
    color_material["vrml2_initialized"] = True
    color_material["vrml2_enabled"] = True
    color_material["vrml2_diffuseColor"] = (0.25, 0.25, 0.25)
    studio_material = color_material.vrml2_material
    studio_material.initialized = True
    studio_material.enabled = True
    studio_material.diffuse_color = (1.0, 0.0, 0.0)
    studio_material.emissive_color = (0.0, 0.0, 0.0)
    studio_material.specular_color = (0.1, 0.1, 0.1)
    studio_material.ambient_intensity = 0.2
    studio_material.shininess = 0.1
    studio_material.transparency = 0.0
    for field in (
        "diffuse_color",
        "emissive_color",
        "specular_color",
        "ambient_intensity",
        "shininess",
        "transparency",
    ):
        studio_material.keyframe_insert(data_path=field, frame=1)
    studio_material.diffuse_color = (0.0, 0.0, 1.0)
    studio_material.emissive_color = (0.2, 0.4, 0.8)
    studio_material.specular_color = (1.0, 0.8, 0.2)
    studio_material.ambient_intensity = 0.7
    studio_material.shininess = 0.9
    studio_material.transparency = 0.6
    for field in (
        "diffuse_color",
        "emissive_color",
        "specular_color",
        "ambient_intensity",
        "shininess",
        "transparency",
    ):
        studio_material.keyframe_insert(data_path=field, frame=25)

    displace_modifier = color_obj.modifiers.new("Animated Displace", "DISPLACE")
    displace_modifier.strength = 0.0
    displace_modifier.keyframe_insert(data_path="strength", frame=1)
    displace_modifier.strength = 1.0
    displace_modifier.keyframe_insert(data_path="strength", frame=25)

    visibility_mesh = bpy.data.meshes.new("Visibility Animation Mesh")
    visibility_mesh.from_pydata(
        [(0.0, 0.0, 0.0), (1.0, 0.0, 0.0), (0.0, 1.0, 0.0)],
        [],
        [(0, 1, 2)],
    )
    visibility_obj = bpy.data.objects.new("Blinking Triangle", visibility_mesh)
    scene.collection.objects.link(visibility_obj)
    visibility_obj.location = (13.0, 0.0, 0.0)
    visibility_obj.hide_render = False
    visibility_obj.keyframe_insert(data_path="hide_render", frame=1)
    visibility_obj.hide_render = True
    visibility_obj.keyframe_insert(data_path="hide_render", frame=13)
    visibility_obj.hide_render = False
    visibility_obj.keyframe_insert(data_path="hide_render", frame=25)

    multi_mesh = bpy.data.meshes.new("Multi Material Animation Mesh")
    multi_mesh.from_pydata(
        [
            (0.0, 0.0, 0.0),
            (1.0, 0.0, 0.0),
            (0.0, 1.0, 0.0),
            (1.0, 1.0, 0.0),
        ],
        [],
        [(0, 1, 2), (1, 3, 2)],
    )
    multi_obj = bpy.data.objects.new("Two Material Plane", multi_mesh)
    scene.collection.objects.link(multi_obj)
    multi_obj.location = (16.0, 0.0, 0.0)
    multi_material_a = bpy.data.materials.new("Animated Material Slot A")
    multi_material_b = bpy.data.materials.new("Animated Material Slot B")
    multi_mesh.materials.append(multi_material_a)
    multi_mesh.materials.append(multi_material_b)
    multi_mesh.polygons[0].material_index = 0
    multi_mesh.polygons[1].material_index = 1
    for material in (multi_material_a, multi_material_b):
        properties = material.vrml2_material
        properties.initialized = True
        properties.enabled = True
    multi_properties_a = multi_material_a.vrml2_material
    multi_properties_a.diffuse_color = (1.0, 0.0, 0.0)
    multi_properties_a.keyframe_insert(data_path="diffuse_color", frame=1)
    multi_properties_a.diffuse_color = (0.0, 1.0, 0.0)
    multi_properties_a.keyframe_insert(data_path="diffuse_color", frame=25)
    multi_properties_b = multi_material_b.vrml2_material
    multi_properties_b.transparency = 0.0
    multi_properties_b.keyframe_insert(data_path="transparency", frame=1)
    multi_properties_b.transparency = 0.8
    multi_properties_b.keyframe_insert(data_path="transparency", frame=25)

    obj.location = (1.0, 2.0, 3.0)
    obj.rotation_mode = "XYZ"
    obj.rotation_euler = (0.0, 0.0, 0.5235987755982988)
    obj.scale = (1.0, 1.0, 1.0)
    obj.keyframe_insert(data_path="location", frame=1)
    obj.keyframe_insert(data_path="rotation_euler", frame=1)
    obj.keyframe_insert(data_path="scale", frame=1)
    obj.location = (3.0, 2.0, 3.0)
    obj.rotation_euler = (0.0, 0.0, 2.0943951023931953)
    obj.scale = (2.0, 0.5, 1.5)
    obj.keyframe_insert(data_path="location", frame=25)
    obj.keyframe_insert(data_path="rotation_euler", frame=25)
    obj.keyframe_insert(data_path="scale", frame=25)

    rotating_obj.rotation_mode = "XYZ"
    rotating_obj.rotation_euler = (0.0, 0.0, 0.0)
    rotating_obj.keyframe_insert(data_path="rotation_euler", frame=1)
    rotating_obj.rotation_euler = (0.0, 0.0, 1.5707963267948966)
    rotating_obj.keyframe_insert(data_path="rotation_euler", frame=25)
    scene.frame_set(7)

    with tempfile.TemporaryDirectory(prefix="vrml2-location-animation-") as temp:
        export_path = Path(temp) / "animation.wrl"
        looping_path = Path(temp) / "looping-animation.wrl"
        together_path = Path(temp) / "together-animation.wrl"
        automatic_path = Path(temp) / "automatic-animation.wrl"
        static_path = Path(temp) / "static.wrl"
        animated = export(
            extension,
            export_path,
            export_animation=True,
            animation_loop=False,
            animation_frame_step=12,
            use_mesh_modifiers=True,
            use_color=True,
            color_type="MATERIAL",
        )
        assert scene.frame_current == 7
        assert animated.count("Shape {") == 9
        animated_transform_count = animated.count("DEF AnimatedTransform_")
        assert animated_transform_count == 7, animated_transform_count
        assert "DEF AnimatedTransform_1 Transform {" in animated
        assert "DEF AnimatedTransform_2 Transform {" in animated
        assert "DEF AnimatedTransform_3 Transform {" in animated
        assert "DEF AnimatedTransform_4 Transform {" in animated
        assert "DEF AnimatedTransform_5 Transform {" in animated
        assert "DEF AnimatedTransform_6 Transform {" in animated
        assert "DEF AnimatedTransform_7 Transform {" in animated
        assert "center 1 2 3" in animated
        assert "center -2 0 0" in animated
        assert "scaleOrientation 0 0 1 0.523599" in animated
        assert "DEF AnimationClock TimeSensor {" not in animated
        assert animated.count("TimeSensor {") == 7
        for index in range(1, 8):
            assert f"DEF AnimationClock_{index} TimeSensor {{" in animated
        assert "cycleInterval 1" in animated
        assert "loop FALSE" in animated
        assert "startTime -1" in animated
        assert "DEF AnimationTouch_1 TouchSensor { }" in animated
        assert "key [ 0 0.5 1 ]" in animated
        assert "keyValue [ 0 0 0 1 0 0 2 0 0 ]" in animated
        assert "DEF RotationInterpolator_1 OrientationInterpolator {" in animated
        assert "DEF RotationInterpolator_2 OrientationInterpolator {" in animated
        assert "LocationInterpolator_2" not in animated
        assert "keyValue [ 0 0 1 0 0 0 1 0.785398 0 0 1 1.570796 ]" in animated
        assert (
            "ROUTE AnimationClock_1.fraction_changed TO "
            "LocationInterpolator_1.set_fraction"
        ) in animated
        assert (
            "ROUTE LocationInterpolator_1.value_changed TO "
            "AnimatedTransform_1.set_translation"
        ) in animated
        assert (
            "ROUTE AnimationClock_1.fraction_changed TO "
            "RotationInterpolator_1.set_fraction"
        ) in animated
        assert (
            "ROUTE RotationInterpolator_1.value_changed TO "
            "AnimatedTransform_1.set_rotation"
        ) in animated
        assert (
            "ROUTE RotationInterpolator_2.value_changed TO "
            "AnimatedTransform_2.set_rotation"
        ) in animated
        assert (
            "ROUTE AnimationClock_2.fraction_changed TO "
            "RotationInterpolator_2.set_fraction"
        ) in animated
        assert "DEF ScaleInterpolator_1 PositionInterpolator {" in animated
        assert "ScaleInterpolator_2" not in animated
        assert "keyValue [ 1 1 1 1.5 0.75 1.25 2 0.5 1.5 ]" in animated
        assert (
            "ROUTE ScaleInterpolator_1.value_changed TO "
            "AnimatedTransform_1.set_scale"
        ) in animated
        assert "coord DEF AnimatedCoordinates_3 Coordinate {" in animated
        assert "DEF CoordinateInterpolator_3 CoordinateInterpolator {" in animated
        assert (
            "ROUTE CoordinateInterpolator_3.value_changed TO "
            "AnimatedCoordinates_3.set_point"
        ) in animated
        assert "coord DEF AnimatedCoordinates_4 Coordinate {" in animated
        assert "DEF CoordinateInterpolator_4 CoordinateInterpolator {" in animated
        assert (
            "ROUTE CoordinateInterpolator_4.value_changed TO "
            "AnimatedCoordinates_4.set_point"
        ) in animated
        assert "material DEF AnimatedMaterial_5 Material {" in animated
        assert "coord DEF AnimatedCoordinates_5 Coordinate {" in animated
        assert "DEF CoordinateInterpolator_5 CoordinateInterpolator {" in animated
        assert (
            "ROUTE CoordinateInterpolator_5.value_changed TO "
            "AnimatedCoordinates_5.set_point"
        ) in animated
        assert "DEF ColorInterpolator_5 ColorInterpolator {" in animated
        assert "keyValue [ 1 0 0" in animated
        assert (
            "ROUTE AnimationClock_5.fraction_changed TO "
            "ColorInterpolator_5.set_fraction"
        ) in animated
        assert (
            "ROUTE ColorInterpolator_5.value_changed TO "
            "AnimatedMaterial_5.set_diffuseColor"
        ) in animated
        for interpolator, node_type, vrml_field in (
            ("EmissiveColorInterpolator_5", "ColorInterpolator", "emissiveColor"),
            ("SpecularColorInterpolator_5", "ColorInterpolator", "specularColor"),
            ("AmbientIntensityInterpolator_5", "ScalarInterpolator", "ambientIntensity"),
            ("ShininessInterpolator_5", "ScalarInterpolator", "shininess"),
            ("TransparencyInterpolator_5", "ScalarInterpolator", "transparency"),
        ):
            assert f"DEF {interpolator} {node_type} {{" in animated
            assert (
                f"ROUTE {interpolator}.value_changed TO "
                f"AnimatedMaterial_5.set_{vrml_field}"
            ) in animated
        assert (
            "ROUTE AnimationTouch_1.touchTime TO AnimationClock_1.set_startTime"
        ) in animated
        assert (
            "ROUTE AnimationTouch_5.touchTime TO AnimationClock_5.set_startTime"
        ) in animated
        assert "material DEF AnimatedMaterial_6_1 Material {" in animated
        assert "material DEF AnimatedMaterial_6_2 Material {" in animated
        assert "DEF ColorInterpolator_6_1 ColorInterpolator {" in animated
        assert "DEF TransparencyInterpolator_6_2 ScalarInterpolator {" in animated
        assert (
            "ROUTE ColorInterpolator_6_1.value_changed TO "
            "AnimatedMaterial_6_1.set_diffuseColor"
        ) in animated
        assert (
            "ROUTE TransparencyInterpolator_6_2.value_changed TO "
            "AnimatedMaterial_6_2.set_transparency"
        ) in animated
        assert "DEF VisibilitySwitch_7 Switch {" in animated
        assert "whichChoice 0" in animated
        assert "DEF VisibilityScript_7 Script {" in animated
        assert "field MFInt32 keyValue [ 0 -1 0 ]" in animated
        assert (
            "ROUTE AnimationClock_7.fraction_changed TO "
            "VisibilityScript_7.set_fraction"
        ) in animated
        assert (
            "ROUTE VisibilityScript_7.choice_changed TO "
            "VisibilitySwitch_7.set_whichChoice"
        ) in animated
        assert (
            "ROUTE AnimationTouch_7.touchTime TO AnimationClock_7.set_startTime"
        ) in animated

        looping = export(
            extension,
            looping_path,
            export_animation=True,
            animation_loop=True,
            animation_frame_step=12,
            geometry_reuse="LINKED",
            use_mesh_modifiers=True,
            use_color=True,
            color_type="MATERIAL",
        )
        assert "loop TRUE" in looping
        assert looping.count("DEF AnimationClock TimeSensor {") == 1
        assert "AnimationClock_1" not in looping
        assert (
            "ROUTE AnimationClock.fraction_changed TO "
            "LocationInterpolator_1.set_fraction"
        ) in looping
        assert "startTime -1" not in looping
        assert "TouchSensor" not in looping
        assert ".touchTime" not in looping
        assert looping.count("geometry DEF Geometry_1 IndexedFaceSet") == 1
        assert looping.count("geometry USE Geometry_1") == 2

        together = export(
            extension,
            together_path,
            export_animation=True,
            animation_loop=False,
            animation_play_together=True,
            animation_frame_step=12,
            use_mesh_modifiers=True,
            use_color=True,
            color_type="MATERIAL",
        )
        assert together.count("DEF AnimationClock TimeSensor {") == 1
        assert "AnimationClock_1" not in together
        assert "loop FALSE" in together
        assert "startTime -1" in together
        assert together.count("TouchSensor { }") == 7
        for index in range(1, 8):
            assert (
                f"ROUTE AnimationTouch_{index}.touchTime TO "
                "AnimationClock.set_startTime"
            ) in together
        assert (
            "ROUTE AnimationClock.fraction_changed TO "
            "LocationInterpolator_1.set_fraction"
        ) in together
        assert (
            "ROUTE AnimationClock.fraction_changed TO "
            "TransparencyInterpolator_6_2.set_fraction"
        ) in together

        automatic = export(
            extension,
            automatic_path,
            export_animation=True,
            animation_loop=False,
            animation_start_automatically=True,
            animation_frame_step=12,
            use_mesh_modifiers=True,
            use_color=True,
            color_type="MATERIAL",
        )
        assert automatic.count("TimeSensor {") == 7
        assert automatic.count("startTime 0") == 7
        assert "startTime -1" not in automatic
        assert automatic.count("TouchSensor { }") == 7
        assert (
            "ROUTE AnimationTouch_1.touchTime TO "
            "AnimationClock_1.set_startTime"
        ) in automatic
        assert (
            "ROUTE AnimationTouch_7.touchTime TO "
            "AnimationClock_7.set_startTime"
        ) in automatic

        static = export(extension, static_path, export_animation=False)
        assert "TimeSensor" not in static
        assert "PositionInterpolator" not in static
        assert "OrientationInterpolator" not in static
        assert "ScaleInterpolator" not in static
        assert "CoordinateInterpolator" not in static
        assert "ColorInterpolator" not in static
        assert "ScalarInterpolator" not in static
        assert "AnimatedTransform" not in static

    clear_scene()
    bpy.data.meshes.remove(mesh)
    bpy.data.meshes.remove(shape_mesh)
    bpy.data.meshes.remove(armature_mesh)
    bpy.data.armatures.remove(armature_data)
    bpy.data.meshes.remove(color_mesh)
    bpy.data.materials.remove(color_material)
    bpy.data.meshes.remove(visibility_mesh)
    bpy.data.meshes.remove(multi_mesh)
    bpy.data.materials.remove(multi_material_a)
    bpy.data.materials.remove(multi_material_b)
    del bpy.types.Material.vrml2_material
    bpy.utils.unregister_class(TestVRML2MaterialProperties)
    print("Blender transform animation integration test passed.")


if __name__ == "__main__":
    main()
