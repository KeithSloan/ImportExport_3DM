# Claude Code Instructions — ImportExport_3DM

## Project context

ImportExport_3DM adds Rhino `.3dm` file import and export to FreeCAD.
It is a **FreeCAD module** (not a workbench) — it registers file handlers via
`addImportType`/`addExportType` and appears in FreeCAD's File → Open/Import
and File → Export dialogs.  No workbench UI, toolbar, or menu items.

Source lives at `/Users/ksloan/Workbenches/ImportExport_3DM/`.
FreeCAD loads straight from this directory — there is no separate install step.

## Repository layout

```
freecad/importExport3DM/
  __init__.py               ← registers import/export handlers (entry point)
  init_gui.py               ← intentionally empty
  import3DM.py              ← primary importer (Brep, NurbsSurface, curves)
  improved_import3DM.py     ← alternate importer (registered separately)
  export3DM.py              ← primary exporter
  improved_export3DM.py     ← alternate exporter (registered separately)
  objects3DM.py             ← Surface3DM FeaturePython object class
  Resources/icons/
    ImportExport_3DM.svg    ← package icon (referenced in package.xml)
    3dm-file-format-extension.svg
  Developer_Notes/          ← developer documentation
package.xml                 ← FreeCAD addon manifest (content type: other)
metadata.txt                ← legacy metadata (pylibs=rhino3dm only)
testCases/                  ← .3dm test files for round-trip testing
```

## Module registration

`__init__.py` registers four handlers:

| Handler | Type | Module |
|---|---|---|
| `3DM Importer (*.3dm)` | import | `import3DM` |
| `3DM Improved Importer (*.3dm)` | import | `improved_import3DM` |
| `3DM (*.3dm)` | export | `export3DM` |
| `3DM Improved Exporter (*.3dm)` | export | `improved_export3DM` |

FreeCAD calls `open(filename)` / `insert(filename, docname)` on import,
and `export(objects, filename)` on export.

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

## Companion repos

| Repo | Path | Purpose |
|---|---|---|
| Blender_Export_3DM | `/Users/ksloan/github/Blender_Export_3DM/` | Blender → 3DM exporter |
| KS_JK_import_3dm | `/Users/ksloan/github/KS_JK_import_3dm/` | Blender 3DM importer (for round-trip testing) |
| KS_CurvesWB | `/Users/ksloan/Workbenches/KS_CurvesWB/` | FreeCAD NURBS workbench |

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

## package.xml notes

- `<content><other>` — module, not workbench; no classname needed
- `<freecadmin>1.1</freecadmin>` — requires FreeCAD 1.1+
- `<depend>rhino3dm</depend>` — Python dependency; must be installed into
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
