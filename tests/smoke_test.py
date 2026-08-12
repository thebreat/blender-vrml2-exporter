from __future__ import annotations

import importlib.util
import os
import sys
import tempfile
import types
from pathlib import Path

SOURCE = Path(os.environ.get('VRML2_SOURCE', Path(__file__).resolve().parents[1]))


# Minimal module stubs for importing the extension outside Blender.
bpy = types.ModuleType('bpy')
bpy.data = types.SimpleNamespace(filepath='/tmp/project/example.blend')
bpy.path = types.SimpleNamespace(
    abspath=lambda path, library=None: path,
    ensure_ext=lambda path, ext: path if path.endswith(ext) else path + ext,
)
bpy.utils = types.SimpleNamespace(register_class=lambda cls: None, unregister_class=lambda cls: None)

class Operator:
    def report(self, levels, message):
        self.last_report = (levels, message)

class ExportMenu:
    @staticmethod
    def append(callback):
        return None

    @staticmethod
    def remove(callback):
        return None

bpy.types = types.SimpleNamespace(Operator=Operator, TOPBAR_MT_file_export=ExportMenu)

bpy_props = types.ModuleType('bpy.props')
for prop_name in ('BoolProperty', 'EnumProperty', 'FloatProperty', 'StringProperty'):
    setattr(bpy_props, prop_name, lambda **kwargs: kwargs)

bpy_extras = types.ModuleType('bpy_extras')
io_utils = types.ModuleType('bpy_extras.io_utils')

class ExportHelper:
    pass

def orientation_helper(**kwargs):
    return lambda cls: cls

class AxisConversion:
    def to_4x4(self):
        return self

io_utils.ExportHelper = ExportHelper
io_utils.orientation_helper = orientation_helper
io_utils.path_reference_mode = object()
io_utils.axis_conversion = lambda **kwargs: AxisConversion()
io_utils.path_reference = lambda *args, **kwargs: args[0]
io_utils.path_reference_copy = lambda copy_set: None
bpy_extras.io_utils = io_utils

bmesh = types.ModuleType('bmesh')

sys.modules.update({
    'bpy': bpy,
    'bpy.props': bpy_props,
    'bpy_extras': bpy_extras,
    'bpy_extras.io_utils': io_utils,
    'bmesh': bmesh,
})

# Import the package entry point.
spec = importlib.util.spec_from_file_location(
    'io_scene_vrml2_export',
    SOURCE / '__init__.py',
    submodule_search_locations=[str(SOURCE)],
)
package = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = package
spec.loader.exec_module(package)
assert package.ExportVRML.bl_idname == 'export_scene.vrml2'
assert package.ExportVRML.filename_ext == '.wrl'
assert package.ExportVRML.__annotations__['geometry_reuse']['default'] == 'LINKED'

# Import the writer.
writer_spec = importlib.util.spec_from_file_location(
    'io_scene_vrml2_export.export_vrml2',
    SOURCE / 'export_vrml2.py',
)
writer = importlib.util.module_from_spec(writer_spec)
sys.modules[writer_spec.name] = writer
writer_spec.loader.exec_module(writer)
assert writer._vrml_quote(r'C:\textures\a "quoted" file.png') == '"C:/textures/a \\"quoted\\" file.png"'


class LayerSet:
    def __init__(self, active=None):
        self.active = active


class LoopLayers:
    def __init__(self):
        self.uv = LayerSet(None)


class LoopsContainer:
    def __init__(self):
        self.layers = LoopLayers()


class Vertex:
    def __init__(self, index, co, color):
        self.index = index
        self.co = co
        self._color = color

    def __getitem__(self, layer):
        assert layer == 'point_color'
        return self._color


class Loop:
    def __init__(self, vertex, color, uv=(0.0, 0.0)):
        self.vert = vertex
        self._color = color
        self._uv = uv

    def __getitem__(self, layer):
        if layer == 'corner_color':
            return self._color
        if layer == 'uv_layer':
            return types.SimpleNamespace(uv=self._uv)
        raise AssertionError(f'Unexpected loop layer: {layer!r}')


class Face:
    def __init__(self, loops, material_index=0):
        self.loops = loops
        self.material_index = material_index


class BMesh:
    def __init__(self):
        self.verts = [
            Vertex(0, (0.0, 0.0, 0.0), (1.0, 0.0, 0.0, 1.0)),
            Vertex(1, (1.0, 0.0, 0.0), (0.0, 1.0, 0.0, 1.0)),
            Vertex(2, (0.0, 1.0, 0.0), (0.0, 0.0, 1.0, 1.0)),
        ]
        loops = [
            Loop(self.verts[0], (1.0, 0.0, 0.0, 1.0), (0.0, 0.0)),
            Loop(self.verts[1], (0.0, 1.0, 0.0, 1.0), (1.0, 0.0)),
            Loop(self.verts[2], (0.0, 0.0, 1.0, 1.0), (0.0, 1.0)),
        ]
        self.faces = [Face(loops)]
        self.loops = LoopsContainer()


bm = BMesh()
with tempfile.NamedTemporaryFile('w+', suffix='.wrl', encoding='utf-8', delete=False) as handle:
    writer.save_bmesh(
        handle.write,
        bm,
        '/tmp',
        True,
        'VERTEX',
        [],
        'CORNER',
        'corner_color',
        False,
        None,
        'AUTO',
        set(),
    )
    handle.flush()
    content = Path(handle.name).read_text(encoding='utf-8')

assert 'colorPerVertex TRUE' in content
assert 'colorIndex [ 0 1 2 -1 ]' in content
assert 'coordIndex [ 0 1 2 -1 ]' in content
assert '1.0000 0.0000 0.0000' in content

# Identical geometry in the same reuse group is written once and then referenced.
geometry_cache = {}
with tempfile.NamedTemporaryFile('w+', suffix='.wrl', encoding='utf-8', delete=False) as handle:
    first_reused = writer.save_bmesh(
        handle.write,
        bm,
        '/tmp',
        False,
        'MATERIAL',
        [],
        None,
        None,
        False,
        None,
        'AUTO',
        set(),
        geometry_cache,
        ('LINKED', 1001),
    )
    second_reused = writer.save_bmesh(
        handle.write,
        bm,
        '/tmp',
        False,
        'MATERIAL',
        [],
        None,
        None,
        False,
        None,
        'AUTO',
        set(),
        geometry_cache,
        ('LINKED', 1001),
    )
    handle.flush()
    reused_content = Path(handle.name).read_text(encoding='utf-8')

assert first_reused is False
assert second_reused is True
assert reused_content.count('geometry DEF Geometry_1 IndexedFaceSet') == 1
assert reused_content.count('geometry USE Geometry_1') == 1
assert reused_content.count('point [ ') == 1

# The same geometry in a different linked-mesh group remains independent.
with tempfile.NamedTemporaryFile('w+', suffix='.wrl', encoding='utf-8', delete=False) as handle:
    writer.save_bmesh(
        handle.write,
        bm,
        '/tmp',
        False,
        'MATERIAL',
        [],
        None,
        None,
        False,
        None,
        'AUTO',
        set(),
        geometry_cache,
        ('LINKED', 2002),
    )
    handle.flush()
    independent_content = Path(handle.name).read_text(encoding='utf-8')

assert 'geometry DEF Geometry_2 IndexedFaceSet' in independent_content
assert 'geometry USE Geometry_1' not in independent_content
assert 'geometry DEF' not in content

with tempfile.NamedTemporaryFile('w+', suffix='.wrl', encoding='utf-8', delete=False) as handle:
    handle.write(reused_content)
    handle.write(independent_content)
    cleanup_path = handle.name

writer._remove_unused_geometry_defs(cleanup_path, geometry_cache)
cleaned_content = Path(cleanup_path).read_text(encoding='utf-8')
assert 'geometry DEF Geometry_1 IndexedFaceSet' in cleaned_content
assert 'geometry USE Geometry_1' in cleaned_content
assert 'DEF Geometry_2' not in cleaned_content
assert cleaned_content.count('geometry IndexedFaceSet') == 1


class Rotation:
    def __init__(self, rows, axis=(0.0, 0.0, 1.0), angle=0.0):
        self.rows = rows
        self.axis = axis
        self.angle = angle

    def to_matrix(self):
        return self.rows

    def to_axis_angle(self):
        return self.axis, self.angle


class TransformMatrix(list):
    def __init__(self, rows, translation, rotation, scale):
        super().__init__(rows)
        self.parts = (translation, rotation, scale)

    def decompose(self):
        return self.parts


identity_rotation = Rotation(
    (
        (1.0, 0.0, 0.0),
        (0.0, 1.0, 0.0),
        (0.0, 0.0, 1.0),
    )
)
positive_non_uniform = TransformMatrix(
    (
        (2.0, 0.0, 0.0, 4.0),
        (0.0, 1.0, 0.0, 5.0),
        (0.0, 0.0, 0.5, 6.0),
        (0.0, 0.0, 0.0, 1.0),
    ),
    (4.0, 5.0, 6.0),
    identity_rotation,
    (2.0, 1.0, 0.5),
)
assert writer._decompose_vrml_transform(positive_non_uniform) == (
    (4.0, 5.0, 6.0),
    (0.0, 0.0, 1.0),
    0.0,
    (2.0, 1.0, 0.5),
)

mirrored = TransformMatrix(
    positive_non_uniform,
    (4.0, 5.0, 6.0),
    identity_rotation,
    (-2.0, 1.0, 0.5),
)
assert writer._decompose_vrml_transform(mirrored) is None

sheared = TransformMatrix(
    (
        (2.0, 0.25, 0.0, 4.0),
        (0.0, 1.0, 0.0, 5.0),
        (0.0, 0.0, 0.5, 6.0),
        (0.0, 0.0, 0.0, 1.0),
    ),
    (4.0, 5.0, 6.0),
    identity_rotation,
    (2.0, 1.0, 0.5),
)
assert writer._decompose_vrml_transform(sheared) is None

# The export coordinator distinguishes intentional Blender links from
# independent objects before the heavier Blender mesh conversion begins.
shared_mesh = object()
linked_a = types.SimpleNamespace(type='MESH', name='Linked A', data=shared_mesh)
linked_b = types.SimpleNamespace(type='MESH', name='Linked B', data=shared_mesh)
independent = types.SimpleNamespace(type='MESH', name='Independent', data=object())
context = types.SimpleNamespace(
    scene=types.SimpleNamespace(objects=[linked_a, linked_b, independent]),
    selected_objects=[],
)
operator = Operator()
original_save_object = writer.save_object


def capture_reuse(*args):
    capture_reuse.calls.append((args[2].name, args[-2], args[-1]))
    return False


writer.save_object = capture_reuse
try:
    for reuse_mode in ('LINKED', 'IDENTICAL', 'OFF'):
        capture_reuse.calls = []
        with tempfile.NamedTemporaryFile(suffix='.wrl', delete=False) as handle:
            export_path = handle.name
        assert writer.save(
            operator,
            context,
            filepath=export_path,
            global_matrix=object(),
            geometry_reuse=reuse_mode,
        ) == {'FINISHED'}

        linked_a_call, linked_b_call, independent_call = capture_reuse.calls
        if reuse_mode == 'LINKED':
            assert linked_a_call[1] is linked_b_call[1]
            assert linked_a_call[1] is not None
            assert linked_a_call[2] == linked_b_call[2]
            assert independent_call[1:] == (None, None)
        elif reuse_mode == 'IDENTICAL':
            assert linked_a_call[1] is linked_b_call[1] is independent_call[1]
            assert {call[2] for call in capture_reuse.calls} == {'IDENTICAL'}
        else:
            assert all(call[1:] == (None, None) for call in capture_reuse.calls)
finally:
    writer.save_object = original_save_object

with tempfile.NamedTemporaryFile('w+', suffix='.wrl', encoding='utf-8', delete=False) as handle:
    writer.save_bmesh(
        handle.write,
        bm,
        '/tmp',
        True,
        'VERTEX',
        [],
        'POINT',
        'point_color',
        False,
        None,
        'AUTO',
        set(),
    )
    handle.flush()
    point_content = Path(handle.name).read_text(encoding='utf-8')

assert 'colorPerVertex TRUE' in point_content
assert 'colorIndex [' not in point_content
assert 'coordIndex [ 0 1 2 -1 ]' in point_content

print('Extension import and VRML writer smoke tests passed.')

# Material colors and texture paths exercise the remaining writer branches.
with tempfile.NamedTemporaryFile('w+', suffix='.wrl', encoding='utf-8', delete=False) as handle:
    writer.save_bmesh(
        handle.write,
        bm,
        '/tmp/export destination',
        True,
        'MATERIAL',
        [(0.25, 0.5, 0.75)],
        None,
        None,
        False,
        None,
        'AUTO',
        set(),
    )
    handle.flush()
    material_content = Path(handle.name).read_text(encoding='utf-8')

assert 'colorPerVertex FALSE' in material_content
assert 'color [ 0.2500 0.5000 0.7500 ]' in material_content
assert 'colorIndex [ 0 ]' in material_content

bm.loops.layers.uv.active = 'uv_layer'
image = types.SimpleNamespace(
    filepath='/tmp/textures/a "quoted" file.png',
    library=None,
)
with tempfile.NamedTemporaryFile('w+', suffix='.wrl', encoding='utf-8', delete=False) as handle:
    writer.save_bmesh(
        handle.write,
        bm,
        '/tmp/export destination',
        False,
        'MATERIAL',
        [],
        None,
        None,
        True,
        image,
        'AUTO',
        set(),
    )
    handle.flush()
    texture_content = Path(handle.name).read_text(encoding='utf-8')

assert 'texCoordIndex [ 0 1 2 -1 ]' in texture_content
assert '0.000000 0.000000 1.000000 0.000000 0.000000 1.000000' in texture_content
assert '\"/tmp/textures/a \\"quoted\\" file.png\"' in texture_content

for generated in (
    content,
    reused_content,
    cleaned_content,
    point_content,
    material_content,
    texture_content,
):
    assert generated.count('{') == generated.count('}')
    assert generated.count('[') == generated.count(']')

print('Material, UV, path escaping, and structural checks passed.')
