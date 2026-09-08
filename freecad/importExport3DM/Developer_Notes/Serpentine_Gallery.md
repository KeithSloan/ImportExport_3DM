# Building the Serpentine3D vs ImportExport_3DM comparison gallery

Purpose: render the same Rhino `.3dm` samples in **Serpentine3D** (an
independent, MIT-licensed OCCT/Rhino-style modeller) and in **FreeCAD's
import3DM**, and show them side-by-side so import fidelity can be eyeballed.

Result so far: repo `serpentine_gallery/index.html` (working copy also at
`~/Workbenches/ImportExport_3DM/_serp_gallery/serpentine_vs_import3dm.html`)
— **106 of 139** samples captured (all of V1–V3 plus V4's first three). The
remaining 33 crash/hang Serpentine3D's own 3dm importer (`v4_Gear` etc., most
of V4, all of V5/V6) and are shown as "not captured" in the table.

## Requirements
- FreeCAD 1.1.x with this addon (`import3DM`), for the left-hand images.
- Serpentine3D installed from source (has the screenshot RPC):
  `~/github/Serpentine3D/.venv/bin/serp3d` (see the repo's README; needs a GUI
  session — screenshots are viewport grabs, there is no headless screenshot).
- Sample `.3dm` files (the openNURBS V1–V6 set used by the wiki gallery).

## How the gallery was produced
1. Render the FreeCAD side with `macros/make_3dm_gallery.FCMacro` (produces the
   wiki `images/*.png`, 480x360, white background).
2. Launch Serpentine3D GUI. At first start it shows an "open file / show at
   each startup" prompt and a macOS Gatekeeper notice for the unsigned build —
   approve once and uncheck "show at each startup".
   - macOS Gatekeeper: `xattr -dr com.apple.quarantine "/Applications/Serpentine3D.app"`
     or right-click → Open.
   - Source install: `PYOPENGL_PLATFORM=cgl ~/github/Serpentine3D/.venv/bin/serp3d`
     (CGL is required on macOS or the viewport fails with an EGL import error).
3. Serpentine3D listens on `127.0.0.1:<port>` where the port is in
   `~/.serpentine3d/rpc.port` (default 5757). Protocol: one JSON object per
   newline — `{"method": ..., "params": {...}, "id": 1}` → `{"result": ...}`.
4. For each sample file, drive it over that RPC:
   - `command {command:"new", inputs:["Yes"]}` — clears the scene
   - `import_file {path: <file>}`
   - `set_viewport {view:"isometric", display_mode:"shaded", zoom_extents:true, grid:false}`
   - `screenshot {path: <out.png>, width:480, height:360}`
5. Capture one file per scene (files must not be imported into the same scene).
   A few files crash/hang Serpentine's 3dm import helper (e.g. `v4_Gear`): keep
   a "bad" list, skip those, and if an import call returns garbage or the
   connection dies, mark that file bad and restart the app before continuing.
6. Assemble `_serp_gallery/`: `import3dm/` (FreeCAD PNGs), `serpentine/`
   (Serpentine PNGs), and `serpentine_vs_import3dm.html` (one row per file,
   side-by-side). Files Serpentine could not capture get an explanatory cell.

- Hang/crash isolation: some `.3dm` files hang or crash Serpentine's importer
  inside the shared GUI (v5_ring, v5_teacup, …). For those, or for any batch,
  capture each file in its OWN fresh instance: launch `serp3d`, import the one
  file, screenshot, then kill the instance. A hang then costs only that file.
  Driver: `python3 tools/serp_gallery/cap_isolated.py` (launches/kills its own
  instances; records failures in `tools/serp_gallery/serp_bad.txt`).
  Deterministic import bugs ("Add(): incompatible function arguments") are
  file-specific and can differ between a shared session and a fresh instance,
  which is why isolated retries often succeed.

## Reproduce
Capture driver (per pass; run while the Serpentine GUI is open):
- `python3 tools/serp_gallery/cap_pass.py`  — captures any missing file,
  skipping the bad list in `tools/serp_gallery/serp_bad.txt`; stops when the
  app crashes (run from the repo root while the Serpentine GUI is open).
- After each pass that crashes the app, relaunch Serpentine3D and re-run.

Rebuild the comparison page any time with:
`python3 tools/serp_gallery/build_gallery.py <imp_dir> <serp_dir> <out.html>`
(The working `/tmp` copies were moved into `tools/serp_gallery/` for reuse.)
