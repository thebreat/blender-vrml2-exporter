# Changelog

All notable changes to this maintained fork are recorded here.

## 0.7.0-alpha.8 - 2026-10-05

- Added sampled diffuse material color animation through VRML `ColorInterpolator` nodes.
- Animated Blender base colors and animated VRML2 Material Studio diffuse colors are supported on objects that export as one Shape with one material.
- Reused the existing loop and click-to-play animation controls for material animation.
- Added Blender integration coverage for a red-to-blue keyed material.

## 0.7.0-alpha.7 - 2026-10-05

- Added sampled Armature modifier deformation through VRML `CoordinateInterpolator` nodes for meshes whose evaluated vertex count remains stable.
- Armature objects and bones remain Blender-side controls; the resulting animated mesh positions are baked into the VRML file.
- Added a Blender integration test with a genuinely animated bone and fully weighted mesh.

## 0.7.0-alpha.6 - 2026-10-05

- Fixed shape-key animation being skipped when Blender changed a quad's triangulation diagonal as the shape deformed.
- Added regression coverage using a deforming quad-based cube.

## 0.7.0-alpha.5 - 2026-10-05

- Added sampled shape-key deformation through VRML `CoordinateInterpolator` nodes for constant-topology, single-Shape meshes.
- Kept animated coordinate geometry independent from DEF/USE geometry reuse so one object's deformation cannot alter another object.
- Added adaptive coordinate-animation precision and Blender-side shape-key coverage.

## 0.7.0-alpha.4 - 2026-10-05

- Added sampled positive object-scale animation through VRML `PositionInterpolator` nodes routed to `Transform.set_scale`.
- Preserved each object's starting rotation as the scale orientation so non-uniform scale animation follows Blender's local axes.
- Added coverage for simultaneous location, rotation, and scale animation.

## 0.7.0-alpha.3 - 2026-10-05

- Made click-to-play one-shot playback the default and explicitly kept the VRML timer inactive until an animated object is clicked.

## 0.7.0-alpha.2 - 2026-10-04

- Added sampled mesh-object rotation animation through VRML `OrientationInterpolator` nodes.
- Combined location and rotation animation around each object's starting world-space pivot, preventing animated objects from orbiting the scene origin.
- Added adaptive rotation precision and Blender-side coverage for simultaneous location and rotation animation.
- Included the 0.6.3 Blender Extensions packaging exclusions in the animation branch.

## 0.7.0-alpha.1 - 2026-09-10

- Added the first animation alpha with optional mesh-object location animation over Blender's scene frame range.
- Added a shared VRML `TimeSensor`, per-object `PositionInterpolator` nodes, continuous looping or click-to-play one-shot playback, and configurable frame sampling.
- Preserved the user's current Blender timeline frame after animation export.
- Kept animation disabled by default so existing static exports remain unchanged.

## 0.6.3 - 2026-10-02

- Excluded automated tests and development-only validation documentation from distributable extension packages.

## 0.6.2 - 2026-09-14

- Added an optional Two-Sided Faces export setting that writes `solid FALSE` on every exported geometry. The existing one-sided output remains the default.

## 0.6.1 - 2026-09-10

- Fixed exported texture URLs so they follow the selected path mode instead of also recording the absolute location of the texture on the exporting machine.
- Fixed `Match` path mode so it keeps a Blender-relative texture path relative instead of always writing an absolute one.
- Kept textured shapes lit by writing a `Material` node in every exported `Appearance`, because VRML97 renders a shape unlit when its appearance has no material.
- Added regression coverage for every path mode and for the textured-shape lighting cases, including checks that run inside Blender against its own path resolution.
- Updated the extension license declaration and bundled license text to GNU GPL version 3 or later for Blender Extensions platform compatibility.

## 0.6.0 - 2026-09-09

- Preserved Blender edges marked Sharp when exporting meshes with a positive VRML `creaseAngle`.
- Limited sharp-edge coordinate splitting to boundaries that `creaseAngle` would otherwise smooth, avoiding redundant file-size growth on angle-generated sharp edges.

## 0.5.0 - 2026-08-26

- Added automatic conversion of Blender Shade Smooth and Smooth by Angle settings to VRML `creaseAngle` radians.
- Kept otherwise-identical reusable geometry separate when its smoothing angle differs.
- Added Blender 5.2 compatibility for reading Geometry Nodes modifier inputs.
- Corrected triangle winding after baking mirrored or negative-scale transforms so one-sided VRML viewers do not display hollow geometry.
- Added automatic export of VRML2 Material Studio diffuse, emissive, specular, ambient intensity, shininess, and transparency values.
- Split multi-material meshes into separate VRML Shapes only when full per-material Appearance settings require it.

## 0.4.0 - 2026-08-21

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
