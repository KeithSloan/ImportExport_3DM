# ImportExport 3DM

FreeCAD Import/Export module for Rhino `.3dm` files.  Geometry is read and
written as true NURBS — control points, weights, degree, and knot vectors are
preserved exactly, with no tessellation.

> **FreeCAD 1.1+ and rhino3dm ≥ 8.0.0 required.**

## Supported geometry

### Import

| rhino3dm type | FreeCAD result |
|---|---|
| Brep (multi-face solid) | `Part::Feature` via OCCT |
| NurbsSurface | `Part::Feature` with BSplineSurface shell |
| NurbsCurve | `Part::Feature` with BSplineCurve wire |
| SubD | Diagnostic only — NURBS not preserved by originating app |
| Mesh | Diagnostic only — NURBS not preserved by originating app |

### Export

| FreeCAD surface type | 3DM output |
|---|---|
| BSplineSurface | NURBS surface (control points, knots, weights copied exactly) |
| Plane | NURBS surface via OCC `toNurbs()` |
| Cylinder | Native `r3.Cylinder` primitive (or NURBS fallback) |
| Cone | Native `r3.Cone` primitive (or NURBS fallback) |
| Sphere | Native `r3.Sphere` primitive (or NURBS fallback) |
| Torus | Native `r3.Torus` primitive (or NURBS fallback) |
| Other analytic surfaces | NURBS via OCC `toNurbs()` / `toBSpline()` |

The native-primitives behaviour is controlled by a Preferences option (see
below).

## Export preferences

Open **Edit → Preferences → Import-Export → ImportExport 3DM**:

| Option | Default | Effect |
|---|---|---|
| Export Cylinder / Cone / Sphere / Torus as native primitives | On | Writes analytic surfaces as exact rhino3dm primitives — preserves the analytic shape and produces smaller files.  When off, OCC converts them to NURBS approximations. |

## Requirements

`rhino3dm` ≥ 8.0.0 must be installed into **FreeCAD's own Python interpreter**.

### FreeCAD 1.1 on macOS

```bash
/Applications/FreeCAD_1.1.app/Contents/Resources/bin/python \
  -m pip install "rhino3dm>=8.0.0"
```

### Other platforms

Find FreeCAD's Python interpreter via the FreeCAD Python console:

```python
import sys; print(sys.executable)
```

Then install:

```bash
/path/to/freecad/python -m pip install "rhino3dm>=8.0.0"
```

## Installation

### Manual install (macOS / Linux)

```bash
cd ~/Library/Application\ Support/FreeCAD/Mod   # macOS
# or
cd ~/.local/share/FreeCAD/Mod                    # Linux

git clone https://github.com/KeithSloan/ImportExport_3DM.git
```

Restart FreeCAD.  The importers and exporter appear automatically in
`File → Open` / `File → Import` / `File → Export`.

### From the FreeCAD Addon Manager

Not yet listed — install manually for now.

## Usage

- **Import:** `File → Open` or `File → Import` — select a `.3dm` file and
  choose `3DM` from the format dropdown.
- **Export:** `File → Export` — choose `3DM`.

## Report View diagnostics

Version and progress information is printed to the FreeCAD Report View during
import and export.  The module version and rhino3dm version are printed at
module load time.

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
    ↓  KS_CurvesWB Import commands (optional)
Editable NurbsSurfaceFP / NurbsCurveFP objects
```

## Sample Rhino files

Test `.3dm` files are in `testCases/`.  Additional Rhino sample files:
<https://www.rhino3d.com/download/opennurbs/6/opennurbs6samples>

Rhino API reference: <https://developer.rhino3d.com/api/rhinocommon/>

## Acknowledgements

- Test cases kindly supplied by Jonne Neva (cheezebreeze), EdWilliams, Sven

## Developers

- Keith Sloan
- Chris Grellier

## License

GNU Lesser General Public License v2.1 — see [LICENSE](LICENSE).
