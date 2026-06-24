# trim3dm — call for testing (before merge to Main)

**Status: experimental / alpha, on the `trim3dm` branch.**
This document is a request for testers. The goal is to gather enough confidence —
across platforms and real models — to merge trimmed-Brep support into Main.

If you try this, **please leave feedback** (see [How to give feedback](#how-to-give-feedback)).
Even "built fine on Linux, round-trip looked right" is valuable.

---

## What this is

ImportExport_3DM (Main) round-trips Rhino `.3dm` as **untrimmed** NURBS surfaces
plus loose boundary curves, because rhino3dm's Python API cannot *construct*
trimmed Breps ([rhino3dm #712](https://github.com/mcneel/rhino3dm/issues/712)).
Trims then have to be reconstructed on re-import, which is fragile — planes and
cylinders in particular come back untrimmed.

`trim3dm` is a small standalone **pybind11 + OpenNURBS** extension that *builds
and reads* trimmed Breps directly in the `.3dm` file. It is independent of
rhino3dm — the two cooperate only at the file level (both speak OpenNURBS). With
it installed, FreeCAD can export real trimmed Breps and re-import them as proper
trimmed `Part::Face` objects.

The full round-trip has been **proven on macOS**:

```
FreeCAD trimmed face → trim3dm write → .3dm → trim3dm read → pythonOCC rebuild
                     → valid trimmed Part::Face back in FreeCAD
```

---

## What we most need help with

1. **Builds on Linux and Windows.** trim3dm has only been built and run on
   **macOS (Apple Silicon, FreeCAD 1.1, conda Python 3.11)**. The CMake +
   pybind11 setup is meant to be cross-platform but is **untested elsewhere**.
   Build notes for all three platforms are in
   [`trim3dm/README.md`](README.md). Tell us what worked / what you had to change.

2. **Real-world models.** Try your own parts, especially ones with trimmed
   planes and cylinders (the cases that look wrong on the untrimmed path).

3. **Rhino verification.** None of the maintainers currently has Rhino. If you
   do: does Rhino open the exported `.3dm` with the faces correctly trimmed?
   How do the named Breps look in the Rhino object table (see known limitation
   on groups below)?

---

## How to test

### 1. Build trim3dm

It is **not pure Python** — it must be compiled for your platform against
FreeCAD's Python (3.11 for FreeCAD 1.1). See [`trim3dm/README.md`](README.md) for
macOS / Linux / Windows instructions. On macOS, building against a conda Python
3.11 that has dev headers works well:

```bash
conda create -n trim311 python=3.11
conda activate trim311
PYTHON=$(which python) ./build.sh
```

Put the resulting `trim3dm.cpython-311-*.so` (or `.pyd` on Windows) where FreeCAD
can import it — e.g. the repo's `trim3dm/` folder, which the importer/exporter
both search.

> If trim3dm is **not** built, nothing breaks: export falls back to the untrimmed
> surfaces + curves path with a warning, and the "3DM Non Trimmed" importer works
> as on Main.

### 2. Export a trimmed `.3dm` from FreeCAD

The `ExportTrimmedBreps` preference (Edit → Preferences → Import-Export →
ImportExport 3DM) is **on by default**. Export any model to `.3dm`. With trim3dm
built, each face is written as a real trimmed Brep.

### 3. Re-import and check

In File → Open / Import, the format dropdown now has two `.3dm` entries:

| Import type | What it does |
|---|---|
| **3DM Non Trimmed** | original importer — untrimmed surfaces + boundary curves (Main behaviour) |
| **3DM Trimmed via trim3dm** | reads trims, rebuilds trimmed `Part::Face` objects |

Open the file with **3DM Trimmed via trim3dm** and confirm faces come back
trimmed (planes/cylinders bounded, not full untrimmed patches), with the object
tree (`Part → group → faces`) matching the original.

---

## Known limitations (alpha)

- **Curved trims use sampled (approximate) pcurves** — currently degree-1
  polyline 2D curves (good enough for OpenNURBS, approximate for tightly curved
  trims). Exact OCCT `CurveOnSurface` pcurves are the main precision upgrade still
  to come.
- **No real Rhino groups.** A face's parent object is encoded in the Brep *name*
  as `"{object}::{face}"`, so FreeCAD rebuilds the right tree, but in Rhino the
  Breps appear *named* `Object::Face`, not inside real groups. Proper groups need
  trim3dm to write OpenNURBS group-table entries (a C++ change + rebuild).
- **macOS-only build verification** (see above).

See the "trim3dm branch" section of [`../CLAUDE.md`](../CLAUDE.md) for the full
open-items list.

---

## How to give feedback

Please report results — positive or negative — via **GitHub Issues** or
**Discussions** on the repo:

- Your **OS, FreeCAD version, and Python version**
- Whether **trim3dm built** (and any changes you needed to `build.sh`/CMake)
- Whether the **round-trip** looked correct (attach the `.3dm` and/or a
  screenshot if you can)
- For Rhino users: how the file opens in Rhino

Thanks for helping get this to Main.
