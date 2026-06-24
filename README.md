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
| `ExportTrimmedBreps` *(trim3dm branch)* | **On** | Write faces as **trimmed Breps** via the optional `trim3dm` extension. If trim3dm isn't built, a warning is printed and export falls back to untrimmed surfaces + curves. See *Trimmed Breps* below. |
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

## Trimmed Breps — `trim3dm` (experimental, `trim3dm` branch)

> Only on the **`trim3dm` branch**. Main writes untrimmed NURBS surfaces +
> boundary curves; trims are reconstructed on re-import (and can be fragile).

rhino3dm's Python API cannot *construct* trimmed Breps (the OpenNURBS
loop/trim/2D-curve tables aren't bound — see
[rhino3dm #712](https://github.com/mcneel/rhino3dm/issues/712)). So a 3dm exported
through rhino3dm alone carries the full untrimmed surface plus loose boundary
curves, and Rhino/FreeCAD see untrimmed patches.

The **`trim3dm`** companion extension closes that gap: a small pybind11 +
OpenNURBS module that *builds and reads* trimmed Breps in `.3dm` files. It is
separate from rhino3dm — they cooperate at the file level (both speak
OpenNURBS). With it installed:

- **Export** (`ExportTrimmedBreps`, default on): each face is written as a real
  **trimmed Brep**. If `trim3dm` isn't built, you get a warning and a normal
  untrimmed export — nothing breaks.
- **Import:** the File → Open / Import format dropdown offers two `.3dm` import
  types: **"3DM Non Trimmed"** (the original importer — untrimmed surfaces +
  boundary curves) and **"3DM Trimmed via trim3dm"**, which reads the trims and
  rebuilds proper trimmed `Part::Face` objects (via pythonOCC). Pick "Non
  Trimmed" for the stable path, "Trimmed via trim3dm" to exercise this feature.

Group/name is preserved: a trimmed Brep is named `"{object}::{face}"`, and the
trimmed importer rebuilds the matching FreeCAD `Part → group → faces` tree.

**`trim3dm` must be compiled** for your platform and FreeCAD's Python (it is not
pure Python). Build instructions (macOS / Linux / Windows) are in
[`trim3dm/README.md`](trim3dm/README.md). Without it, the "3DM Non Trimmed"
import and untrimmed export continue to work.

> **The trim3dm build has so far only been tested on macOS** (Apple Silicon,
> FreeCAD 1.1 + conda Python 3.11). The CMake/pybind11 setup is written to be
> cross-platform, but **Linux and Windows builds are untested** — feedback
> welcome (see the testing call-out below).

Status: alpha. Curved trims currently use sampled (approximate) pcurves, and the
trimmed Breps appear *named* (not in real Rhino groups) in Rhino — see the
"trim3dm branch" section of `CLAUDE.md` for the open items.

### Help test this — before it merges to Main

The `trim3dm` branch is being shared for testing ahead of a merge to Main. If you
work with FreeCAD ↔ Rhino `.3dm` interchange, please try it and report back — see
[`trim3dm/TESTING.md`](trim3dm/TESTING.md) for what to test, how to build on your
platform, and where to leave feedback.

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
