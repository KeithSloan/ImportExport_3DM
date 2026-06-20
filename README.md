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
| BSplineSurface | NURBS surface — control points, **rational weights**, knots copied exactly |
| Plane | NURBS surface via OCC `toNurbs()` |
| Cylinder | Rational NURBS surface (exact); native `r3.Cylinder` optional (see preferences) |
| Cone | Rational NURBS surface (exact); native `r3.Cone` optional |
| Sphere | Rational NURBS surface (exact); native `r3.Sphere` optional |
| Torus | Rational NURBS surface (exact); native `r3.Torus` optional |
| Other analytic surfaces | NURBS via OCC `toNurbs()` / `toBSpline()` |

Whole objects are traversed correctly: selecting an **App::Part**, a
**PartDesign Body**, or a group exports all the geometry nested inside it. The
final solid of a PartDesign Body is exported once.

**NURBS fidelity.** Rational geometry (cylinders, cones, spheres, tori, and any
circular edges) is written with its true control-point weights, so circles stay
circular on re-import. Periodic (closed) surfaces and curves are converted to
clamped form first, and circular/arc edges are written as exact degree-2
rational arcs rather than polyline approximations.

The native-primitives behaviour is controlled by a Preferences option (see
below; it is **off by default** because the bounded-NURBS path round-trips trim
boundaries more reliably).

## Preferences

Open **Edit → Preferences → Import-Export → ImportExport 3DM**:

| Option | Default | Effect |
|---|---|---|
| Export Cylinder / Cone / Sphere / Torus as native primitives | **Off** | When on, writes analytic surfaces as exact rhino3dm primitives (smaller files). When off (default), they are written as exact bounded rational NURBS, which reconstructs trimmed faces more reliably on re-import. |
| **Import: create groups** | **On** | Mirrors each named `.3dm` group as an `App::DocumentObjectGroup` so an object's faces and boundary curves stay together. |
| Import: try to make shell/solid | Off | After collecting a group's surfaces, attempt `Part.makeShell()` (and `makeSolid()` if closed); falls back to individual surfaces. |

### Controlling the imported tree structure — *Import: create groups*

This is the option to reach for if you don't want the grouped tree layout.

- **On (default):** every named group in the `.3dm` becomes an
  `App::DocumentObjectGroup`. Useful when each exported object carries its own
  group, but it can produce a group that wraps a single same-named object.
- **Off:** no container objects are created. Surfaces are placed directly under
  the top-level `Part` and keep their own names; boundary curves are labelled
  `{groupName}_{curveName}` so the association stays visible without nesting.

Set it from the preferences page, or from the Python console:

```python
FreeCAD.ParamGet(
    "User parameter:BaseApp/Preferences/Mod/ImportExport_3DM"
).SetBool("ImportCreateGroups", False)
```

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

## Changes

### 0.3.0

- **Export now traverses containers.** Selecting an `App::Part`, a PartDesign
  Body, or a group exports all nested geometry (previously such selections could
  produce a nearly empty file). The whole selection list is exported, not just
  the first object.
- **Rational weights preserved.** NURBS surfaces and curves are written with
  their true control-point weights and created as rational where needed, so
  cylinders, cones, spheres, tori and circular profiles no longer come back with
  straight/flattened edges.
- **Exact rational arcs.** Circular and arc edges are exported as exact degree-2
  rational arcs instead of high-degree polynomial approximations.
- **Periodic geometry handled.** Closed surfaces/curves are converted to clamped
  form before writing.
- **Import: degenerate trimmed faces fall back to the untrimmed surface.** When
  trim reconstruction produces an invalid, zero-area face, the importer repairs
  it or falls back to the (valid, correctly curved) untrimmed surface rather than
  leaving a collapsed face. (import3DM 0.1.13)

## Acknowledgements

- Test cases kindly supplied by Jonne Neva (cheezebreeze), EdWilliams, Sven

## Developers

- Keith Sloan
- Chris Grellier

## License

GNU Lesser General Public License v2.1 — see [LICENSE](LICENSE).
