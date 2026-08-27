# SPDX-License-Identifier: GPL-2.0-or-later
#
# Original VRML2 exporter by Campbell Barton.
# Current extension packaging and compatibility maintenance are provided by
# thebreat.

"""VRML 2.0 mesh writer used by the Blender export operator."""

import gzip
import hashlib
import io
import math
import os
import stat
import tempfile

import bmesh
import bpy
import bpy_extras


_VRML2_MATERIAL_KEYS = {
    "initialized": "vrml2_initialized",
    "enabled": "vrml2_enabled",
    "diffuse_color": "vrml2_diffuseColor",
    "emissive_color": "vrml2_emissiveColor",
    "specular_color": "vrml2_specularColor",
    "ambient_intensity": "vrml2_ambientIntensity",
    "shininess": "vrml2_shininess",
    "transparency": "vrml2_transparency",
}

_VRML2_MATERIAL_DEFAULTS = {
    "diffuse_color": (0.8, 0.8, 0.8),
    "emissive_color": (0.0, 0.0, 0.0),
    "specular_color": (0.0, 0.0, 0.0),
    "ambient_intensity": 0.2,
    "shininess": 0.2,
    "transparency": 0.0,
}


def _clamp_material_value(value, default):
    """Return one finite VRML material value in the required 0..1 range."""
    try:
        number = float(value)
    except (TypeError, ValueError):
        number = float(default)
    if not math.isfinite(number):
        number = float(default)
    return min(1.0, max(0.0, number))


def _clamp_material_color(value, default):
    """Return three finite VRML material color values in the 0..1 range."""
    try:
        components = tuple(value)
    except TypeError:
        components = ()
    if len(components) < 3:
        components = default
    return tuple(
        _clamp_material_value(component, fallback)
        for component, fallback in zip(components[:3], default)
    )


def _material_studio_settings(material):
    """Read VRML2 Material Studio data without importing or requiring that add-on."""
    if material is None:
        return None
    try:
        initialized = bool(material.get(_VRML2_MATERIAL_KEYS["initialized"], False))
        enabled = bool(material.get(_VRML2_MATERIAL_KEYS["enabled"], False))
    except (AttributeError, TypeError):
        return None
    if not initialized or not enabled:
        return None

    settings = {}
    for field in ("diffuse_color", "emissive_color", "specular_color"):
        default = _VRML2_MATERIAL_DEFAULTS[field]
        settings[field] = _clamp_material_color(
            material.get(_VRML2_MATERIAL_KEYS[field], default),
            default,
        )
    for field in ("ambient_intensity", "shininess", "transparency"):
        default = _VRML2_MATERIAL_DEFAULTS[field]
        settings[field] = _clamp_material_value(
            material.get(_VRML2_MATERIAL_KEYS[field], default),
            default,
        )
    return settings


def _material_export_settings(material):
    """Return full Material Studio data or a compatible viewport-color fallback."""
    studio_settings = _material_studio_settings(material)
    if studio_settings is not None:
        return studio_settings

    if material is None:
        diffuse_color = (1.0, 1.0, 1.0)
    else:
        diffuse_color = getattr(material, "diffuse_color", (1.0, 1.0, 1.0))
    return {
        "diffuse_color": _clamp_material_color(
            diffuse_color,
            (1.0, 1.0, 1.0),
        )
    }


def _guess_material_image(material):
    """Return the first usable image texture from one Blender material."""
    if material is None or not material.use_nodes or material.node_tree is None:
        return None

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


def _guess_object_image(obj):
    """Return the first usable image texture from an object's materials."""
    for slot in obj.material_slots:
        image = _guess_material_image(slot.material)
        if image is not None:
            return image

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


def _format_float(value, decimals):
    """Round a VRML number without trailing zeroes or negative zero."""
    if abs(value) < 0.5 * 10 ** (-decimals):
        value = 0.0

    output = f"{value:.{decimals}f}"
    if "." in output:
        output = output.rstrip("0").rstrip(".")
    if output in {"", "-0"}:
        return "0"
    return output


def _triangle_area_squared(first, second, third):
    """Return four times a triangle's squared area using ordinary sequences."""
    ab = tuple(second[index] - first[index] for index in range(3))
    ac = tuple(third[index] - first[index] for index in range(3))
    cross = (
        ab[1] * ac[2] - ab[2] * ac[1],
        ab[2] * ac[0] - ab[0] * ac[2],
        ab[0] * ac[1] - ab[1] * ac[0],
    )
    return sum(component * component for component in cross)


def _coordinate_decimal_places(bm, requested, maximum=9):
    """Raise coordinate precision only when rounding would collapse a face."""
    for decimals in range(requested, maximum + 1):
        collapsed = False
        for face in bm.faces:
            coordinates = [tuple(loop.vert.co[:3]) for loop in face.loops]
            rounded = [
                tuple(round(value, decimals) for value in coordinate)
                for coordinate in coordinates
            ]
            for index in range(1, len(coordinates) - 1):
                original_area = _triangle_area_squared(
                    coordinates[0],
                    coordinates[index],
                    coordinates[index + 1],
                )
                rounded_area = _triangle_area_squared(
                    rounded[0],
                    rounded[index],
                    rounded[index + 1],
                )
                if original_area > 1.0e-30 and rounded_area <= 1.0e-30:
                    collapsed = True
                    break
            if collapsed:
                break
        if not collapsed:
            return decimals

    return maximum


def _uv_triangle_area(first, second, third):
    """Return twice the absolute area of a triangle in UV space."""
    return abs(
        (second[0] - first[0]) * (third[1] - first[1])
        - (second[1] - first[1]) * (third[0] - first[0])
    )


def _uv_decimal_places(bm, uv_layer, requested, maximum=9):
    """Raise UV precision only when rounding would collapse a mapped face."""
    for decimals in range(requested, maximum + 1):
        collapsed = False
        for face in bm.faces:
            coordinates = [tuple(loop[uv_layer].uv[:2]) for loop in face.loops]
            rounded = [
                tuple(round(value, decimals) for value in coordinate)
                for coordinate in coordinates
            ]
            for index in range(1, len(coordinates) - 1):
                original_area = _uv_triangle_area(
                    coordinates[0],
                    coordinates[index],
                    coordinates[index + 1],
                )
                rounded_area = _uv_triangle_area(
                    rounded[0],
                    rounded[index],
                    rounded[index + 1],
                )
                if original_area > 1.0e-15 and rounded_area <= 1.0e-15:
                    collapsed = True
                    break
            if collapsed:
                break
        if not collapsed:
            return decimals

    return maximum


def _transform_decimal_places(transform, requested, maximum=9):
    """Keep a positive transform scale from rounding down to zero."""
    scale = transform[3]
    for decimals in range(requested, maximum + 1):
        if all(_format_float(value, decimals) != "0" for value in scale):
            return decimals
    return maximum


def _nodes_modifier_input_value(modifier, identifier):
    """Read a Geometry Nodes modifier input across Blender API versions."""
    properties = getattr(modifier, "properties", None)
    inputs = getattr(properties, "inputs", None)
    if inputs is not None:
        input_property = getattr(inputs, identifier, None)
        if input_property is not None:
            value = getattr(input_property, "value", None)
            if value is not None:
                return value

    # Blender 4.2 through 5.1 stored Geometry Nodes inputs as system-defined
    # ID properties. Blender 5.2 exposes them through modifier.properties.
    get_value = getattr(modifier, "get", None)
    if get_value is not None:
        try:
            return get_value(identifier)
        except (KeyError, TypeError):
            pass
    return None


def _smooth_by_angle_modifier_angle(obj):
    """Return a visible Smooth by Angle modifier's angle in radians."""
    modifiers = getattr(obj, "modifiers", ())
    for modifier in reversed(modifiers):
        if (
            getattr(modifier, "type", None) != "NODES"
            or not getattr(modifier, "show_viewport", True)
        ):
            continue

        node_group = getattr(modifier, "node_group", None)
        if node_group is None:
            continue

        names = (
            getattr(modifier, "name", ""),
            getattr(node_group, "name", ""),
        )
        normalized_names = (
            name.casefold().replace("_", " ").replace("-", " ")
            for name in names
        )
        if not any("smooth by angle" in name for name in normalized_names):
            continue

        interface = getattr(node_group, "interface", None)
        for socket in getattr(interface, "items_tree", ()):
            if (
                getattr(socket, "item_type", "SOCKET") != "SOCKET"
                or getattr(socket, "in_out", "INPUT") != "INPUT"
                or getattr(socket, "name", "") != "Angle"
            ):
                continue

            identifier = getattr(socket, "identifier", "")
            if not identifier:
                continue
            angle = _nodes_modifier_input_value(modifier, identifier)
            if isinstance(angle, (int, float)):
                return min(math.pi, max(0.0, float(angle)))

    return None


def _crease_angle_for_mesh(obj, bm, use_mesh_modifiers):
    """Map Blender's smooth shading state to a VRML crease angle in radians."""
    if use_mesh_modifiers:
        modifier_angle = _smooth_by_angle_modifier_angle(obj)
        if modifier_angle is not None:
            return modifier_angle

    faces = list(bm.faces)
    if faces and all(getattr(face, "smooth", False) for face in faces):
        return math.pi
    return 0.0


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
    decimal_places,
    deduplicate_uvs,
    crease_angle,
):
    """Write the reusable geometry portion of a VRML Shape node."""
    coordinate_decimals = _coordinate_decimal_places(bm, decimal_places)
    color_decimals = min(decimal_places, 4)

    fw("IndexedFaceSet {\n")
    if crease_angle > 0.0:
        angle_decimals = max(decimal_places, 6)
        fw(f"\tcreaseAngle {_format_float(crease_angle, angle_decimals)}\n")
    fw("\tcoord Coordinate {\n")
    fw("\t\tpoint [ ")
    for vertex in bm.verts:
        fw(
            "%s %s %s "
            % tuple(
                _format_float(value, coordinate_decimals)
                for value in vertex.co[:3]
            )
        )
    fw("]\n")
    fw("\t}\n")

    if use_color:
        if color_type == "MATERIAL":
            fw("\tcolorPerVertex FALSE\n")
            fw("\tcolor Color {\n")
            fw("\t\tcolor [ ")
            for color in material_colors:
                fw(
                    "%s %s %s "
                    % tuple(
                        _format_float(value, color_decimals)
                        for value in color
                    )
                )
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
                    fw(
                        "%s %s %s "
                        % tuple(
                            _format_float(value, color_decimals)
                            for value in vertex[color_layer][:3]
                        )
                    )
            else:
                for face in bm.faces:
                    for loop in face.loops:
                        fw(
                            "%s %s %s "
                            % tuple(
                                _format_float(value, color_decimals)
                                for value in loop[color_layer][:3]
                            )
                        )

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
        uv_decimals = _uv_decimal_places(bm, uv_layer, decimal_places)
        uv_values = []
        uv_indices_by_face = []
        uv_index_by_value = {}

        for face in bm.faces:
            face_indices = []
            for loop in face.loops:
                uv = tuple(
                    _format_float(value, uv_decimals)
                    for value in loop[uv_layer].uv[:2]
                )
                uv_index = uv_index_by_value.get(uv) if deduplicate_uvs else None
                if uv_index is None:
                    uv_index = len(uv_values)
                    uv_values.append(uv)
                    if deduplicate_uvs:
                        uv_index_by_value[uv] = uv_index
                face_indices.append(uv_index)
            uv_indices_by_face.append(face_indices)

        fw("\ttexCoord TextureCoordinate {\n")
        fw("\t\tpoint [ ")
        for u_value, v_value in uv_values:
            fw(f"{u_value} {v_value} ")
        fw("]\n")
        fw("\t}\n")

        fw("\ttexCoordIndex [ ")
        for face_indices in uv_indices_by_face:
            for texture_index in face_indices:
                fw(f"{texture_index} ")
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


def _matrix_flips_winding(matrix):
    """Return whether the matrix reverses triangle winding."""
    determinant = (
        matrix[0][0]
        * (matrix[1][1] * matrix[2][2] - matrix[1][2] * matrix[2][1])
        - matrix[0][1]
        * (matrix[1][0] * matrix[2][2] - matrix[1][2] * matrix[2][0])
        + matrix[0][2]
        * (matrix[1][0] * matrix[2][1] - matrix[1][1] * matrix[2][0])
    )
    return determinant < 0.0


def _apply_baked_transform(bm, matrix):
    """Transform geometry and preserve outward winding across reflections."""
    bm.transform(matrix)
    if _matrix_flips_winding(matrix):
        bmesh.ops.reverse_faces(bm, faces=list(bm.faces))


def _write_transform_start(fw, transform, decimal_places):
    translation, axis, angle, scale = transform
    decimals = _transform_decimal_places(transform, decimal_places)
    fw("Transform {\n")
    fw(
        "\ttranslation %s %s %s\n"
        % tuple(_format_float(value, decimals) for value in translation)
    )
    fw(
        "\trotation %s %s %s %s\n"
        % tuple(_format_float(value, decimals) for value in (*axis, angle))
    )
    fw(
        "\tscale %s %s %s\n"
        % tuple(_format_float(value, decimals) for value in scale)
    )
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


def _compact_wrl_file(filepath):
    """Remove indentation and blank lines without loading a large WRL at once."""
    original_mode = stat.S_IMODE(os.stat(filepath).st_mode)
    output_directory = os.path.dirname(os.path.abspath(filepath)) or os.getcwd()
    fd, temporary_path = tempfile.mkstemp(
        prefix=".vrml2-compact-",
        suffix=".wrl",
        dir=output_directory,
        text=True,
    )
    try:
        with open(filepath, "r", encoding="utf-8", newline="") as source_file:
            with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as output_file:
                for line in source_file:
                    compacted = line.lstrip()
                    if compacted.strip():
                        output_file.write(compacted.rstrip("\r\n") + "\n")
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


def _write_wrz_copy(filepath):
    """Create a deterministic gzip-compressed WRZ copy beside the WRL."""
    output_directory = os.path.dirname(os.path.abspath(filepath)) or os.getcwd()
    wrz_path = os.path.splitext(filepath)[0] + ".wrz"
    original_mode = stat.S_IMODE(os.stat(filepath).st_mode)
    fd, temporary_path = tempfile.mkstemp(
        prefix=".vrml2-compress-",
        suffix=".wrz",
        dir=output_directory,
    )
    try:
        with open(filepath, "rb") as source_file:
            with os.fdopen(fd, "wb") as raw_output:
                with gzip.GzipFile(
                    filename="",
                    mode="wb",
                    fileobj=raw_output,
                    compresslevel=9,
                    mtime=0,
                ) as compressed_output:
                    while True:
                        chunk = source_file.read(1024 * 1024)
                        if not chunk:
                            break
                        compressed_output.write(chunk)
        os.chmod(temporary_path, original_mode)
        os.replace(temporary_path, wrz_path)
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
    return wrz_path


def _mesh_data_identity(obj):
    """Return an export-session identity for an object's original mesh data."""
    mesh = obj.data
    as_pointer = getattr(mesh, "as_pointer", None)
    return as_pointer() if as_pointer is not None else id(mesh)


def _write_material_node(fw, settings, indent, decimal_places):
    """Write one VRML Material node from normalized export settings."""
    material_decimals = min(decimal_places, 4)
    fw(f"{indent}material Material {{\n")
    for field, vrml_name in (
        ("diffuse_color", "diffuseColor"),
        ("emissive_color", "emissiveColor"),
        ("specular_color", "specularColor"),
    ):
        if field not in settings:
            continue
        color_text = " ".join(
            _format_float(value, material_decimals)
            for value in settings[field]
        )
        fw(f"{indent}\t{vrml_name} {color_text}\n")
    for field, vrml_name in (
        ("ambient_intensity", "ambientIntensity"),
        ("shininess", "shininess"),
        ("transparency", "transparency"),
    ):
        if field not in settings:
            continue
        value_text = _format_float(settings[field], material_decimals)
        fw(f"{indent}\t{vrml_name} {value_text}\n")
    fw(f"{indent}}}\n")


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
    decimal_places=6,
    deduplicate_uvs=True,
    crease_angle=0.0,
    material_settings=None,
):
    """Write one triangulated BMesh as a VRML Shape node."""
    base_src = os.path.dirname(bpy.data.filepath) or os.getcwd()
    single_material_color = (
        use_color
        and color_type == "MATERIAL"
        and len(material_colors) == 1
    )
    if material_settings is None:
        material_settings = [
            {"diffuse_color": tuple(color)}
            for color in material_colors
        ]

    fw(f"{indent}Shape {{\n")
    fw(f"{indent}\tappearance Appearance {{\n")
    if single_material_color:
        settings = (
            material_settings[0]
            if material_settings
            else {"diffuse_color": tuple(material_colors[0])}
        )
        _write_material_node(fw, settings, f"{indent}\t\t", decimal_places)
    else:
        # A Shape whose Appearance has no material field is unlit, and an RGB
        # texture is then drawn flat at full brightness instead of being shaded
        # (VRML97 4.14.2 and table 4.5). Writing an empty Material keeps every
        # exported Shape lit using the VRML97 material defaults.
        fw(f"{indent}\t\tmaterial Material {{\n")
        fw(f"{indent}\t\t}}\n")

    if use_uv:
        filepath = uv_image.filepath
        filepath_full = os.path.normpath(
            bpy.path.abspath(filepath, library=uv_image.library)
        )
        # path_reference() decides Match from the Blender-relative "//" prefix
        # and resolves the path itself, so it needs the stored filepath rather
        # than an already-absolute one. Passing an absolute path here made Match
        # behave like Absolute for every image. The normalized absolute path is
        # still used below for the file name.
        filepath_ref = bpy_extras.io_utils.path_reference(
            filepath,
            base_src,
            base_dst,
            path_mode,
            "textures",
            copy_set,
            uv_image.library,
        )
        filepath_base = os.path.basename(filepath_full)

        # path_reference() has already applied the selected path mode, so its
        # result is the reference the user asked for. Appending the absolute
        # source path on top of it defeated Strip Path and Copy, and wrote
        # machine-local directory names into the exported file. The bare file
        # name stays as an additional VRML url alternative for viewers that
        # resolve textures beside the exported .wrl.
        image_urls = _unique_strings([filepath_ref, filepath_base])

        fw(f"{indent}\t\ttexture ImageTexture {{\n")
        fw(
            f"{indent}\t\t\turl [ %s ]\n"
            % " ".join(_vrml_quote(url) for url in image_urls)
        )
        fw(f"{indent}\t\t}}\n")
    fw(f"{indent}\t}}\n")

    geometry_buffer = io.StringIO()
    _write_indexed_face_set(
        geometry_buffer.write,
        bm,
        use_color and not single_material_color,
        color_type,
        material_colors,
        color_domain,
        color_layer,
        use_uv,
        decimal_places,
        deduplicate_uvs,
        crease_angle,
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


def _face_material_index(face, material_count):
    """Return a valid material index for one face, matching Blender's fallback."""
    material_index = getattr(face, "material_index", 0)
    if material_index < 0 or material_index >= material_count:
        return 0
    return material_index


def _material_bmesh_subset(bm, material_index, material_count):
    """Copy only the faces assigned to one material into a compact BMesh."""
    subset = bm.copy()
    other_faces = [
        face
        for face in subset.faces
        if _face_material_index(face, material_count) != material_index
    ]
    if other_faces:
        bmesh.ops.delete(subset, geom=other_faces, context="FACES")
    subset.verts.index_update()
    subset.faces.index_update()
    return subset


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
    decimal_places,
    deduplicate_uvs,
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
        crease_angle = _crease_angle_for_mesh(obj, bm, use_mesh_modifiers)
        object_matrix = obj_eval.matrix_world if obj_eval is not None else obj.matrix_world
        export_matrix = global_matrix @ object_matrix
        transform = (
            _decompose_vrml_transform(export_matrix)
            if geometry_cache is not None
            else None
        )
        if transform is None:
            _apply_baked_transform(bm, export_matrix)
        bm.verts.index_update()
        bm.faces.index_update()

        materials = []
        material_colors = []
        material_settings = []
        color_domain = None
        color_layer = None
        uv_image = None

        if use_color:
            if color_type == "VERTEX":
                color_domain, color_layer = _active_color_layer(bm, mesh)
                if color_layer is None:
                    color_type = "MATERIAL"

            if color_type == "MATERIAL":
                material_object = obj_eval if obj_eval is not None else obj
                materials = [slot.material for slot in material_object.material_slots]
                if not materials:
                    materials = list(mesh.materials)
                if not materials:
                    use_color = False
                else:
                    material_settings = [
                        _material_export_settings(material)
                        for material in materials
                    ]
                    material_colors = [
                        settings["diffuse_color"]
                        for settings in material_settings
                    ]

        if use_uv:
            if bm.loops.layers.uv.active is None:
                use_uv = False

        material_count = len(material_settings)
        used_material_indices = (
            sorted(
                {
                    _face_material_index(face, material_count)
                    for face in bm.faces
                }
            )
            if material_count
            else []
        )
        split_material_shapes = (
            use_color
            and color_type == "MATERIAL"
            and material_count > 1
            and bool(used_material_indices)
            and any(
                len(material_settings[index]) > 1
                for index in used_material_indices
            )
        )

        if use_uv and not split_material_shapes:
            uv_image = _guess_object_image(obj)
            if uv_image is None or not getattr(uv_image, "filepath", ""):
                use_uv = False

        if transform is not None:
            _write_transform_start(fw, transform, decimal_places)

        reusable_geometry_cache = geometry_cache if transform is not None else None
        reused = 0
        if split_material_shapes:
            for material_index in used_material_indices:
                subset = _material_bmesh_subset(bm, material_index, material_count)
                try:
                    subset_image = (
                        _guess_material_image(materials[material_index])
                        if use_uv
                        else None
                    )
                    subset_use_uv = bool(
                        subset_image is not None
                        and getattr(subset_image, "filepath", "")
                    )
                    reused += save_bmesh(
                        fw,
                        subset,
                        base_dst,
                        True,
                        "MATERIAL",
                        [material_colors[material_index]],
                        None,
                        None,
                        subset_use_uv,
                        subset_image,
                        path_mode,
                        copy_set,
                        reusable_geometry_cache,
                        geometry_group if reusable_geometry_cache is not None else None,
                        "\t\t" if transform is not None else "",
                        decimal_places,
                        deduplicate_uvs,
                        crease_angle,
                        [material_settings[material_index]],
                    )
                finally:
                    subset.free()
        else:
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
                decimal_places,
                deduplicate_uvs,
                crease_angle,
                material_settings,
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
    decimal_places=6,
    deduplicate_uvs=True,
    include_object_comments=True,
    compact_output=False,
    create_wrz=False,
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
    if not 0 <= decimal_places <= 9:
        raise ValueError("Decimal places must be between 0 and 9")

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
            if include_object_comments:
                fw("\n# Object: %r\n" % obj.name)
            else:
                fw("\n")
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
                decimal_places,
                deduplicate_uvs,
                object_geometry_cache,
                geometry_group,
            )

    if geometry_cache is not None:
        _remove_unused_geometry_defs(filepath, geometry_cache)

    if compact_output:
        _compact_wrl_file(filepath)

    wrz_path = _write_wrz_copy(filepath) if create_wrz else None

    bpy_extras.io_utils.path_reference_copy(copy_set)
    message = f"Exported {len(mesh_objects)} mesh object(s) to VRML2"
    if reused_geometry_count:
        message += f"; reused {reused_geometry_count} geometries with DEF/USE"
    if wrz_path is not None:
        message += f"; created {os.path.basename(wrz_path)}"
    operator.report({"INFO"}, message)
    return {"FINISHED"}
