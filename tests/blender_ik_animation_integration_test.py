"""Verify that IK driven deformation survives a multi material VRML export."""

from __future__ import annotations

import importlib.util
import re
import sys
import tempfile
from pathlib import Path

sys.dont_write_bytecode = True

import bpy  # noqa: E402
from mathutils import Matrix  # noqa: E402


SOURCE = Path(__file__).resolve().parents[1]


def load_extension():
    package_name = "io_scene_vrml2_export_ik_test"
    spec = importlib.util.spec_from_file_location(
        package_name,
        SOURCE / "__init__.py",
        submodule_search_locations=[str(SOURCE)],
    )
    extension = importlib.util.module_from_spec(spec)
    sys.modules[package_name] = extension
    spec.loader.exec_module(extension)
    return extension


class Operator:
    def report(self, _levels, message):
        self.message = message


def main():
    extension = load_extension()
    for existing_object in list(bpy.data.objects):
        bpy.data.objects.remove(existing_object, do_unlink=True)
    scene = bpy.context.scene
    scene.frame_start = 1
    scene.frame_end = 25
    scene.render.fps = 24

    armature_data = bpy.data.armatures.new("IK Rig")
    armature = bpy.data.objects.new("IK Rig", armature_data)
    scene.collection.objects.link(armature)
    bpy.context.view_layer.objects.active = armature
    armature.select_set(True)
    bpy.ops.object.mode_set(mode="EDIT")
    lower = armature_data.edit_bones.new("Lower")
    lower.head = (0.0, 0.0, 0.0)
    lower.tail = (0.0, 0.0, 1.0)
    upper = armature_data.edit_bones.new("Upper")
    upper.head = lower.tail
    upper.tail = (0.0, 0.0, 2.0)
    upper.parent = lower
    upper.use_connect = True
    bpy.ops.object.mode_set(mode="OBJECT")

    target = bpy.data.objects.new("IK Target", None)
    scene.collection.objects.link(target)
    target.empty_display_type = "PLAIN_AXES"
    target.empty_display_size = 0.35
    target.location = (0.2, 0.0, 1.8)
    target.keyframe_insert(data_path="location", frame=1)
    target.location = (1.2, 0.0, 0.9)
    target.keyframe_insert(data_path="location", frame=25)
    constraint = armature.pose.bones["Upper"].constraints.new("IK")
    constraint.target = target
    constraint.chain_count = 2

    mesh = bpy.data.meshes.new("Two Material IK Mesh")
    mesh.from_pydata(
        [
            (-0.15, 0.0, 0.0), (0.15, 0.0, 0.0),
            (-0.15, 0.0, 1.0), (0.15, 0.0, 1.0),
            (-0.15, 0.0, 2.0), (0.15, 0.0, 2.0),
        ],
        [],
        [(0, 1, 3, 2), (2, 3, 5, 4)],
    )
    mesh_obj = bpy.data.objects.new("IK Mesh", mesh)
    scene.collection.objects.link(mesh_obj)
    for bone_name, vertex_indices in (("Lower", (0, 1, 2, 3)), ("Upper", (4, 5))):
        group = mesh_obj.vertex_groups.new(name=bone_name)
        group.add(list(vertex_indices), 1.0, "REPLACE")
    modifier = mesh_obj.modifiers.new("IK Armature", "ARMATURE")
    modifier.object = armature

    for index in range(2):
        material = bpy.data.materials.new(f"IK Material {index + 1}")
        material.diffuse_color = (1.0, float(index), 0.0, 1.0)
        material["vrml2_initialized"] = True
        material["vrml2_enabled"] = True
        material["vrml2_diffuseColor"] = (1.0, float(index), 0.0)
        mesh.materials.append(material)
        mesh.polygons[index].material_index = index

    example_paths = (
        sys.argv[sys.argv.index("--") + 1:]
        if "--" in sys.argv
        else []
    )
    if example_paths:
        scene.frame_set(1)
        armature.select_set(False)
        target.select_set(True)
        bpy.context.view_layer.objects.active = target
        bpy.ops.wm.save_as_mainfile(filepath=str(Path(example_paths[0]).resolve()))

    evaluated_positions = []
    with tempfile.TemporaryDirectory(prefix="vrml2-ik-animation-") as temporary:
        for frame in (1, 25):
            scene.frame_set(frame)
            depsgraph = bpy.context.evaluated_depsgraph_get()
            evaluated = mesh_obj.evaluated_get(depsgraph)
            evaluated_mesh = evaluated.to_mesh()
            evaluated_positions.append(
                tuple(tuple(vertex.co) for vertex in evaluated_mesh.vertices)
            )
            evaluated.to_mesh_clear()
        assert any(
            abs(current[axis] - initial[axis]) > 0.01
            for initial, current in zip(*evaluated_positions)
            for axis in range(3)
        ), "The IK target did not deform the test mesh"

        export_path = Path(temporary) / "ik-animation.wrl"
        result = extension.export_vrml2.save(
            Operator(),
            bpy.context,
            filepath=str(export_path),
            global_matrix=Matrix.Identity(4),
            use_mesh_modifiers=True,
            use_color=True,
            color_type="MATERIAL",
            use_uv=False,
            geometry_reuse="OFF",
            export_animation=True,
            animation_frame_step=12,
        )
        assert result == {"FINISHED"}, result
        wrl = export_path.read_text(encoding="utf-8")
        assert wrl.count("Shape {") == 2
        assert wrl.count("TimeSensor {") == 1
        assert "material DEF" not in wrl
        for material_index in (1, 2):
            coordinate = f"AnimatedCoordinates_1_{material_index}"
            interpolator = f"CoordinateInterpolator_1_{material_index}"
            assert f"coord DEF {coordinate} Coordinate {{" in wrl
            assert f"DEF {interpolator} CoordinateInterpolator {{" in wrl
            assert (
                f"ROUTE AnimationClock_1.fraction_changed TO "
                f"{interpolator}.set_fraction"
            ) in wrl
            assert (
                f"ROUTE {interpolator}.value_changed TO "
                f"{coordinate}.set_point"
            ) in wrl
            match = re.search(
                rf"DEF {interpolator} CoordinateInterpolator \{{.*?"
                r"keyValue \[ ([^\]]+) \]",
                wrl,
                re.DOTALL,
            )
            assert match is not None
            key_values = [float(value) for value in match.group(1).split()]
            assert len(key_values) % 3 == 0
            values_per_frame = len(key_values) // 3
            assert values_per_frame > 0
            assert any(
                abs(a - b) > 0.01
                for a, b in zip(
                    key_values[:values_per_frame],
                    key_values[-values_per_frame:],
                )
            )
        assert "ROUTE AnimationTouch_1.touchTime TO AnimationClock_1.set_startTime" in wrl
    print("Blender IK animation integration test passed.")


if __name__ == "__main__":
    main()
