# SPDX-License-Identifier: GPL-2.0-or-later
#
# Original VRML2 exporter by Campbell Barton.
# Current extension packaging and compatibility maintenance are provided by
# the maintainer identified in blender_manifest.toml.

"""Blender Extension entry point for the VRML2 exporter."""

_needs_reload = "bpy" in locals()

import importlib
import traceback

import bpy
from bpy.props import BoolProperty, EnumProperty, FloatProperty, StringProperty
from bpy_extras.io_utils import (
    ExportHelper,
    axis_conversion,
    orientation_helper,
    path_reference_mode,
)

from . import export_vrml2

if _needs_reload:
    export_vrml2 = importlib.reload(export_vrml2)


@orientation_helper(axis_forward="Z", axis_up="Y")
class ExportVRML(bpy.types.Operator, ExportHelper):
    """Export mesh objects to a VRML 2.0 file."""

    bl_idname = "export_scene.vrml2"
    bl_label = "Export VRML2"
    bl_description = "Export mesh objects as VRML 2.0 with colors and textures"
    bl_options = {"PRESET"}

    filename_ext = ".wrl"
    filter_glob: StringProperty(default="*.wrl", options={"HIDDEN"})

    use_selection: BoolProperty(
        name="Selection Only",
        description="Export selected objects only",
        default=False,
    )

    use_mesh_modifiers: BoolProperty(
        name="Apply Modifiers",
        description="Export the evaluated mesh with modifiers applied",
        default=True,
    )

    use_color: BoolProperty(
        name="Colors",
        description="Export the active color attribute or material colors",
        default=True,
    )

    color_type: EnumProperty(
        name="Color Source",
        items=(
            ("VERTEX", "Color Attribute", "Use the active mesh color attribute"),
            ("MATERIAL", "Material Color", "Use material viewport colors"),
        ),
        default="VERTEX",
    )

    use_uv: BoolProperty(
        name="Texture and UVs",
        description="Export the active UV map and a referenced image texture",
        default=True,
    )

    global_scale: FloatProperty(
        name="Scale",
        description="Scale exported coordinates",
        min=0.01,
        max=1000.0,
        default=1.0,
    )

    path_mode: path_reference_mode

    @classmethod
    def poll(cls, context):
        scene = getattr(context, "scene", None)
        return scene is not None and any(obj.type == "MESH" for obj in scene.objects)

    def execute(self, context):
        from mathutils import Matrix

        keywords = self.as_keywords(
            ignore=(
                "axis_forward",
                "axis_up",
                "global_scale",
                "check_existing",
                "filter_glob",
            )
        )

        global_matrix = (
            axis_conversion(
                to_forward=self.axis_forward,
                to_up=self.axis_up,
            ).to_4x4()
            @ Matrix.Scale(self.global_scale, 4)
        )
        keywords["global_matrix"] = global_matrix

        self.filepath = bpy.path.ensure_ext(self.filepath, self.filename_ext)

        try:
            return export_vrml2.save(self, context, **keywords)
        except Exception as exc:  # Blender should show a useful error instead of failing silently.
            self.report({"ERROR"}, f"VRML2 export failed: {exc}")
            traceback.print_exc()
            return {"CANCELLED"}

    def draw(self, context):
        del context
        layout = self.layout

        layout.prop(self, "use_selection")
        layout.prop(self, "use_mesh_modifiers")

        row = layout.row(align=True)
        row.prop(self, "use_uv")
        row.prop(self, "use_color")

        row = layout.row()
        row.active = self.use_color
        row.prop(self, "color_type")

        layout.separator()
        layout.prop(self, "axis_forward")
        layout.prop(self, "axis_up")
        layout.prop(self, "global_scale")
        layout.prop(self, "path_mode")


def menu_func_export(self, context):
    del context
    self.layout.operator(ExportVRML.bl_idname, text="VRML2 (.wrl)")


classes = (ExportVRML,)


def register():
    for cls in classes:
        bpy.utils.register_class(cls)
    bpy.types.TOPBAR_MT_file_export.append(menu_func_export)


def unregister():
    bpy.types.TOPBAR_MT_file_export.remove(menu_func_export)
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)


if __name__ == "__main__":
    register()
