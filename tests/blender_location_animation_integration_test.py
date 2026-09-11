"""Blender-side integration check for the first location-animation alpha."""

from __future__ import annotations

import importlib.util
import sys

sys.dont_write_bytecode = True

import tempfile  # noqa: E402
from pathlib import Path  # noqa: E402

import bpy  # noqa: E402
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
    static_obj = bpy.data.objects.new("Static Triangle", mesh)
    scene.collection.objects.link(static_obj)
    static_obj.location = (-2.0, 0.0, 0.0)

    obj.location = (1.0, 2.0, 3.0)
    obj.keyframe_insert(data_path="location", frame=1)
    obj.location = (3.0, 2.0, 3.0)
    obj.keyframe_insert(data_path="location", frame=25)
    scene.frame_set(7)

    with tempfile.TemporaryDirectory(prefix="vrml2-location-animation-") as temp:
        export_path = Path(temp) / "animation.wrl"
        looping_path = Path(temp) / "looping-animation.wrl"
        static_path = Path(temp) / "static.wrl"
        animated = export(
            extension,
            export_path,
            export_animation=True,
            animation_loop=False,
            animation_frame_step=12,
        )
        assert scene.frame_current == 7
        assert animated.count("Shape {") == 2
        assert animated.count("DEF AnimatedTransform_") == 1
        assert "DEF AnimatedTransform_1 Transform {" in animated
        assert "DEF AnimationClock TimeSensor {" in animated
        assert "cycleInterval 1" in animated
        assert "loop FALSE" in animated
        assert "DEF AnimationTouch_1 TouchSensor { }" in animated
        assert "key [ 0 0.5 1 ]" in animated
        assert "keyValue [ 0 0 0 1 0 0 2 0 0 ]" in animated
        assert (
            "ROUTE AnimationClock.fraction_changed TO "
            "LocationInterpolator_1.set_fraction"
        ) in animated
        assert (
            "ROUTE LocationInterpolator_1.value_changed TO "
            "AnimatedTransform_1.set_translation"
        ) in animated
        assert (
            "ROUTE AnimationTouch_1.touchTime TO AnimationClock.set_startTime"
        ) in animated

        looping = export(
            extension,
            looping_path,
            export_animation=True,
            animation_loop=True,
            animation_frame_step=12,
            geometry_reuse="LINKED",
        )
        assert "loop TRUE" in looping
        assert "TouchSensor" not in looping
        assert ".touchTime" not in looping
        assert looping.count("geometry DEF Geometry_1 IndexedFaceSet") == 1
        assert looping.count("geometry USE Geometry_1") == 1

        static = export(extension, static_path, export_animation=False)
        assert "TimeSensor" not in static
        assert "PositionInterpolator" not in static
        assert "AnimatedTransform" not in static

    clear_scene()
    bpy.data.meshes.remove(mesh)
    print("Blender location animation integration test passed.")


if __name__ == "__main__":
    main()
