# ImportExport 3DM

FreeCAD Import/Export module for Rhino `.3dm` files. Geometry is read and
written as true NURBS — control points, weights, degree, and knot vectors are
preserved exactly, with no tessellation.

> **FreeCAD 1.1+ required. rhino3dm ≥ 8.32 recommended** (≥ 8.0.0 works, but
> importing Rhino-authored *trimmed* surfaces needs the trim-topology read API
> added in the 8.32 line — see [Requirements](#requirements)).

## Supported geometry

### Import

Rhino-authored **trimmed Breps** are read using rhino3dm's official Brep
trim-topology API (`BrepFace.Loops` / `Trims` / `Edges`, rhino3dm ≥ 8.32) and
reconstructed as trimmed faces sewn into a solid/shell, entirely through
FreeCAD's own `Part`/OCCT API (no pythonOCC/OCC.Core dependency). Files produced
by this module's own exporter, and older rhino3dm, use the legacy reconstruction
path automatically.

| rhino3dm type | FreeCAD result |
|---|---|
| Brep (trimmed multi-face solid) | Trimmed `Part` faces sewn to a Solid/Shell; analytic faces optionally native (see below) |
| Extrusion (cylinder/box/pipe) | Native `Part::Cylinder` etc. (analytic parameters read directly) |
| NurbsSurface | `Part::Feature` with BSplineSurface |
| NurbsCurve | `Part::Feature` with BSplineCurve wire |
| SubD | Diagnostic only — rhino3dm exposes SubD topology but no `ToBrep`/`ToNurbs` in Python, so it can't yet be imported as NURBS |
| Mesh | Diagnostic only — NURBS not preserved by originating app |

**Native analytic primitives.** With *Import: native primitives* on (default),
Brep faces flagged by Rhino as planar / cylindrical / conical / spherical are
rebuilt on native OCCT `Plane`/`Cylinder`/`Cone`/`Sphere` surfaces — the analytic
parameters are *fitted* from the face geometry (rhino3dm exposes only the type
flag, not the parameters) and each fit is accepted only within tolerance,
otherwise the face falls back to NURBS. This gives cleaner solids that behave
better under booleans, fillets and draft. (Needs numpy in FreeCAD's Python;
without it every face uses NURBS.)

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

**Trimmed surfaces on export.** rhino3dm's Python bindings expose no API to
*author* Brep trim topology, so a trimmed FreeCAD face cannot yet be written as a
true trimmed Rhino Brep. The exporter instead writes the underlying (untrimmed)
NURBS **surface** and then its trim boundary as separate **NURBS curves** — both
the surface and its edges are preserved, and the face can be re-trimmed on the
Rhino side. Full trimmed-Brep export awaits trim-authoring support in rhino3dm.

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
| **Import: native primitives** (`ImportNativePrimitives`) | **On** | Rebuild planar/cylindrical/conical/spherical Brep faces on native OCCT analytic surfaces (fitted, with per-face tolerance check and NURBS fallback). Turn off to import every face as NURBS. Requires numpy. |
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

`rhino3dm` must be installed into the Python interpreter **FreeCAD actually
loads from** (its own bundled Python, or the matching per-user site). Importing
Rhino-authored *trimmed* surfaces needs **rhino3dm ≥ 8.32** (the trim-topology
read API); older versions still import untrimmed surfaces, curves and the
module's own exported files. The wheel is compiled, so it must match FreeCAD's
Python version and platform — FreeCAD 1.1 uses **CPython 3.11 (cp311)**.

Install (or upgrade), then confirm the version and the trim API in FreeCAD's
Python console:

```python
import rhino3dm as r3; print(r3.__version__)
b = r3.BoundingBox(r3.Point3d(0,0,0), r3.Point3d(1,1,1)).ToBrep()
print(hasattr(b.Faces[0], "OuterLoop"))   # True from 8.32 on
```

### FreeCAD 1.1 on macOS (Apple Silicon)

```bash
/Applications/FreeCAD_1.1.app/Contents/Resources/bin/python \
  -m pip install --upgrade "rhino3dm>=8.32"
```

### Other platforms

Find FreeCAD's Python via the console (`import sys; print(sys.executable)`),
then `/(that)/python -m pip install --upgrade "rhino3dm>=8.32"`.

### Platform notes (trim-import support)

- **Windows / modern Linux / Apple-Silicon macOS** — a cp311 wheel of rhino3dm
  ≥ 8.32 is available; the trim-import path works.
- **Linux** — the ≥ 8.32 wheel needs a modern glibc (`manylinux_2_28`, i.e.
  Ubuntu 20.04+ / RHEL 8+); older distros cap below the trim API.
- **Intel macOS** — the current universal2 wheel is tagged macOS 15+, so trimmed
  import is only available on macOS 15 (Sequoia) or newer; earlier Intel Macs
  fall back to untrimmed import.
- The trimmed-Brep import path uses **only FreeCAD's own OCCT** (no
  pythonOCC/OCC.Core needed). numpy — bundled with FreeCAD — is used for the
  native-primitive fit; without it, import falls back to NURBS surfaces.

## Installation

### Manual install (macOS / Linux)

```bash
cd ~/Library/Application\ Support/FreeCAD/Mod   # macOS
# or
cd ~/.local/share/FreeCAD/Mod                    # Linux

git clone https://github.com/KeithSloan/ImportExport_3DM.git
```

Restart FreeCAD. The importers and exporter appear automatically in
`File → Open` / `File → Import` / `File → Export`.

### From the FreeCAD Addon Manager

Not yet listed — install manually for now.

## Usage

- **Import:** `File → Open` or `File → Import` — select a `.3dm` file and
  choose `3DM` from the format dropdown.
- **Export:** `File → Export` — choose `3DM`.

## Report View diagnostics

Version and progress information is printed to the FreeCAD Report View during
import and export. The module version and rhino3dm version are printed at
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

Test `.3dm` files are in `testCases/` and `UserTestCases/`. The current set
covers trimmed **planar** faces (Cone, PolysurfCylinder, Stein), trimmed
**spherical** faces with holes (Stein), and analytic **cylinder/cone** solids.
Contributions of further test cases are welcome (must be authored in native
Rhino) — in particular a trimmed **free-form NURBS** face with a curved-boundary
cut/hole, a trimmed **cylinder/cone wall** (hole bored through the side), a face
with **multiple holes**, and a trimmed **torus**.

Additional Rhino sample files: <https://www.rhino3d.com/download/opennurbs/6/opennurbs6samples>
· Rhino API reference: <https://developer.rhino3d.com/api/rhinocommon/>

## Notes on SubD, other formats, and analysis

- **SubD.** A subdivision surface is a coarse control cage plus subdivision rules
  whose smooth *limit* is (away from extraordinary vertices) a set of bicubic
  B-spline patches — so it sits between mesh and NURBS and converts to either,
  but is *not* stored as both. rhino3dm exposes SubD topology and `Subdivide()`
  but no `ToBrep`/`ToNurbs` in the Python bindings (RhinoCommon has `SubD.ToBrep`,
  so this is an unwrapped-binding gap), which is why SubD is not yet imported as
  NURBS. A control-cage-as-mesh import is the practical near-term option.
- **NURBS and FEM.** FreeCAD's FEM workbench is mesh-based, which discretizes
  away the exact NURBS geometry. The meshless alternative for NURBS is
  **isogeometric analysis (IGA)** — using the NURBS basis directly (open-source:
  G+Smo, PetIGA, tIGAr, Nutils). FreeCAD has no native IGA today, and *trimmed*
  multi-patch models remain a research area, so an export-to-IGA companion is the
  realistic path rather than native support.

## Changes

### Import 0.3.1 — trimmed-face import crash fix

- **Fixed a hard crash (FreeCAD segfault) when importing some Rhino-authored
  trimmed surfaces.** Sewing the reconstructed faces called `Part.Solid()` on an
  *open* shell (a single trimmed face, or a shell containing a face with a hole);
  on such a shell OCCT raises a C++ `Standard_Failure` that a Python `except`
  cannot catch, which aborted FreeCAD. `Part.Solid()` is now attempted only when
  the sewn shell is genuinely closed — open shells are kept as shells. Closed
  solids (e.g. PolysurfCylinder, Cone) are unaffected. Surfaced by a
  Rhino-authored free-form trimmed face with a curved-boundary hole.

### Import 0.3.0 — official trimmed-surface import + native primitives

- **Rhino trimmed surfaces now import as trimmed faces.** Multi-face Breps are
  read via rhino3dm's official Brep trim-topology API (≥ 8.32) — `BrepFace.Loops`
  / `Trims` / `Edges` — and reconstructed as trimmed `Part` faces (outer loop +
  inner-loop holes, singular apex/pole trims skipped) sewn into a solid or shell.
  Previously a Rhino trimmed solid imported as a wireframe cage.
- **Native OCCT reconstruction — no pythonOCC.** The trim path is built on
  FreeCAD's own `Part`/OCCT API, so it no longer depends on the conda-only
  `OCC.Core` (pythonOCC) package.
- **Native analytic primitives** (`ImportNativePrimitives`, default on): planar,
  cylindrical, conical and spherical Brep faces are rebuilt on native
  `Plane`/`Cylinder`/`Cone`/`Sphere` surfaces (parameters fitted from geometry,
  per-face tolerance check, NURBS fallback, and a guard against trimming to the
  complementary region).
- **Automatic path selection.** Files with real trimmed Breps use the new path;
  the module's own exported files and older rhino3dm use the legacy
  reconstruction unchanged.

### Export 0.3.0

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
