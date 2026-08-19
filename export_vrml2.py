# SPDX-License-Identifier: GPL-2.0-or-later
#
# Original VRML2 exporter by Campbell Barton.
# Current extension packaging and compatibility maintenance are provided by
# thebreat.

"""VRML 2.0 mesh writer used by the Blender export operator."""

import hashlib
import io
import os
import stat
import tempfile

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


def _write_indexed_face_set(
    fw,
    bm,
    use_color,
    color_type,
    material_colors,
    color_domain,
    color_layer,
    use_uv,
):
    """Write the reusable geometry portion of a VRML Shape node."""
    fw("IndexedFaceSet {\n")
    fw("\tcoord Coordinate {\n")
    fw("\t\tpoint [ ")
    for vertex in bm.verts:
        fw("%.6f %.6f %.6f " % tuple(vertex.co[:3]))
    fw("]\n")
    fw("\t}\n")

    if use_color:
        if color_type == "MATERIAL":
            fw("\tcolorPerVertex FALSE\n")
            fw("\tcolor Color {\n")
            fw("\t\tcolor [ ")
            for color in material_colors:
                fw("%.4f %.4f %.4f " % color)
            fw("]\n")
            fw("\t}\n")

            fw("\tcolorIndex [ ")
            for face in bm.faces:
                material_index = face.material_index
                if material_index >= len(material_colors):
                    material_index = 0
                fw(f"{material_index} ")
            fw("]\n")

        elif color_type == "VERTEX":
            fw("\tcolorPerVertex TRUE\n")
            fw("\tcolor Color {\n")
            fw("\t\tcolor [ ")

            if color_domain == "POINT":
                for vertex in bm.verts:
                    fw("%.4f %.4f %.4f " % tuple(vertex[color_layer][:3]))
            else:
                for face in bm.faces:
                    for loop in face.loops:
                        fw("%.4f %.4f %.4f " % tuple(loop[color_layer][:3]))

            fw("]\n")
            fw("\t}\n")

            if color_domain == "CORNER":
                fw("\tcolorIndex [ ")
                color_index = 0
                for face in bm.faces:
                    for _loop in face.loops:
                        fw(f"{color_index} ")
                        color_index += 1
                    fw("-1 ")
                fw("]\n")

    if use_uv:
        uv_layer = bm.loops.layers.uv.active
        fw("\ttexCoord TextureCoordinate {\n")
        fw("\t\tpoint [ ")
        for face in bm.faces:
            for loop in face.loops:
                fw("%.6f %.6f " % tuple(loop[uv_layer].uv[:2]))
        fw("]\n")
        fw("\t}\n")

        fw("\ttexCoordIndex [ ")
        texture_index = 0
        for face in bm.faces:
            for _loop in face.loops:
                fw(f"{texture_index} ")
                texture_index += 1
            fw("-1 ")
        fw("]\n")

    fw("\tcoordIndex [ ")
    _write_face_indices(fw, bm.faces, lambda loop: loop.vert.index)
    fw("]\n")
    fw("}\n")


def _indent_after_first_line(text, indent):
    """Indent a generated VRML block while keeping its first line inline."""
    lines = text.splitlines(keepends=True)
    if not lines:
        return text
    return lines[0] + "".join(indent + line for line in lines[1:])


def _decompose_vrml_transform(matrix):
    """Return a VRML-compatible transform, or None for shear/reflection cases."""
    translation, rotation, scale = matrix.decompose()
    if any(component <= 0.0 for component in scale):
        return None

    rotation_matrix = rotation.to_matrix()
    magnitude = max(1.0, *(abs(value) for row in matrix for value in row))
    tolerance = 1.0e-5 * magnitude
    for row in range(4):
        for column in range(4):
            if row < 3 and column < 3:
                expected = rotation_matrix[row][column] * scale[column]
            elif row < 3 and column == 3:
                expected = translation[row]
            else:
                expected = 1.0 if row == column else 0.0
            if abs(matrix[row][column] - expected) > tolerance:
                return None

    axis, angle = rotation.to_axis_angle()
    if abs(angle) < 1.0e-10:
        axis = (0.0, 0.0, 1.0)
        angle = 0.0

    return tuple(translation), tuple(axis), angle, tuple(scale)


def _write_transform_start(fw, transform):
    translation, axis, angle, scale = transform
    fw("Transform {\n")
    fw("\ttranslation %.6f %.6f %.6f\n" % translation)
    fw("\trotation %.6f %.6f %.6f %.6f\n" % (*axis, angle))
    fw("\tscale %.6f %.6f %.6f\n" % scale)
    fw("\tchildren [\n")


def _remove_unused_geometry_defs(filepath, geometry_cache):
    """Remove DEF names that were never referenced by a USE statement."""
    unused_names = {
        entry["name"]
        for entry in geometry_cache.values()
        if entry["occurrences"] == 1
    }
    if not unused_names:
        return

    original_mode = stat.S_IMODE(os.stat(filepath).st_mode)
    output_directory = os.path.dirname(os.path.abspath(filepath)) or os.getcwd()
    fd, temporary_path = tempfile.mkstemp(
        prefix=".vrml2-export-",
        suffix=".wrl",
        dir=output_directory,
        text=True,
    )
    try:
        with open(filepath, "r", encoding="utf-8", newline="") as source_file:
            with os.fdopen(fd, "w", encoding="utf-8", newline="") as output_file:
                for line in source_file:
                    stripped_line = line.lstrip(" \t")
                    if stripped_line.startswith("geometry DEF "):
                        indentation = line[:len(line) - len(stripped_line)]
                        definition = stripped_line[len("geometry DEF "):]
                        geometry_name, separator, geometry_text = definition.partition(" ")
                        if separator and geometry_name in unused_names:
                            line = f"{indentation}geometry {geometry_text}"
                    output_file.write(line)
        os.chmod(temporary_path, original_mode)
        os.replace(temporary_path, filepath)
    except Exception:
        try:
            os.close(fd)
        except OSError:
            pass
        try:
            os.unlink(temporary_path)
        except OSError:
            pass
        raise


def _mesh_data_identity(obj):
    """Return an export-session identity for an object's original mesh data."""
    mesh = obj.data
    as_pointer = getattr(mesh, "as_pointer", None)
    return as_pointer() if as_pointer is not None else id(mesh)


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
    geometry_cache=None,
    geometry_group=None,
    indent="",
):
    """Write one triangulated BMesh as a VRML Shape node."""
    base_src = os.path.dirname(bpy.data.filepath) or os.getcwd()

    fw(f"{indent}Shape {{\n")
    fw(f"{indent}\tappearance Appearance {{\n")
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

        fw(f"{indent}\t\ttexture ImageTexture {{\n")
        fw(
            f"{indent}\t\t\turl [ %s ]\n"
            % " ".join(_vrml_quote(url) for url in image_urls)
        )
        fw(f"{indent}\t\t}}\n")
    else:
        fw(f"{indent}\t\tmaterial Material {{\n")
        fw(f"{indent}\t\t}}\n")
    fw(f"{indent}\t}}\n")

    geometry_buffer = io.StringIO()
    _write_indexed_face_set(
        geometry_buffer.write,
        bm,
        use_color,
        color_type,
        material_colors,
        color_domain,
        color_layer,
        use_uv,
    )
    geometry_text = geometry_buffer.getvalue()
    geometry_indent = f"{indent}\t"
    reused = False

    if geometry_cache is None:
        fw(f"{geometry_indent}geometry ")
        fw(_indent_after_first_line(geometry_text, geometry_indent))
    else:
        geometry_digest = hashlib.sha256(geometry_text.encode("utf-8")).digest()
        cache_key = (geometry_group, geometry_digest)
        cache_entry = geometry_cache.get(cache_key)
        if cache_entry is None:
            geometry_name = f"Geometry_{len(geometry_cache) + 1}"
            geometry_cache[cache_key] = {
                "name": geometry_name,
                "occurrences": 1,
            }
            fw(f"{geometry_indent}geometry DEF {geometry_name} ")
            fw(_indent_after_first_line(geometry_text, geometry_indent))
        else:
            geometry_name = cache_entry["name"]
            cache_entry["occurrences"] += 1
            fw(f"{geometry_indent}geometry USE {geometry_name}\n")
            reused = True

    fw(f"{indent}}}\n")
    return reused


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
    geometry_cache,
    geometry_group,
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
        export_matrix = global_matrix @ object_matrix
        transform = (
            _decompose_vrml_transform(export_matrix)
            if geometry_cache is not None
            else None
        )
        if transform is None:
            bm.transform(export_matrix)
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

        if transform is not None:
            _write_transform_start(fw, transform)

        reusable_geometry_cache = geometry_cache if transform is not None else None
        reused = save_bmesh(
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
            reusable_geometry_cache,
            geometry_group if reusable_geometry_cache is not None else None,
            "\t\t" if transform is not None else "",
        )
        if transform is not None:
            fw("\t]\n")
            fw("}\n")
        return reused
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
    geometry_reuse="LINKED",
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
    if geometry_reuse not in {"LINKED", "IDENTICAL", "OFF"}:
        raise ValueError(f"Unknown geometry reuse mode: {geometry_reuse!r}")

    geometry_cache = {} if geometry_reuse != "OFF" else None
    mesh_data_counts = {}
    if geometry_reuse == "LINKED":
        for obj in mesh_objects:
            mesh_key = _mesh_data_identity(obj)
            mesh_data_counts[mesh_key] = mesh_data_counts.get(mesh_key, 0) + 1
    reused_geometry_count = 0
    base_dst = os.path.dirname(os.path.abspath(filepath)) or os.getcwd()

    with open(filepath, "w", encoding="utf-8", newline="\n") as file:
        fw = file.write
        fw("#VRML V2.0 utf8\n")
        fw("# Exported from Blender with the VRML2 Exporter extension\n")

        for obj in mesh_objects:
            fw("\n# Object: %r\n" % obj.name)
            object_geometry_cache = geometry_cache
            geometry_group = "IDENTICAL" if geometry_reuse == "IDENTICAL" else None
            if geometry_reuse == "LINKED":
                mesh_key = _mesh_data_identity(obj)
                if mesh_data_counts[mesh_key] < 2:
                    object_geometry_cache = None
                    geometry_group = None
                else:
                    geometry_group = ("LINKED", mesh_key)
            reused_geometry_count += save_object(
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
                object_geometry_cache,
                geometry_group,
            )

    if geometry_cache is not None:
        _remove_unused_geometry_defs(filepath, geometry_cache)

    bpy_extras.io_utils.path_reference_copy(copy_set)
    message = f"Exported {len(mesh_objects)} mesh object(s) to VRML2"
    if reused_geometry_count:
        message += f"; reused {reused_geometry_count} geometries with DEF/USE"
    operator.report({"INFO"}, message)
    return {"FINISHED"}
