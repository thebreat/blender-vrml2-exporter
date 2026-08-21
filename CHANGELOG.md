# Changelog

All notable changes to this maintained fork are recorded here.

## Unreleased

- Added configurable decimal rounding for coordinates, transforms, UVs, and colors.
- Removed unnecessary trailing zeroes and normalized negative zero in exported numbers.
- Added automatic precision promotion when low precision would collapse a valid geometry face, collapse a mapped UV triangle, or turn a positive transform scale into zero.
- Added UV-coordinate deduplication with remapped `texCoordIndex` values.
- Moved single material colors into `Appearance` instead of repeating a geometry color index for every face.
- Added options to omit object-name comments, compact WRL whitespace, and create a gzip-compressed WRZ copy.
- Kept `solid FALSE` out of generated `IndexedFaceSet` nodes.

## 0.3.0 - 2026-08-19

- Added geometry reuse modes for linked objects, all identical geometry, or no reuse.
- Made intentional Blender mesh links the default requirement for VRML `DEF`/`USE` instancing.
- Omitted unnecessary `DEF` names when a geometry node has no matching `USE` reference.
- Preserved location, rotation, and positive non-uniform scale through VRML `Transform` nodes so moved copies can share geometry.
- Added safe baked-coordinate fallback for mirrored, zero-scale, or sheared transforms.
- Improved unused-`DEF` cleanup performance and preserved exported file permissions.

## 0.2.0 - 2026-07-17

- Converted the package from Blender's legacy add-on format to the current Blender Extension format.
- Added `blender_manifest.toml` and removed legacy `bl_info` metadata.
- Set the minimum supported Blender version to 4.2, the first release family with the Extensions system.
- Removed the inherited `OFFICIAL` support claim and replaced it with community-maintained metadata.
- Preserved evaluated mesh data layers when exporting with modifiers.
- Added safer handling for point- and corner-domain color attributes.
- Preserved per-corner colors by writing an explicit VRML `colorIndex` where needed.
- Improved texture path normalization, quoting, and duplicate URL removal.
- Added Blender-visible error reporting and a no-mesh warning.
- Added cross-platform installation, usage, maintenance, and release documentation.
- Removed generated cache files and macOS archive metadata from the distributable package.

## 0.1.0

- Earlier community port of the original VRML2 exporter.
