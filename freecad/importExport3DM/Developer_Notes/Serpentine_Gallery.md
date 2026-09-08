# Building the Serpentine3D vs ImportExport_3DM comparison gallery

Purpose: render the same Rhino `.3dm` samples in **Serpentine3D** (an
independent OCCT/Rhino-style modeller) and in **FreeCAD's import3DM**, and show
them side-by-side so import fidelity can be eyeballed.

Result (2026-09-08, import3DM 0.5.0): repo `serpentine_gallery/index.html`
(working copy mirrored at
`~/Workbenches/ImportExport_3DM/_serp_gallery/serpentine_vs_import3dm.html`)
— **132 of 138** rows captured. Left: FreeCAD import3DM on white. Right:
Serpentine3D 0.9.0 shaded, white viewport, with Rhino-invisible layers hidden
so both sides show the same "saved view". Six files could not be captured:

| File | Symptom in Serpentine 0.9.0's 3dm importer |
|---|---|
| `v4_Gear`, `v4_RhinoPhone`, `v4_Wheel_PG`, `v5_ring` | crash / hang even in a fresh instance |
| `v5_clip`, `v5_disk_brake` | import hangs past a long timeout on this recapture (the earlier dark-background pass captured both in fresh instances) |

## Requirements
- FreeCAD 1.1.x with this addon (`import3DM`), for the left-hand images.
- Serpentine3D installed from source (has the screenshot RPC):
  `~/github/Serpentine3D/.venv/bin/serp3d` (needs a GUI session — screenshots
  are viewport grabs, there is no headless screenshot).
- Sample `.3dm` files (the openNURBS V1-V6 set used by the wiki gallery).

## White viewport background
The viewport background is hardcoded to the dark theme constants
(`serpentine3d/ui/theme.py` `VIEWPORT_BG_TOP/BOTTOM`), and they are read at
paint time, so a small launcher overrides them before the app starts:

```python
# serp_white.py — launch with: .venv/bin/python serp_white.py
import serpentine3d.ui.theme as theme
theme.VIEWPORT_BG_TOP    = (1.0, 1.0, 1.0)
theme.VIEWPORT_BG_BOTTOM = (1.0, 1.0, 1.0)
from serpentine3d.launcher import main
raise SystemExit(main())
```

`SERP3D_NO_UPDATE_CHECK=1` and `PYOPENGL_PLATFORM=cgl` are also set on launch.

## Fairness: hide Rhino-invisible layers
Serpentine 0.9.0's `.3dm` importer ignores Rhino layer visibility — every
layer comes in "visible", so construction-history files (HumanHead's eye
layers, the Camera build, Soccer's wireframe/point layers, ...) render as a
mess. import3DM honours layer visibility (`ImportRespectLayerVisibility`), so
for an apples-to-apples comparison the Serpentine captures hide the layers
that Rhino marks invisible, using the layers RPC after import:

- precompute per-file hidden layer names from the file (`rhino3dm`: layers
  with `Visible == False`), then
- `layers {action:"visible", name: <layer>, visible: false}` for each.

Only the *visible* content is then compared on both sides.

## How a row is captured
Drive Serpentine over its JSON-per-line RPC (port in
`~/.serpentine3d/rpc.port`, default 5757):
1. `command {command:"new", inputs:["Yes"]}` — clear the scene
2. `import_file {path: <file>}`
3. `layers {action:"visible", ...}` for each Rhino-hidden layer (see above)
4. `set_viewport {view:"isometric", display_mode:"shaded", zoom_extents:true, grid:false}`
5. `screenshot {path: <out>.png, width:480, height:360}`

A shared GUI session works for most files, but a handful hang or crash the
importer (`v4_Gear`, ...): keep a bad list, and for hang/crash recovery
capture one file per **fresh** instance (launch -> import -> screenshot ->
kill) so a hang costs only that file. Deterministic import bugs ("Add():
incompatible function arguments") are file-specific and can differ between a
shared session and a fresh instance, so isolated retries often succeed.

## FreeCAD side and assembly
1. Render the FreeCAD side with `macros/make_3dm_gallery.FCMacro` (produces
   480x360 white-background PNGs). The macro pins the import prefs and adds a
   tiny sphere "anchor" at degenerate single-point clouds so isolated points
   are visible (spheres, not the oversized boxes an earlier revision used).
2. Assemble the page next to two folders — `import3dm/` (FreeCAD PNGs) and
   `serpentine/` (Serpentine PNGs) — with `index.html` listing one row per
   sample, side by side; rows Serpentine could not capture show a "not
   captured" cell instead of an image.

## Reproduce
Drivers used for the 2026-09-08 white recapture (kept in `/tmp/ie3dm/`,
machine-specific paths):
- `prep_layers.py` — writes per-file hidden-layer names to
  `/tmp/ie3dm/hidden_layers.json`
- `cap_white.py` — shared-session white capture with hidden-layer hiding,
  self-healing relaunch of the Serpentine instance
- `cap_white_isolated.py` / `cap_white_retry.py` — fresh-instance capture for
  the files that hang the shared session
- `deploy_white_gallery.py` — rebuilds repo `serpentine_gallery/` from the
  wiki `images/` (overlaid with freshly regenerated FreeCAD rows) plus the
  white Serpentine captures, and mirrors into `_serp_gallery/`
