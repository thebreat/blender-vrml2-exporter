"""Blender-side integration check for VRML2 Material Studio export data."""

from __future__ import annotations

import importlib.util
import sys
import tempfile
from pathlib import Path

import bpy
from mathutils import Matrix


SOURCE = Path(__file__).resolve().parents[1]
PACKAGE_NAME = "io_scene_vrml2_export_material_test"


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


def set_studio_values(material, values):
    material["vrml2_initialized"] = True
    material["vrml2_enabled"] = True
    material["vrml2_diffuseColor"] = values["diffuse_color"]
    material["vrml2_emissiveColor"] = values["emissive_color"]
    material["vrml2_specularColor"] = values["specular_color"]
    material["vrml2_ambientIntensity"] = values["ambient_intensity"]
    material["vrml2_shininess"] = values["shininess"]
    material["vrml2_transparency"] = values["transparency"]


class Operator:
    def report(self, _levels, message):
        self.message = message


def main():
    extension = load_extension()
    for existing_object in list(bpy.data.objects):
        bpy.data.objects.remove(existing_object, do_unlink=True)

    mesh = bpy.data.meshes.new("Material Studio Export Test Mesh")
    mesh.from_pydata(
        [
            (0.0, 0.0, 0.0),
            (1.0, 0.0, 0.0),
            (0.0, 1.0, 0.0),
            (2.0, 0.0, 0.0),
            (3.0, 0.0, 0.0),
            (2.0, 1.0, 0.0),
        ],
        [],
        [(0, 1, 2), (3, 4, 5)],
    )
    mesh.polygons[0].material_index = 0
    mesh.polygons[1].material_index = 1

    first = bpy.data.materials.new("Studio First")
    second = bpy.data.materials.new("Studio Second")
    set_studio_values(
        first,
        {
            "diffuse_color": (0.1, 0.2, 0.3),
            "emissive_color": (0.01, 0.02, 0.03),
            "specular_color": (0.4, 0.5, 0.6),
            "ambient_intensity": 0.25,
            "shininess": 0.7,
            "transparency": 0.1,
        },
    )
    set_studio_values(
        second,
        {
            "diffuse_color": (0.7, 0.6, 0.5),
            "emissive_color": (0.03, 0.02, 0.01),
            "specular_color": (0.3, 0.2, 0.1),
            "ambient_intensity": 0.4,
            "shininess": 0.8,
            "transparency": 0.2,
        },
    )
    mesh.materials.append(first)
    mesh.materials.append(second)

    obj = bpy.data.objects.new("Material Studio Export Test", mesh)
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
            use_color=True,
            color_type="MATERIAL",
            use_uv=False,
            geometry_reuse="OFF",
        )
        assert result == {"FINISHED"}
        content = export_path.read_text(encoding="utf-8")
        assert content.count("Shape {") == 2, content
        assert content.count("material Material {") == 2, content
        assert "diffuseColor 0.1 0.2 0.3" in content
        assert "emissiveColor 0.01 0.02 0.03" in content
        assert "specularColor 0.4 0.5 0.6" in content
        assert "ambientIntensity 0.25" in content
        assert "shininess 0.7" in content
        assert "transparency 0.1" in content
        assert "diffuseColor 0.7 0.6 0.5" in content
        assert "transparency 0.2" in content
        assert content.count("coordIndex [") == 2
    finally:
        export_path.unlink(missing_ok=True)
        bpy.data.objects.remove(obj, do_unlink=True)
        bpy.data.meshes.remove(mesh)
        bpy.data.materials.remove(first)
        bpy.data.materials.remove(second)

    print("Blender Material Studio export integration test passed.")


if __name__ == "__main__":
    main()
