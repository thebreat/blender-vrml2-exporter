"""Blender-side integration checks for texture path modes and Shape lighting.

These two behaviours depend on Blender itself rather than on the writer alone:

* Path modes are resolved by ``bpy_extras.io_utils.path_reference``. The
  Blender-free smoke test can only exercise a stand-in for that function, so it
  proves the writer honours our model of Blender's rules. Running the real
  function here proves the writer honours Blender's actual rules. In particular
  Match reads Blender's ``//`` prefix, which only exists on genuine Blender
  image data.
* The material and texture branches are chosen from evaluated Blender material,
  UV and colour-attribute data, which the smoke test supplies as stubs.

The fixtures are built entirely inside a temporary directory, and the blend file
is saved inside it, so every expected relative path is deterministic on any
machine.
"""

from __future__ import annotations

import importlib.util
import sys
from contextlib import contextmanager

# Importing the exporter would otherwise leave __pycache__ directories in the
# checkout. Blender enables bytecode writing regardless of PYTHONDONTWRITEBYTECODE,
# so it has to be turned off here, before the extension is imported.
sys.dont_write_bytecode = True

import tempfile  # noqa: E402
from pathlib import Path  # noqa: E402

import bpy  # noqa: E402
from mathutils import Matrix  # noqa: E402


SOURCE = Path(__file__).resolve().parents[1]
PACKAGE_NAME = "io_scene_vrml2_export_correctness_test"

TEXTURE_NAME = "example.png"
PATH_MODES = ("AUTO", "ABSOLUTE", "RELATIVE", "MATCH", "STRIP", "COPY")

EMPTY_MATERIAL = "material Material {\n\t\t}"


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


def set_studio_values(material, values):
    material["vrml2_initialized"] = True
    material["vrml2_enabled"] = True
    material["vrml2_diffuseColor"] = values["diffuse_color"]
    material["vrml2_emissiveColor"] = values["emissive_color"]
    material["vrml2_specularColor"] = values["specular_color"]
    material["vrml2_ambientIntensity"] = values["ambient_intensity"]
    material["vrml2_shininess"] = values["shininess"]
    material["vrml2_transparency"] = values["transparency"]


@contextmanager
def texture_image(texture_directory, stored_filepath):
    """Write a real image file so Copy mode has something to copy.

    ``stored_filepath`` is what Blender keeps in ``Image.filepath``. Match reads
    the ``//`` prefix from it, so the stored form matters as much as the file.
    """
    texture_directory.mkdir(parents=True, exist_ok=True)
    image = bpy.data.images.new("Correctness Texture", 4, 4)
    try:
        image.file_format = "PNG"
        image.filepath_raw = str(texture_directory / TEXTURE_NAME)
        image.save()
        image.filepath = stored_filepath
        yield image
    finally:
        bpy.data.images.remove(image)


@contextmanager
def textured_object(image, *, with_color_attribute=False, materials=()):
    """Build a UV-mapped mesh whose materials are supplied by the caller.

    ``materials`` receives the shared image texture node, because every case
    here is about what an Appearance carries alongside a texture.
    """
    created_materials = []
    mesh = bpy.data.meshes.new("Correctness Mesh")
    obj = None
    try:
        corners = [
            (0.0, 0.0, 0.0), (1.0, 0.0, 0.0), (0.0, 1.0, 0.0),
            (2.0, 0.0, 0.0), (3.0, 0.0, 0.0), (2.0, 1.0, 0.0),
        ]
        mesh.from_pydata(corners, [], [(0, 1, 2), (3, 4, 5)])
        mesh.uv_layers.new(name="UVMap")
        if with_color_attribute:
            mesh.color_attributes.new(name="Col", type="FLOAT_COLOR", domain="CORNER")

        specs = materials or ({"name": "Plain"},)
        for spec in specs:
            material = bpy.data.materials.new(spec["name"])
            created_materials.append(material)
            texture_node = material.node_tree.nodes.new("ShaderNodeTexImage")
            texture_node.image = image
            material.node_tree.nodes.active = texture_node
            if "studio" in spec:
                set_studio_values(material, spec["studio"])
            mesh.materials.append(material)

        for polygon in mesh.polygons:
            polygon.material_index = min(polygon.index, len(specs) - 1)

        obj = bpy.data.objects.new("Correctness Object", mesh)
        bpy.context.scene.collection.objects.link(obj)
        yield obj
    finally:
        if obj is not None:
            bpy.data.objects.remove(obj, do_unlink=True)
        bpy.data.meshes.remove(mesh)
        for material in created_materials:
            bpy.data.materials.remove(material)


def export(extension, export_path, **keywords):
    keywords.setdefault("global_matrix", Matrix.Identity(4))
    keywords.setdefault("use_mesh_modifiers", False)
    keywords.setdefault("geometry_reuse", "OFF")
    result = extension.export_vrml2.save(
        Operator(),
        bpy.context,
        filepath=str(export_path),
        **keywords,
    )
    assert result == {"FINISHED"}, result
    return export_path.read_text(encoding="utf-8")


def texture_urls(content):
    for line in content.splitlines():
        stripped = line.strip()
        if stripped.startswith("url ["):
            return stripped[len("url ["):].rsplit("]", 1)[0].strip()
    raise AssertionError(f"No ImageTexture url was written:\n{content}")


@contextmanager
def scenario(root, name, texture_subdirectory):
    """Lay out one self-contained blend/texture/export tree."""
    scenario_root = root / name
    texture_directory = scenario_root / texture_subdirectory
    export_directory = scenario_root / "export"
    export_directory.mkdir(parents=True, exist_ok=True)
    texture_directory.mkdir(parents=True, exist_ok=True)
    # Saving the blend inside the tree makes Blender's '//' prefix and the
    # exporter's base_src resolve to this directory rather than to whatever the
    # test happened to inherit.
    bpy.ops.wm.save_as_mainfile(filepath=str(scenario_root / "scene.blend"))
    yield texture_directory, export_directory


def check_path_modes(extension, root):
    """Every mode must write the reference Blender resolved, and nothing more.

    The exporter used to append its own absolute source path on top of that
    reference, which contradicted the selected mode and recorded the exporting
    machine's directory layout in the file.
    """
    checks = 0

    # 1. Absolute stored path, texture outside the export directory.
    with scenario(root, "outside", "source textures") as (
        texture_directory, export_directory
    ):
        absolute = str(texture_directory / TEXTURE_NAME)
        expected = {
            # Blender legitimately resolves these to the absolute reference.
            "AUTO": f'"{absolute}" "{TEXTURE_NAME}"',
            "ABSOLUTE": f'"{absolute}" "{TEXTURE_NAME}"',
            # The stored path is absolute, so Match must mean Absolute.
            "MATCH": f'"{absolute}" "{TEXTURE_NAME}"',
            # Relative may traverse upwards. That is a relative reference, not
            # an absolute path the exporter added.
            "RELATIVE": f'"../source textures/{TEXTURE_NAME}" "{TEXTURE_NAME}"',
            "STRIP": f'"{TEXTURE_NAME}"',
            "COPY": f'"textures/{TEXTURE_NAME}" "{TEXTURE_NAME}"',
        }
        with texture_image(texture_directory, absolute) as image:
            with textured_object(image):
                checks += check_modes(
                    extension, export_directory, expected, texture_directory,
                    leak_free=("STRIP", "COPY"),
                )
            copied = export_directory / "textures" / TEXTURE_NAME
            assert copied.is_file(), copied

    # 2. Absolute stored path, texture already inside the export directory.
    #    Auto resolves to Relative here, and used to be given an absolute
    #    alternative anyway, so this is not only a Strip/Copy problem.
    with scenario(root, "inside", "export/textures") as (
        texture_directory, export_directory
    ):
        absolute = str(texture_directory / TEXTURE_NAME)
        expected = {
            "AUTO": f'"textures/{TEXTURE_NAME}" "{TEXTURE_NAME}"',
            "ABSOLUTE": f'"{absolute}" "{TEXTURE_NAME}"',
            "MATCH": f'"{absolute}" "{TEXTURE_NAME}"',
            "RELATIVE": f'"textures/{TEXTURE_NAME}" "{TEXTURE_NAME}"',
            "STRIP": f'"{TEXTURE_NAME}"',
            "COPY": f'"textures/{TEXTURE_NAME}" "{TEXTURE_NAME}"',
        }
        with texture_image(texture_directory, absolute) as image:
            with textured_object(image):
                checks += check_modes(
                    extension, export_directory, expected, texture_directory,
                    leak_free=("AUTO", "RELATIVE", "STRIP", "COPY"),
                )

    # 3. Blender-relative '//' stored path. Match must follow the stored form
    #    and resolve relative, which only works if the writer hands
    #    path_reference the stored path instead of an absolute one.
    with scenario(root, "relative", "source textures") as (
        texture_directory, export_directory
    ):
        absolute = str(texture_directory / TEXTURE_NAME)
        expected = {
            "AUTO": f'"{absolute}" "{TEXTURE_NAME}"',
            "ABSOLUTE": f'"{absolute}" "{TEXTURE_NAME}"',
            "MATCH": f'"../source textures/{TEXTURE_NAME}" "{TEXTURE_NAME}"',
            "RELATIVE": f'"../source textures/{TEXTURE_NAME}" "{TEXTURE_NAME}"',
            "STRIP": f'"{TEXTURE_NAME}"',
            "COPY": f'"textures/{TEXTURE_NAME}" "{TEXTURE_NAME}"',
        }
        stored = f"//source textures/{TEXTURE_NAME}"
        with texture_image(texture_directory, stored) as image:
            assert image.filepath.startswith("//"), image.filepath
            with textured_object(image):
                checks += check_modes(
                    extension, export_directory, expected, texture_directory,
                    leak_free=("MATCH", "RELATIVE", "STRIP", "COPY"),
                )

    assert checks == 3 * len(PATH_MODES), checks


def check_modes(extension, export_directory, expected, texture_directory, leak_free):
    """Assert the emitted url list for every path mode in one scenario."""
    export_path = export_directory / "correctness.wrl"
    assert set(expected) == set(PATH_MODES), sorted(expected)
    for path_mode in PATH_MODES:
        content = export(
            extension,
            export_path,
            use_color=True,
            color_type="MATERIAL",
            use_uv=True,
            path_mode=path_mode,
        )
        urls = texture_urls(content)
        assert urls == expected[path_mode], (path_mode, urls, expected[path_mode])
        if path_mode in leak_free:
            # No mode that resolved to something portable may still carry the
            # source directory of the exporting machine.
            assert str(texture_directory) not in content, (path_mode, urls)
    return len(PATH_MODES)


STUDIO_ONE = {
    "diffuse_color": (0.1, 0.2, 0.3),
    "emissive_color": (0.01, 0.02, 0.03),
    "specular_color": (0.4, 0.5, 0.6),
    "ambient_intensity": 0.25,
    "shininess": 0.7,
    "transparency": 0.1,
}
STUDIO_TWO = {
    "diffuse_color": (0.7, 0.6, 0.5),
    "emissive_color": (0.03, 0.02, 0.01),
    "specular_color": (0.3, 0.2, 0.1),
    "ambient_intensity": 0.4,
    "shininess": 0.8,
    "transparency": 0.2,
}


def check_textured_shape_is_lit(extension, root):
    """A textured Shape must still carry a material node so it stays lit.

    VRML97 4.14.2 makes a Shape unlit when Appearance.material is NULL, and
    table 4.5 then draws an RGB texture flat at full brightness rather than
    shading it. Every textured Appearance therefore needs a material field, but
    only the cases with no material of their own may fall back to an empty one.
    """
    with scenario(root, "lighting", "lighting textures") as (
        texture_directory, export_directory
    ):
        export_path = export_directory / "lighting.wrl"
        cases = (
            # label, use_color, color_type, colour attribute, materials,
            # expected Shapes, expected material fields, expected empty ones
            ("vertex colours", True, "VERTEX", True, (), 1, 1, 1),
            ("colours disabled", False, "MATERIAL", False, (), 1, 1, 1),
            ("ordinary single material", True, "MATERIAL", False,
             ({"name": "Plain"},), 1, 1, 0),
            ("studio single material", True, "MATERIAL", False,
             ({"name": "Studio", "studio": STUDIO_ONE},), 1, 1, 0),
            ("multiple ordinary materials", True, "MATERIAL", False,
             ({"name": "Plain A"}, {"name": "Plain B"}), 1, 1, 1),
            ("split studio materials", True, "MATERIAL", False,
             ({"name": "Studio A", "studio": STUDIO_ONE},
              {"name": "Studio B", "studio": STUDIO_TWO}), 2, 2, 0),
        )
        absolute = str(texture_directory / TEXTURE_NAME)
        with texture_image(texture_directory, absolute) as image:
            for (
                label, use_color, color_type, with_color_attribute, materials,
                shapes, material_fields, empty_materials,
            ) in cases:
                with textured_object(
                    image,
                    with_color_attribute=with_color_attribute,
                    materials=materials,
                ):
                    content = export(
                        extension,
                        export_path,
                        use_color=use_color,
                        color_type=color_type,
                        use_uv=True,
                        path_mode="STRIP",
                    )
                assert content.count("Shape {") == shapes, (label, content)
                assert content.count("texture ImageTexture {") == shapes, (
                    label, content,
                )
                # Every Appearance carries exactly one material field: never
                # zero, which would be unlit, and never two.
                assert content.count("material Material {") == material_fields, (
                    label, content,
                )
                assert content.count(EMPTY_MATERIAL) == empty_materials, (
                    label, content,
                )

        # The Studio values must survive rather than being replaced by the
        # empty fallback.
        assert "shininess 0.7" in content, content
        assert "shininess 0.8" in content, content
        assert "diffuseColor 0.1 0.2 0.3" in content, content


def main():
    extension = load_extension()
    clear_scene()
    with tempfile.TemporaryDirectory(prefix="vrml2-correctness-") as temporary:
        root = Path(temporary)
        try:
            check_path_modes(extension, root)
            check_textured_shape_is_lit(extension, root)
        finally:
            # Leave no fixture behind for a following run, whether or not an
            # assertion above failed.
            clear_scene()
    print("Blender texture path mode and Shape lighting integration test passed.")


if __name__ == "__main__":
    main()
