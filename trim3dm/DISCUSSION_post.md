<!-- Draft GitHub Discussion post.
     Suggested category: "Show and tell" or "General".
     Title: Testing wanted — trimmed-Brep .3dm round-trip (trim3dm branch) before merge to Main -->

# Testing wanted: trimmed-Brep `.3dm` round-trip (`trim3dm` branch)

**TL;DR:** there's an experimental branch that makes FreeCAD export *real trimmed
Breps* to `.3dm` and re-import them as trimmed faces — fixing the "planes and
cylinders come back untrimmed" problem. I'd like help testing it before merging to
Main, especially **building it on Linux and Windows** (only macOS is tested so
far).

## Background

Main round-trips `.3dm` as **untrimmed** NURBS surfaces plus loose boundary
curves, because rhino3dm's Python API can't *construct* trimmed Breps
([rhino3dm #712](https://github.com/mcneel/rhino3dm/issues/712)). Trims then get
reconstructed on re-import, which is fragile — trimmed planes and cylinders in
particular come back as full untrimmed patches.

The `trim3dm` branch adds a small standalone **pybind11 + OpenNURBS** extension
that builds and reads trimmed Breps directly in the `.3dm` file. It's independent
of rhino3dm — they cooperate only at the file level (both speak OpenNURBS).

The full round-trip is **proven on macOS**:

```
FreeCAD trimmed face → trim3dm write → .3dm → trim3dm read → pythonOCC rebuild
                     → valid trimmed Part::Face back in FreeCAD
```

## What I'd love help with

1. **Building on Linux / Windows.** trim3dm has only been built and run on macOS
   (Apple Silicon, FreeCAD 1.1, conda Python 3.11). The CMake/pybind11 setup is
   meant to be cross-platform but is untested elsewhere.
2. **Real models** — anything with trimmed planes and cylinders.
3. **Rhino verification** — I don't currently have Rhino. Does the exported
   `.3dm` open with the faces correctly trimmed?

## How to try it

Check out the `trim3dm` branch and follow
[`trim3dm/TESTING.md`](trim3dm/TESTING.md) — it covers building the extension,
turning on `ExportTrimmedBreps`, and re-importing with the new **"3DM Trimmed via
trim3dm"** import type. If trim3dm isn't built, nothing breaks: export falls back
to the untrimmed path with a warning.

## Known limitations (alpha)

- Curved trims use sampled (approximate) pcurves for now.
- Faces are *named* `Object::Face` in Rhino rather than placed in real Rhino
  groups (FreeCAD rebuilds the correct tree from the name).

## Please reply with

- Your OS, FreeCAD version, Python version
- Whether trim3dm built (and any tweaks you needed)
- Whether the round-trip looked right (a screenshot or sample `.3dm` is great)
- Rhino users: how it opens in Rhino

Thanks — feedback here will decide when this is solid enough to merge to Main.
