# Serpentine3D — batch-import issue report (draft for the upstream repo)

**Project:** https://github.com/chisomobanzi/Serpentine3D
**Component:** `.3dm` import (`fileio.rhino.import_3dm`) over long GUI sessions
**Version tested:** Serpentine3D 0.9.0 (pip install from source), Python 3.13,
macOS (arm64), Qt/PySide6, cadquery-ocp 7.9.3.1.1

## Summary

Driving Serpentine3D over its RPC port (localhost JSON-RPC, newline-delimited
JSON as implemented in `serpentine3d/rpc.py`) to batch-import 138 Rhino `.3dm`
sample files, one scene per file (`command new [Yes]` → `import_file` →
`set_viewport` → `screenshot`), I found two behaviours that look like
**session-state pollution rather than file problems**:

1. A file that fails or hangs when imported inside a long-lived session often
   **imports fine in a fresh instance** of the app.
2. Failures only start appearing after many (~100+) imports in the same
   session, then hit files that are otherwise importable.

## Evidence: shared session vs fresh instance

All runs used the same files and the same RPC sequence; the only difference was
whether the import happened in a session that had already imported many files,
or in a just-launched instance.

| File | In long-lived session | Fresh instance |
|---|---|---|
| `v4_MechPartA.3dm` | Import failed (`Add(): incompatible function arguments`) | **OK** |
| `v4_PerfumeBottle_Solid.3dm` | Import failed | **OK** |
| `v4_Prarie settle.3dm` | Import failed | **OK** |
| `v4_SaltAndPepper.3dm` | Import failed | **OK** |
| `v4_SolidHandle.3dm` | Import failed | **OK** |
| `v5_clip.3dm` | Import failed | **OK** |
| `v5_disk_brake.3dm` | Import failed | **OK** |
| `v5_teacup.3dm` | Import hang (timeout) | **OK** |
| `v5_teapot.3dm` | Import failed/hang | **OK** |
| `v6_rhino_logo.3dm` | Import failed | **OK** |
| `v6_rhino_subd_logo.3dm` | Import failed | **OK** |

The V1–V3 sample set (~103 files) imported cleanly in one session before the
failures began, which points to accumulation (state, memory, GL resources,
helper process, layer/name tables) rather than the individual files.

## Files Serpentine3D cannot import even in a fresh instance

These consistently crash/hang the importer (worth a separate look):

- `v4_Gear.3dm` — hard crash / hang of the import
- `v4_RhinoPhone.3dm` — hang/crash
- `v4_Wheel_PG.3dm` — import never returns (timeout)
- `v5_ring.3dm` — import never returns (timeout)

## Suspected causes (in order of likelihood)

1. **`new`/Clear does not fully reset state.** After hundreds of imports the
   layer table, undo/history checkpoints, object-name/ID counters, or selection
   are left in a state that makes subsequent `Add()` calls fail with
   `Add(): incompatible function arguments`.
2. **Failed imports leave partial state.** An import that errors mid-way may
   leave half-added objects / a dirty history that contaminates the next
   import.
3. **Resource growth.** GPU mesh buffers / spawned import helper processes
   accumulate over ~100 imports.

## Repro via RPC (no GUI interaction needed)

```python
# launch: ~/.../serp3d   (GUI must be running; port in ~/.serpentine3d/rpc.port)
# then, per file:
send({"method":"command","params":{"command":"new","inputs":["Yes"]},"id":1})
send({"method":"import_file","params":{"path":"/path/v4_MechPartA.3dm"},"id":1})
```

Repeat for ~100+ `.3dm` files in one session and observe that later imports of
files that worked early on start failing, while the same file succeeds in a
fresh `serp3d` process.

Suggested instrumentation for the fix: log `scene_info` (object count, layer
list, object names) before/after each `new` and each `import_file` to see which
table is not being reset.

## How we produced the comparison gallery

See `freecad/importExport3DM/Developer_Notes/Serpentine_Gallery.md` in the
ImportExport_3DM repo, plus `tools/serp_gallery/` there for the drivers used.
