# Draft issue for chisomobanzi/Serpentine3D

**Title:** Some `.3dm` imports silently drop surfaces (area shortfall vs source)

**Version:** Serpentine3D 0.10.3, macOS 26.1

## What happens

Following up on the gallery cross-check from #10: I imported the whole
openNURBS V1-V6 sample set into Serpentine3D and, independently, via my FreeCAD
`import3DM` workbench (which preserves every face of a Brep), and compared
**total surface area** per file. Most files match, but **17 files come in with
materially less surface area in Serpentine3D** - faces are dropped on import,
silently (no error).

It is model-specific, not universal: 83 of the surface-bearing files import
within 5% of the source, so most are fine.

## Worst cases (Serpentine area / source area)

```text
file                          ser/src   surface lost
v4_DinerMug                     11%        ~89%
v4_WishBone                     66%        ~34%
rhino_logo (v1,v2,v3,v5,v6)     69%        ~31%
v5_disk_brake                   72%        ~28%
v4_TreeFrog                     76%        ~24%
MatchSrf (v1,v2,v3)             86%        ~14%
v4_Wheel_PG                     88%        ~12%
v4_SaltAndPepper                88%        ~12%
T-Joint2 (v1,v2,v3)             91%         ~9%
```

Faithful controls: `v4_Gear` (99%), `v5_ring` (~100%).

## Notable pattern

In several cases Serpentine produces *more* objects but *less* area - e.g.
`MatchSrf` 15->38 objects, `v5_disk_brake` 66->79 - so it appears to be
fragmenting / re-trimming the polysurface and losing faces in the process.

`v4_TreeFrog` is a clean minimal repro: the file is one **closed 83-face
solid**, but Serpentine imports it as a single open **surface** and drops ~24%
of the area (visibly, the eye domes go missing).

## How to reproduce

Import each file, sum the surface area of the resulting objects, compare to the
source. Measured headless via `serpentine3d.scripting.Document`
(area = `geo.surface_area`), which matches the GUI import exactly. Per-file
numbers and the sweep script are in this repo under `tools/serp_gallery/`
(`serp_vs_import3dm.tsv`, `serp_area_sweep.py`).
