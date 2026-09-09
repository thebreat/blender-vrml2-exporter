"""Blender-side integration check for manually marked sharp edge export."""

from __future__ import annotations

import importlib.util
import re
import sys
import tempfile
from pathlib import Path

import bpy
from mathutils import Matrix


SOURCE = Path(__file__).resolve().parents[1]
PACKAGE_NAME = "io_scene_vrml2_export_sharp_edge_test"


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


def main():
    extension = load_extension()
    for existing_object in list(bpy.data.objects):
        bpy.data.objects.remove(existing_object, do_unlink=True)

    mesh = bpy.data.meshes.new("Sharp Edge Export Test Mesh")
    mesh.from_pydata(
        [
            (0.0, 0.0, 0.0),
            (1.0, 0.0, 0.0),
            (1.0, 1.0, 0.0),
            (0.0, 1.0, 0.0),
        ],
        [],
        [(0, 1, 2), (0, 2, 3)],
    )
    for polygon in mesh.polygons:
        polygon.use_smooth = True
    for edge in mesh.edges:
        if set(edge.vertices) == {0, 2}:
            edge.use_edge_sharp = True
            break
    else:
        raise AssertionError("Shared test edge was not created")
    mesh.update()

    obj = bpy.data.objects.new("Sharp Edge Export Test", mesh)
    bpy.context.scene.collection.objects.link(obj)

    with tempfile.NamedTemporaryFile(suffix=".wrl", delete=False) as handle:
        export_path = Path(handle.name)

    operator = Operator()
    try:
        result = extension.export_vrml2.save(
            operator,
            bpy.context,
            filepath=str(export_path),
            global_matrix=Matrix.Identity(4),
            use_mesh_modifiers=False,
            use_color=False,
            use_uv=False,
            geometry_reuse="OFF",
        )
        assert result == {"FINISHED"}
        content = export_path.read_text(encoding="utf-8")
        assert "creaseAngle 3.141593" in content

        point_match = re.search(r"point \[ ([^\]]*)\]", content)
        assert point_match is not None, content
        point_values = [float(value) for value in point_match.group(1).split()]
        points = [
            tuple(point_values[index : index + 3])
            for index in range(0, len(point_values), 3)
        ]
        assert len(points) == 6, points
        assert len(set(points)) == 4, points

        index_match = re.search(r"coordIndex \[ ([^\]]*)\]", content)
        assert index_match is not None, content
        index_values = [int(value) for value in index_match.group(1).split()]
        faces = []
        face = []
        for value in index_values:
            if value == -1:
                faces.append(face)
                face = []
            else:
                face.append(value)
        assert len(faces) == 2, faces
        assert not set(faces[0]).intersection(faces[1]), faces
    finally:
        export_path.unlink(missing_ok=True)
        bpy.data.objects.remove(obj, do_unlink=True)
        bpy.data.meshes.remove(mesh)

    print("Blender sharp-edge export integration test passed.")


if __name__ == "__main__":
    main()
