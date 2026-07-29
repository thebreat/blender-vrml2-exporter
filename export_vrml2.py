# SPDX-License-Identifier: GPL-2.0-or-later
#
# Original VRML2 exporter by Campbell Barton.
# Current extension packaging and compatibility maintenance are provided by
# thebreat.

"""VRML 2.0 mesh writer used by the Blender export operator."""

import os

import bmesh
import bpy
import bpy_extras


def _guess_object_image(obj):
    """Return the first usable image texture from an object's materials."""
    for slot in obj.material_slots:
        material = slot.material
        if material is None or not material.use_nodes or material.node_tree is None:
            continue

        active_node = getattr(material.node_tree.nodes, "active", None)
        if (
            active_node is not None
            and active_node.type == "TEX_IMAGE"
            and getattr(active_node, "image", None) is not None
        ):
            return active_node.image

        for node in material.node_tree.nodes:
            if node.type == "TEX_IMAGE" and getattr(node, "image", None) is not None:
                return node.image

    return None


def _layer_by_name(layer_collection, name):
    """Look up a BMesh custom-data layer without assuming a specific API shape."""
    get_layer = getattr(layer_collection, "get", None)
    if get_layer is not None:
        layer = get_layer(name)
        if layer is not None:
            return layer

    try:
        return layer_collection[name]
    except (KeyError, TypeError):
        return None


def _active_mesh_color_info(mesh):
    """Return (name, domain, data_type) for the active mesh color attribute."""
    color_attributes = getattr(mesh, "color_attributes", None)
    if color_attributes is None:
        return None

    attribute = getattr(color_attributes, "active_color", None)
    if attribute is None:
        attribute = getattr(color_attributes, "active", None)
    if attribute is None:
        return None

    return (
        attribute.name,
        getattr(attribute, "domain", "CORNER"),
        getattr(attribute, "data_type", "BYTE_COLOR"),
    )


def _active_color_layer(bm, mesh=None):
    """Return (domain, layer) for point- or corner-domain mesh colors."""
    color_info = _active_mesh_color_info(mesh) if mesh is not None else None
    if color_info is not None:
        name, domain, data_type = color_info
        elements = bm.verts if domain == "POINT" else bm.loops if domain == "CORNER" else None
        if elements is not None:
            preferred_types = (
                ("float_color", "color")
                if data_type == "FLOAT_COLOR"
                else ("color", "float_color")
            )
            for layer_type in preferred_types:
                collection = getattr(elements.layers, layer_type, None)
                if collection is None:
                    continue
                layer = _layer_by_name(collection, name)
                if layer is not None:
                    return domain, layer

    # Compatibility fallback for meshes where active color metadata is unavailable.
    for domain, elements in (("CORNER", bm.loops), ("POINT", bm.verts)):
        for layer_type in ("float_color", "color"):
            collection = getattr(elements.layers, layer_type, None)
            if collection is None:
                continue
            layer = getattr(collection, "active", None)
            if layer is not None:
                return domain, layer

    return None, None


def _vrml_quote(value):
    """Quote and normalize a path for a VRML string literal."""
    text = os.fspath(value).replace("\\", "/")
    text = text.replace("\r", "").replace("\n", "")
    text = text.replace('"', '\\"')
    return f'"{text}"'


def _unique_strings(values):
    """Return non-empty strings in order, without duplicates."""
    result = []
    seen = set()
    for value in values:
        if not value or value in seen:
            continue
        seen.add(value)
        result.append(value)
    return result


def _write_face_indices(fw, faces, index_for_loop):
    for face in faces:
        for loop in face.loops:
            fw(f"{index_for_loop(loop)} ")
        fw("-1 ")


def save_bmesh(
    fw,
    bm,
    base_dst,
    use_color,
    color_type,
    material_colors,
    color_domain,
    color_layer,
    use_uv,
    uv_image,
    path_mode,
    copy_set,
):
    """Write one triangulated BMesh as a VRML Shape node."""
    base_src = os.path.dirname(bpy.data.filepath) or os.getcwd()

    fw("Shape {\n")
    fw("\tappearance Appearance {\n")
    if use_uv:
        filepath = uv_image.filepath
        filepath_full = os.path.normpath(
            bpy.path.abspath(filepath, library=uv_image.library)
        )
        filepath_ref = bpy_extras.io_utils.path_reference(
            filepath_full,
            base_src,
            base_dst,
            path_mode,
            "textures",
            copy_set,
            uv_image.library,
        )
        filepath_base = os.path.basename(filepath_full)

        image_urls = [filepath_ref, filepath_base]
        if path_mode != "RELATIVE":
            image_urls.append(filepath_full)
        image_urls = _unique_strings(image_urls)

        fw("\t\ttexture ImageTexture {\n")
        fw("\t\t\turl [ %s ]\n" % " ".join(_vrml_quote(url) for url in image_urls))
        fw("\t\t}\n")
    else:
        fw("\t\tmaterial Material {\n")
        fw("\t\t}\n")
    fw("\t}\n")

    fw("\tgeometry IndexedFaceSet {\n")
    fw("\t\tcoord Coordinate {\n")
    fw("\t\t\tpoint [ ")
    for vertex in bm.verts:
        fw("%.6f %.6f %.6f " % tuple(vertex.co[:3]))
    fw("]\n")
    fw("\t\t}\n")

    if use_color:
        if color_type == "MATERIAL":
            fw("\t\tcolorPerVertex FALSE\n")
            fw("\t\tcolor Color {\n")
            fw("\t\t\tcolor [ ")
            for color in material_colors:
                fw("%.4f %.4f %.4f " % color)
            fw("]\n")
            fw("\t\t}\n")

            fw("\t\tcolorIndex [ ")
            for face in bm.faces:
                material_index = face.material_index
                if material_index >= len(material_colors):
                    material_index = 0
                fw(f"{material_index} ")
            fw("]\n")

        elif color_type == "VERTEX":
            fw("\t\tcolorPerVertex TRUE\n")
            fw("\t\tcolor Color {\n")
            fw("\t\t\tcolor [ ")

            if color_domain == "POINT":
                for vertex in bm.verts:
                    fw("%.4f %.4f %.4f " % tuple(vertex[color_layer][:3]))
            else:
                for face in bm.faces:
                    for loop in face.loops:
                        fw("%.4f %.4f %.4f " % tuple(loop[color_layer][:3]))

            fw("]\n")
            fw("\t\t}\n")

            if color_domain == "CORNER":
                fw("\t\tcolorIndex [ ")
                color_index = 0
                for face in bm.faces:
                    for _loop in face.loops:
                        fw(f"{color_index} ")
                        color_index += 1
                    fw("-1 ")
                fw("]\n")

    if use_uv:
        uv_layer = bm.loops.layers.uv.active
        fw("\t\ttexCoord TextureCoordinate {\n")
        fw("\t\t\tpoint [ ")
        for face in bm.faces:
            for loop in face.loops:
                fw("%.6f %.6f " % tuple(loop[uv_layer].uv[:2]))
        fw("]\n")
        fw("\t\t}\n")

        fw("\t\ttexCoordIndex [ ")
        texture_index = 0
        for face in bm.faces:
            for _loop in face.loops:
                fw(f"{texture_index} ")
                texture_index += 1
            fw("-1 ")
        fw("]\n")

    fw("\t\tcoordIndex [ ")
    _write_face_indices(fw, bm.faces, lambda loop: loop.vert.index)
    fw("]\n")

    fw("\t}\n")
    fw("}\n")


def save_object(
    fw,
    global_matrix,
    obj,
    base_dst,
    use_mesh_modifiers,
    use_color,
    color_type,
    use_uv,
    path_mode,
    copy_set,
):
    """Evaluate and export a single mesh object."""
    if obj.type != "MESH":
        raise TypeError(f"Expected a mesh object, got {obj.type!r}")

    obj_eval = None
    bm = None
    try:
        if use_mesh_modifiers:
            if obj.mode == "EDIT":
                obj.update_from_editmode()

            depsgraph = bpy.context.evaluated_depsgraph_get()
            obj_eval = obj.evaluated_get(depsgraph)
            mesh = obj_eval.to_mesh(
                preserve_all_data_layers=True,
                depsgraph=depsgraph,
            )
            bm = bmesh.new()
            bm.from_mesh(mesh)
        else:
            mesh = obj.data
            if obj.mode == "EDIT":
                bm = bmesh.from_edit_mesh(mesh).copy()
            else:
                bm = bmesh.new()
                bm.from_mesh(mesh)

        bmesh.ops.triangulate(bm, faces=list(bm.faces))
        object_matrix = obj_eval.matrix_world if obj_eval is not None else obj.matrix_world
        bm.transform(global_matrix @ object_matrix)
        bm.verts.index_update()
        bm.faces.index_update()

        material_colors = []
        color_domain = None
        color_layer = None
        uv_image = None

        if use_color:
            if color_type == "VERTEX":
                color_domain, color_layer = _active_color_layer(bm, mesh)
                if color_layer is None:
                    color_type = "MATERIAL"

            if color_type == "MATERIAL":
                if not mesh.materials:
                    use_color = False
                else:
                    material_colors = [
                        tuple(material.diffuse_color[:3])
                        if material is not None
                        else (1.0, 1.0, 1.0)
                        for material in mesh.materials
                    ]

        if use_uv:
            if bm.loops.layers.uv.active is None:
                use_uv = False
            else:
                uv_image = _guess_object_image(obj)
                if uv_image is None or not getattr(uv_image, "filepath", ""):
                    use_uv = False

        save_bmesh(
            fw,
            bm,
            base_dst,
            use_color,
            color_type,
            material_colors,
            color_domain,
            color_layer,
            use_uv,
            uv_image,
            path_mode,
            copy_set,
        )
    finally:
        if bm is not None:
            bm.free()
        if obj_eval is not None:
            obj_eval.to_mesh_clear()


def save(
    operator,
    context,
    filepath="",
    global_matrix=None,
    use_selection=False,
    use_mesh_modifiers=True,
    use_color=True,
    color_type="MATERIAL",
    use_uv=True,
    path_mode="AUTO",
):
    """Export mesh objects from the current context to a VRML 2.0 file."""
    if global_matrix is None:
        from mathutils import Matrix

        global_matrix = Matrix.Identity(4)

    scene = context.scene
    source_objects = context.selected_objects if use_selection else scene.objects
    mesh_objects = [obj for obj in source_objects if obj.type == "MESH"]

    if not mesh_objects:
        operator.report({"WARNING"}, "No mesh objects were available to export")
        return {"CANCELLED"}

    copy_set = set()
    base_dst = os.path.dirname(os.path.abspath(filepath)) or os.getcwd()

    with open(filepath, "w", encoding="utf-8", newline="\n") as file:
        fw = file.write
        fw("#VRML V2.0 utf8\n")
        fw("# Exported from Blender with the VRML2 Exporter extension\n")

        for obj in mesh_objects:
            fw("\n# Object: %r\n" % obj.name)
            save_object(
                fw,
                global_matrix,
                obj,
                base_dst,
                use_mesh_modifiers,
                use_color,
                color_type,
                use_uv,
                path_mode,
                copy_set,
            )

    bpy_extras.io_utils.path_reference_copy(copy_set)
    operator.report({"INFO"}, f"Exported {len(mesh_objects)} mesh object(s) to VRML2")
    return {"FINISHED"}
