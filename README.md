# ImportExport 3DM

Adds Rhino `.3dm` file import and export to FreeCAD.  Geometry is read and
written as true NURBS — control points, weights, degree, and knot vectors are
preserved exactly, with no tessellation.

> **FreeCAD 1.1+ required.**

## Supported geometry

| Object type | Import | Export |
|---|---|---|
| NURBS Surface (BSplineSurface) | ✓ | ✓ |
| NURBS Curve (BSplineCurve) | ✓ | ✓ |
| Brep (multi-face solid) | ✓ | ✓ |

On import, SubD and Mesh objects are detected and reported as diagnostics —
they indicate that NURBS geometry was not preserved by the originating
application.

## Requirements

`rhino3dm` must be installed into **FreeCAD's own Python interpreter**.

### FreeCAD 1.1 on macOS

```bash
python3.11 -m pip install rhino3dm --no-cache \
  -t '/Applications/FreeCAD_1.1.app/Contents/Resources/lib/python3.11/site-packages'
```

### FreeCAD 1.0 on macOS

```bash
python3.11 -m pip install rhino3dm --no-cache \
  -t '/Applications/FreeCAD 1.0.0.app/Contents/Resources/lib/python3.11/site-packages'
```

### Other platforms

Find FreeCAD's Python interpreter path via the FreeCAD Python console:

```python
import sys; print(sys.path)
```

Then install into one of the listed directories:

```bash
python3.11 -m pip install rhino3dm --no-cache -t /path/from/sys.path
```

## Installation

### From the FreeCAD Addon Manager (planned)

Not yet listed.  Install manually for now.

### Manual install (macOS / Linux)

```bash
cd ~/.local/share/FreeCAD/Mod   # Linux
# or
cd ~/Library/Application\ Support/FreeCAD/Mod   # macOS

git clone https://github.com/KeithSloan/ImportExport_3DM.git
```

Restart FreeCAD.  The importers and exporters appear automatically in
`File → Open` / `File → Import` / `File → Export`.

## Usage

- **Import:** `File → Open` or `File → Import` — select a `.3dm` file and
  choose `3DM Importer` or `3DM Improved Importer` from the format dropdown.
- **Export:** `File → Export` — choose `3DM` or `3DM Improved Exporter`.

Two variants of each handler are registered:

| Handler | Notes |
|---|---|
| `3DM Importer` | Primary importer (`import3DM.py`) |
| `3DM Improved Importer` | Alternate importer (`improved_import3DM.py`) |
| `3DM` exporter | Primary exporter (`export3DM.py`) |
| `3DM Improved Exporter` | Alternate exporter (`improved_export3DM.py`) |

## Import diagnostics

The importer reports geometry type information in the FreeCAD Report View:

- **NurbsSurface** — degree, CV count, rational flag, knot counts
- **SubD** — flags that NURBS geometry was not preserved by the originating exporter
- **Mesh** — flags that NURBS geometry was not preserved

## Blender NURBS pipeline

A companion Blender extension exports NURBS geometry directly to `.3dm`:

**[Blender_Export_3DM](https://github.com/KeithSloan/Blender_Export_3DM)**

This enables a lossless Blender → 3DM → FreeCAD NURBS pipeline:

```
Blender NURBS surface / Surface Psycho patch
    ↓  Blender_Export_3DM
.3dm file
    ↓  ImportExport_3DM (File → Open)
FreeCAD Part::Feature (exact BSplineSurface)
```

## Sample Rhino files

Test `.3dm` files are in `testCases/`.  Additional Rhino sample files:
<https://www.rhino3d.com/download/opennurbs/6/opennurbs6samples>

Rhino API reference: <https://developer.rhino3d.com/api/rhinocommon/>

## Acknowledgements

- Icon design by Freepik
- Test cases kindly supplied by Jonne Neva (cheezebreeze), EdWilliams, Sven

## Developers

- Chris Grellier
- Keith Sloan

## License

GNU Lesser General Public License v2.1 — see [LICENSE](LICENSE).
