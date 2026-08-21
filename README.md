# VRML2 Exporter for Blender

A maintained Blender Extension for exporting mesh objects to **VRML 2.0 (`.wrl`)**. This package modernizes the extension metadata and packaging while retaining the original export workflow.

## Project status and attribution

- **Original VRML2 exporter:** Campbell Barton
- **Current maintainer:** thebreat
- **Source code:** [GitHub repository](https://github.com/thebreat/blender-vrml2-exporter)
- **Bug reports and feature requests:** [GitHub Issues](https://github.com/thebreat/blender-vrml2-exporter/issues)
- **License:** GNU General Public License, version 2 or any later version (`GPL-2.0-or-later`)
- **Extension ID:** `io_scene_vrml2_export`
- **Current package version:** `0.3.0`
- **Minimum Blender version:** `4.2.0`

## Features

- Exports Blender mesh objects to VRML 2.0 (`.wrl`).
- Exports every mesh in the scene or selected objects only.
- Applies evaluated modifiers when **Apply Modifiers** is enabled.
- Applies object transforms, axis conversion, and a configurable global scale.
- Reuses linked mesh geometry with VRML `DEF`/`USE` nodes to reduce file size.
- Preserves separate object locations, rotations, and positive non-uniform scales while reusing geometry.
- Offers an optional maximum-optimization mode that also finds independent but identical geometry.
- Omits `DEF` names from geometry that is not referenced by any `USE` statement.
- Offers configurable decimal rounding without trailing zeroes.
- Automatically retains extra coordinate or UV precision when rounding would collapse a thin face or mapped UV triangle.
- Deduplicates rounded UV coordinates and remaps `texCoordIndex` values.
- Stores a single material color in `Appearance` instead of repeating a color index for every face.
- Can omit object-name comments and compact whitespace for smaller WRL files.
- Can create a gzip-compressed `.wrz` copy beside the exported `.wrl` file.
- Triangulates exported geometry for predictable VRML output.
- Exports the active mesh color attribute.
  - Supports point-domain colors.
  - Supports corner-domain colors with an explicit VRML `colorIndex`.
  - Falls back to material viewport colors when no active color attribute is available.
- Exports the active UV map and the first usable image texture found in the object's node-based materials.
- Supports Blender's path modes and can copy referenced textures when the selected path mode requires it.
- Reports export failures in Blender instead of failing silently.

## Install the packaged extension

Use the included distributable archive named `vrml2_exporter-0.3.0.zip`. **Do not extract it first.**

1. Open Blender 4.2 or newer.
2. Open **Edit > Preferences**.
3. Open **Get Extensions** or **Extensions**, depending on the Blender release.
4. Open the menu in the upper-right corner and choose **Install from Disk**.
5. Select `vrml2_exporter-0.3.0.zip`.
6. Confirm the installation and enable **VRML2 Exporter** if Blender does not enable it automatically.
7. Close Preferences.

The same archive works on Windows, macOS, and Linux; Blender installs it into the appropriate user extension repository for the current operating system.

### Windows

- Download and keep the file as a `.zip`; do not open or extract it in File Explorer.
- Install it through Blender's **Install from Disk** command.
- When exporting with copied textures, choose an output directory where your Windows account has write access.

### macOS

- Safari may automatically extract downloaded ZIP files when **Open “safe” files after downloading** is enabled. Install the original ZIP, or compress the extracted extension files back into a ZIP with `blender_manifest.toml` and `__init__.py` at the archive root.
- Do not copy the extension into the Blender application bundle. Use **Install from Disk** so Blender can manage it in your user profile.
- If macOS quarantines a downloaded archive, confirm that you trust the source before allowing Blender to install it.

### Linux

- Install the unchanged ZIP through Blender's **Install from Disk** command.
- Flatpak, Snap, or other sandboxed Blender builds may only be able to write to locations exposed to the sandbox. Export to your home or project directory, or grant the application access to the required folder.
- No system-wide installation or root access is required.

## Use the exporter

1. Open a `.blend` file containing at least one mesh object.
2. Choose **File > Export > VRML2 (.wrl)**.
3. Choose the destination and configure the export options.
4. Select **Export VRML2**.

### Export options

| Option | Behavior |
| --- | --- |
| **Selection Only** | Exports selected mesh objects instead of every mesh in the scene. |
| **Apply Modifiers** | Exports Blender's evaluated mesh with modifiers applied. |
| **Geometry Reuse: Linked Objects Only** | Default. Reuses geometry only for objects that intentionally share Blender mesh data, such as duplicates created with `Alt+D`. |
| **Geometry Reuse: All Identical Geometry** | Also reuses independent objects, including unchanged `Shift+D` copies, when their complete exported geometry is identical. |
| **Geometry Reuse: Off** | Writes every object's geometry separately using baked coordinates. |
| **Texture and UVs** | Exports the active UV map and a referenced image texture when one can be found. |
| **Deduplicate UV Coordinates** | Default. Writes each rounded UV coordinate once and reuses its index. Disable this only when comparing against older exporter output. |
| **Colors** | Enables color export. |
| **Color Source: Color Attribute** | Uses the active point- or corner-domain mesh color attribute. Falls back to material colors if none is available. |
| **Color Source: Material Color** | Uses each material's viewport diffuse color and the face material index. |
| **Forward / Up** | Converts Blender coordinates to the target axis convention. Defaults remain forward `Z`, up `Y`. |
| **Scale** | Multiplies exported coordinates by the selected value. |
| **Path Mode** | Controls how image texture paths are written and whether Blender copies referenced files. |
| **Decimal Places** | Rounds coordinates, transforms, UVs, and colors from 0 to 9 decimal places. The default is 6. Thin geometry, small mapped UV triangles, and very small positive scales automatically retain additional precision when necessary. |
| **Include Object Name Comments** | Keeps object names in the WRL as human-readable comments. Disable it for a small file-size saving. |
| **Compact Output** | Removes indentation and blank lines while keeping valid VRML syntax. |
| **Create Compressed WRZ Copy** | Creates a gzip-compressed `.wrz` file beside the ordinary `.wrl` export. |

## Known limitations

- The extension exports mesh geometry only. Cameras, lights, armatures, animation, constraints, and scene hierarchy are not exported.
- Geometry is triangulated during export.
- Mirrored (negative-scale) and sheared object transforms are baked into coordinates rather than instanced because VRML97 `Transform` scale values must be positive.
- Linked objects whose evaluated geometry differs because of modifiers, colors, or UV data are not combined.
- Blender shader node graphs are not converted to VRML materials.
- The exporter uses the first usable image texture found in an object's node-based materials; it does not reproduce complex multi-texture shading.
- Color alpha values are ignored because the current writer outputs RGB values.
- Rounding is decimal-place based rather than significant-digit based. Inspect highly precise engineering or medical geometry before choosing very low values.
- VRML viewers differ in their support for texture paths, color indexing, and material behavior. Test representative files in the target viewer.

## Development layout

```text
blender_manifest.toml  Extension identity, version, compatibility, license, and permissions
__init__.py            Blender operator, user interface, registration, and menu entry
export_vrml2.py        Mesh conversion and VRML writer
README.md              User, installation, support, and development documentation
CHANGELOG.md           Version history
LICENSE                GNU GPL version 2 license text
```

## Build and validate a release

Run Blender's extension commands from the source directory:

```bash
blender --command extension validate .
blender --command extension build
```

Before every release:

1. Update `version` in `blender_manifest.toml` using semantic versioning.
2. Add the release notes to `CHANGELOG.md`.
3. Confirm the public `maintainer` and optional `website` values.
4. Validate the extension.
5. Build a fresh ZIP and confirm that `blender_manifest.toml` and `__init__.py` are at the ZIP root.
6. Test installation in a clean Blender user profile.
7. Export representative files covering modifiers, materials, point colors, corner colors, UVs, textures, selection-only mode, and path modes.

## Support request checklist

A useful bug report should include:

- Blender version and operating system.
- Extension version from `blender_manifest.toml`.
- Exact export settings.
- The complete error shown in Blender or the system console.
- A minimal `.blend` file that reproduces the issue, when licensing and privacy permit.
- The VRML viewer or downstream application used to open the exported file.

## License

This extension is free software under `GPL-2.0-or-later`. See [LICENSE](LICENSE). Modified distributions must preserve the applicable copyright and license notices and provide source code under compatible GPL terms.
