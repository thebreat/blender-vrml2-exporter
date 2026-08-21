# Validation notes

The source archive includes a Blender-free smoke test for package imports and the VRML writer's point-color, corner-color, single- and multiple-material color, UV, texture-path, index-output, linked-group separation, unused-DEF cleanup, DEF/USE geometry reuse, safe geometry/UV rounding, UV deduplication, compact output, and WRZ compression branches.

Run it from the project root:

```bash
python3 tests/smoke_test.py
```

This test uses small stand-ins for Blender data structures. It is useful for regression checks, but it does not replace testing inside supported Blender releases.

For a Blender-side release check, run:

```bash
blender --command extension validate .
blender --command extension build
```

Then install the generated ZIP in a clean Blender profile and export representative `.blend` files.
