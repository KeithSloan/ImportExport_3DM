# import3DM vs Serpentine3D - surface-area cross-check

A data-driven cross-check of the openNURBS V1-V6 sample imports. Each `.3dm`
is imported with **import3DM** (FreeCAD) and, independently, with
**Serpentine3D**, and the total surface area of the result is compared. A
large area shortfall on the Serpentine side means faces were dropped on
import. This replaces eyeballing gallery thumbnails with a number per file.

## Files
- `import3dm_sweep.tsv`  - import3DM: per file -> object count, face count, total area
- `serp_sweep.tsv`       - Serpentine3D: per file -> object count, total area
- `serp_vs_import3dm.tsv` - the two joined, with ser/imp area ratio and a flag
- `serp_area_sweep.py`   - the Serpentine sweep (headless; run with the serpentine3d venv python)
- `join_sweeps.py`       - joins the two sweeps into `serp_vs_import3dm.tsv` plus a Markdown summary (`.md`)

## How to regenerate
import3DM side, inside FreeCAD: for each sample, `import3DM.insert(f, doc.Name)`,
then sum `Shape.Area` and count faces over the `Part::Feature` objects (skip the
Origin datum planes). `nobj` counts every `Part::Feature` (curves included), as
Serpentine's object count does.

Serpentine side, with the serpentine3d venv python (keep the `__main__` guard -
Serpentine's .3dm importer uses multiprocessing, whose workers re-import the
module):

    python3 serp_area_sweep.py <samples_dir> serp_sweep.tsv

Compare: `python3 join_sweeps.py` (flags `SER_LOW` < 0.95, `SER_HIGH` > 1.05).

## Outcome - Serpentine3D 0.10.7 and the import3DM trimmed-face fix

The 0.10.3 run below was reported as Serpentine3D
[issue #34](https://github.com/chisomobanzi/Serpentine3D/issues/34) (closed).
A third reference settled it: the render meshes Rhino stores in the file,
compared face by face. The fault was on both sides.

- Serpentine3D lost area on faces running to a pole or round a seam. Fixed in
  0.10.5; verified on 0.10.7 (TreeFrog one closed solid, rhino_logo,
  MatchSrf and DinerMug recovered).
- The rest was import3DM over-reading: failed trims fell back to the whole
  untrimmed surface and holes were lost, so the "reference" was too high. Fixed
  in `import3DM.py` (tight-bbox wire guard, reliable hole cutting, a (u, v)
  rebuild for seam/pole loops, area cap, validated cone fit).

| file | Serpentine 0.10.7 | import3DM (fixed) | Rhino mesh | import3DM (old) |
|---|---|---|---|---|
| v4_TreeFrog | 6.672 | 6.671 | 6.66 | 6.658 |
| v4_WishBone | 1077.3 | 1076.6 | 1078.0 | 1625.8 |
| v4_SaltAndPepper | 26053 | 26106 | 26054 | 29521 |
| v5_disk_brake | 7051.6 | 7056.8 | 7029.2 | 9746.4 |
| v5_rhino_logo | 1058.2 | 1057.5 | 1056.7 | 1105.3 |
| v1_MatchSrf | 33404 | 33454 | - | 34445 |
| v4_Wheel_PG | 2565262 | 2569542 | - | 2913238 |
| v1_T-Joint2 | 2253.2 | 2257.1 | - | 2467.4 |
| v4_DinerMug | 42281 | 34266 * | 42256 | 35458 |

\* FreeCAD's `Shape.Area` (OCCT default integration) under-reads DinerMug's
creased body; the face is trimmed correctly. Serpentine splits creased faces
at C0 knots before integrating.

Full sweep (both TSVs regenerated: fixed import3DM, Serpentine3D 0.10.7, 138
files): 91 ok, **0 SER_LOW** (was 17), 9 SER_HIGH, 25 no-surface, 13 imp-zero.
Every #34 file agrees within 0.2 %. SER_HIGH / imp-zero are mesh and SubD
content (Serpentine counts mesh area; the import3DM sweep sums only
`Part::Feature` surfaces) plus DinerMug's crease measurement.

## Original results - Serpentine3D 0.10.3 vs import3DM (old) (137 sample files)
- 83 files import faithfully (Serpentine area within 5% of import3DM)
- 38 are curves / points (no surface to compare)
- 17 files where Serpentine drops surface area (>5%):

| file | ser/imp area | dropped |
|---|---|---|
| v4_DinerMug | 11% | 89% |
| v4_WishBone | 66% | 34% |
| rhino_logo (v1,v2,v3,v5,v6) | 69% | 31% |
| v5_disk_brake | 72% | 28% |
| v4_TreeFrog | 76% | 24% |
| MatchSrf (v1,v2,v3) | 86% | 14% |
| v4_Wheel_PG | 88% | 12% |
| v4_SaltAndPepper | 88% | 12% |
| T-Joint2 (v1,v2,v3) | 91% | 9% |

Controls that import faithfully: v4_Gear (99%), v5_ring (~100%).

Note: import3DM keeps every face of a multi-face Brep but does not sew Breps
larger than `ImportSewFaceLimit` (8 faces) into a solid, so its objects are
face-complete compounds. At the time, the import3DM area was taken as the
reference; as the outcome above shows, it over-read on the flagged files.
