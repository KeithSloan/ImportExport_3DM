# Claude Code Instructions — ImportExport_3DM

## Project context

ImportExport_3DM adds Rhino `.3dm` file import and export to FreeCAD.
It is a **FreeCAD Import/Export module** (not a workbench) — it registers file
handlers via `addImportType`/`addExportType` and appears in FreeCAD's
File → Open/Import and File → Export dialogs.  No UI, toolbar, or menu items.

Source lives at `/Users/ksloan/Workbenches/ImportExport_3DM/`.
FreeCAD loads straight from this directory — there is no separate install step.

**Important:** The older `ImportNURBS` addon also registers `*.3dm` handlers and must
be disabled to prevent it silently taking precedence over this module.
It has been renamed to `ImportNURBS.disabled` in the FreeCAD Mod directory:
`~/Library/Application Support/FreeCAD/v1-1/Mod/ImportNURBS.disabled`

## Repository layout

```
freecad/importExport3DM/
  __init__.py               ← registers import/export handlers (entry point)
  init_gui.py               ← registers Preferences page (pkgutil GUI init phase)
  import3DM.py              ← primary importer (Brep, NurbsSurface, curves)
  improved_import3DM.py.retired  ← removed — unregistered
  export3DM.py              ← primary exporter (all surface types)
  improved_export3DM.py.retired  ← removed — entry point and output were stubs
  objects3DM.py             ← Surface3DM FeaturePython object class
  Resources/
    icons/
      ImportExport_3DM.svg  ← module icon (referenced in package.xml)
    ui/
      ImportExport3DM_prefs.ui  ← Preferences page (ExportNativePrimitives)
  Developer_Notes/          ← developer documentation
InitGui.py                  ← present but unused; FreeCAD treats this addon as a namespace
                              package and uses the pkgutil init phase (init_gui.py) instead
package.xml                 ← FreeCAD addon manifest (content type: other)
metadata.txt                ← legacy metadata (pylibs=rhino3dm only)
testCases/                  ← .3dm test files for round-trip testing
```

## Module registration

`__init__.py` registers two handlers:

| Handler | Type | Module |
|---|---|---|
| `3DM (*.3dm)` | import | `import3DM` |
| `3DM (*.3dm)` | export | `export3DM` |

FreeCAD calls `open(filename)` / `insert(filename, docname)` on import,
and `export(exportList, filename)` on export.

## Importer architecture (`import3DM.py`)

The importer uses `rhino3dm` to read the `.3dm` file and dispatches on object
type:

| rhino3dm type | FreeCAD result |
|---|---|
| `Brep` | `Part::Feature` via `Part.Shape` from OCCT |
| `NurbsSurface` | `Part::Feature` with BSplineSurface shell |
| `NurbsCurve` | `Part::Feature` with BSplineCurve wire |
| `SubD` | diagnostic message (not imported — NURBS not preserved) |
| `Mesh` | diagnostic message (not imported — NURBS not preserved) |

Key importer options (set at top of `import3DM.py`):
- `merge_brep_faces` — whether to merge Brep faces into a single shell or
  keep them as separate face objects

### Trim reconstruction and degenerate-face fallback

When pythonOCC is available, `_try_trim_reconstruction` rebuilds a trimmed
`Part::Feature` from a NurbsSurface plus its exported boundary curves
(`BRepBuilderAPI_MakeFace` + `ShapeFix_Wire`). This reconstruction can produce a
face without valid pcurves — a zero-area, `isValid()==False` face that renders as
a collapsed/straight patch, especially for irregularly-trimmed faces (mixed
arc/line/blend boundaries).

The importer therefore validates the reconstructed face: if it is null, invalid,
or has near-zero area, it first tries `Shape.fix()`, and if still degenerate it
falls back to the **untrimmed** surface (which is valid and correctly curved,
because the exporter segments each surface to the exact face extent). This is
what keeps round-tripped cylinders curved rather than flat.

## Companion repos

| Repo | Path | Purpose |
|---|---|---|
| Blender_Export_3DM | `/Users/ksloan/github/Blender_Export_3DM/` | Blender → 3DM exporter |
| KS_JK_import_3dm | `/Users/ksloan/github/KS_JK_import_3dm/` | Blender 3DM importer (for round-trip testing) |
| KS_CurvesWB | `/Users/ksloan/Workbenches/KS_CurvesWB/` | FreeCAD NURBS curves module |

## Blender → 3DM → FreeCAD pipeline

```
Blender / Surface Psycho NURBS geometry
    ↓  Blender_Export_3DM extension
.3dm file
    ↓  File → Open / Import in FreeCAD
Part::Feature (BSplineSurface or BSplineCurve)
    ↓  KS_CurvesWB Import commands (optional)
Editable NurbsSurfaceFP / NurbsCurveFP objects
```

## Export preferences

Stored under `User parameter:BaseApp/Preferences/Mod/ImportExport_3DM`.
Exposed in FreeCAD Edit → Preferences → Import-Export → ImportExport 3DM.

| Key | Type | Default | Effect |
|---|---|---|---|
| `ExportNativePrimitives` | Bool | **False** | Write Cylinder/Cone/Sphere/Torus as rhino3dm native primitives instead of converting to NURBS. Default off: the bounded-NURBS path reconstructs trim boundaries more reliably on re-import. |
| `ImportCreateGroups` | Bool | True | On import, create `App::DocumentObjectGroup` objects to mirror 3DM named groups. Set False to place objects directly under the Part with no same-named wrapper groups. |
| `ImportMakeShell` | Bool | False | After collecting a group's surfaces, attempt `Part.makeShell()` / `makeSolid()`; falls back to individual surfaces. |

**Note:** the code default for `ExportNativePrimitives` is `False`
(`getExportNativePrimitives()` in `export3DM.py`). `processSurfaceSphere` always
bypasses the native path regardless of the preference (degenerate pole/seam edge
on re-import).

## Export grouping

Each FreeCAD object exported creates a named rhino3dm group via `model.Groups.Add(obj.Label)`.
Every face/curve/surface added for that object carries `ObjectAttributes.AddToGroup(idx)`.
This means in Rhino/rhino3dm the faces of e.g. `"Wing_Left"` are grouped together and the group
is named `"Wing_Left"`.

`rhinoModel._makeAttrs()` is the single helper that builds `ObjectAttributes` with the current
group index (`self._group_idx`); all `AddBrep` / `AddSurface` / `AddCurve` calls use it.

## Import naming and grouping

`parse_objects` reads `r3_obj.Attributes.Name` and assigns it to `obj.Label` after creation,
so imported objects carry their original Rhino name instead of the generic type string.

If `ImportCreateGroups` is True (default), objects that belong to a 3DM group are placed inside
a matching `App::DocumentObjectGroup`. Group names come from `f3dm.Groups[i].Name`.
Objects with no group membership are placed directly in the top-level Part.

If `ImportCreateGroups` is False, no container objects are created. Instead, group membership is
encoded in the label: surfaces keep their own name; curves get `{groupName}_{curveName}` so the
association is visible in the model tree without structural grouping.

## Object traversal (`addObjToModel`)

`addObjToModel(obj, visited)` is container-aware and shape-driven (not a fixed
TypeId whitelist):

- **Containers** (`App::Part`, `App::Link`, `App::LinkGroup`,
  `App::DocumentObjectGroup`, `Std::Part`) — recurse into children
  (`.Group`/`.OutList`); export no shape of their own.
- **`PartDesign::Body`** — export the body's final solid once (`Body.Shape`); do
  not iterate its individual features (would emit overlapping intermediate
  solids).
- **Datum/helper objects** (origins, planes, sketches) — skipped.
- **Anything else with a non-null `Shape`** — exported via `checkShape`.

A `visited` set guards against double-exporting shared/linked objects. `export()`
exports the whole selection list, not just `exportList[0]`.

## NURBS fidelity (weight-preserving builders)

rhino3dm control points are **homogeneous**: `Point4d(x, y, z, w)` has Euclidean
location `(x/w, y/w, z/w)`. To place a pole `P` with weight `w`, write
`Point4d(P.x*w, P.y*w, P.z*w, w)` **and** create the surface/curve as rational
(`Create(..., rational=True, ...)`), otherwise weights are ignored.

- `_makeR3Surface(surface)` / `_makeR3Curve(bs)` read `getWeights()`, detect
  rationality, create the rhino object rational when any weight ≠ 1, and write
  homogeneous control points. Periodic surfaces/curves are converted to clamped
  form first (`setUNotPeriodic` / `setVNotPeriodic` / `setNotPeriodic`) so the
  drop-first/last knot convention matches.
- `_arcEdgeToR3(edge, crv)` writes circular/arc edges as **exact** degree-2
  rational arcs (≤90° rational Bézier segments, middle weight `cos(half-angle)`)
  instead of FreeCAD's high-degree non-rational `toBSpline()` approximation, so
  boundary curves lie exactly on the rational surface.
- `_edgeToNurbsCurve3D` preference order: exact rational arc → weight-preserving
  BSpline → discretised polyline.

Forcing weights to 1.0 (the old behaviour) turned a circle's control polygon into
a rounded square — the "cylinders with straight edges" symptom.

## Exporter surface dispatch (`export3DM.py`)

`processSurface()` dispatches on `type(face.Surface)`. Analytic surfaces default
to the bounded-NURBS path (`processSurfaceGeneric` → `face.toNurbs()` →
`processBSplineSurface` → `processSurfaceUV` → `_makeR3Surface`); native
primitives are used only when `ExportNativePrimitives` is on.

| FreeCAD type | Handler | Notes |
|---|---|---|
| `Part.BSplineSurface` | `processBSplineSurface` | NURBS copy (weights preserved) |
| `Part.Plane` | `processSurfacePlane` | `toNurbs()` first, bilinear patch fallback |
| `Part.Cylinder` | `processSurfaceCylinder` | generic (rational NURBS) unless native enabled |
| `Part.Cone` | `processSurfaceCone` | generic unless native enabled |
| `Part.Sphere` | `processSurfaceSphere` | always generic (native bypassed) |
| `Part.Toroid` | `processSurfaceToroid` | generic unless native enabled |
| anything else | `processSurfaceGeneric` | `face.toNurbs()` then `toBSpline()` |

`processSurfaceUV` no longer has a special ruled-surface branch — it always uses
the weight-preserving `_makeR3Surface` (the old ruled branch rebuilt cylinder
rails non-rationally and dropped the circular weights).

## package.xml notes

- `<content><other>` — Import/Export module, not a workbench; no classname needed
- `<freecadmin>1.1</freecadmin>` — requires FreeCAD 1.1+
- `<depend version_min="8.0.0">rhino3dm</depend>` — must be installed into
  FreeCAD's Python interpreter (see README for install commands)
- Icon: `freecad/importExport3DM/Resources/icons/ImportExport_3DM.svg`

## FreeCAD version convention

The user runs FreeCAD 1.1 on macOS.  The app bundle may be named
`/Applications/FreeCAD_1.1.app` or similar.  Always verify the exact path
before running FreeCAD-related shell commands.

## testCases directory

Round-trip test `.3dm` files (Rhino-originated) used by `KS_JK_import_3dm`
and `Blender_Export_3DM` batch test scripts.  Also copied into
`/Users/ksloan/github/Blender_Export_3DM/Sample_3DM_Files/`.

## Version bumping rule

**Bump versions only when changes are tested and ready to commit/push —
not during active development.**

Files covered: `import3DM.py`, `improved_import3DM.py`, `export3DM.py`.

Steps:
1. When the user confirms a batch of changes is ready to commit, increment
   `__version__` in each changed file (semver: patch for fixes, minor for
   new surface types or features).
2. The version is printed automatically to the FreeCAD Report View at load
   time — no extra code change needed for that.
3. Update `package.xml` `<version>` to match the highest version across all
   three files at the same time.
