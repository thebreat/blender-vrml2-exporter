# Validation notes

The source archive includes a Blender-free smoke test for package imports and the VRML writer's point-color, corner-color, single- and multiple-material color, VRML2 Material Studio fields, UV, texture-path, texture path-mode handling, textured-Shape lighting, one- and two-sided face output, index-output, linked-group separation, unused-DEF cleanup, DEF/USE geometry reuse, shade-smoothing angle conversion, manually marked sharp-edge selection, smoothing-aware geometry separation, mirrored-transform winding correction, safe geometry/UV rounding, UV deduplication, compact output, and WRZ compression branches.

Run it from the project root:

```bash
python3 tests/smoke_test.py
```

This test uses small stand-ins for Blender data structures. It is useful for regression checks, but it does not replace testing inside supported Blender releases.

Run the Material Studio integration check inside Blender with:

```bash
blender --background --factory-startup --python tests/blender_material_integration_test.py
```

Run the manually marked sharp-edge integration check with:

```bash
blender --background --factory-startup --python tests/blender_sharp_edge_integration_test.py
```

Run the texture path-mode and Shape lighting checks inside Blender with:

```bash
blender --background --factory-startup --python tests/blender_export_correctness_test.py
```

That check needs Blender because it exercises the real
`bpy_extras.io_utils.path_reference` resolution for every path mode, against an
absolute texture outside the export directory, an absolute texture inside it, and
a Blender-relative `//` texture path. `Match` in particular can only be tested
here, because it reads the `//` prefix that exists only on real Blender image
data. The Blender-free smoke test can only use a stand-in for that function.

The smoke, Material Studio, and export-correctness tests do not write
`__pycache__` directories into the checkout; each
disables bytecode writing before importing the exporter, because Blender enables
it regardless of `PYTHONDONTWRITEBYTECODE`.

For a Blender-side release check, run:

```bash
blender --command extension validate .
blender --command extension build
```

Then install the generated ZIP in a clean Blender profile and export representative `.blend` files.
