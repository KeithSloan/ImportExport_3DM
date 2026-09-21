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

## How to regenerate
import3DM side, inside FreeCAD: for each sample, `import3DM.insert(f, doc.Name)`,
then sum `Shape.Area` and count faces over the `Part::Feature` objects (skip the
Origin datum planes).

Serpentine side, with the serpentine3d venv python (keep the `__main__` guard -
Serpentine's .3dm importer uses multiprocessing, whose workers re-import the
module):

    python3 serp_area_sweep.py <samples_dir> serp_sweep.tsv

Compare: join by file name; flag where `ser_area / imp_area < 0.95`.

## Results - Serpentine3D 0.10.3 vs import3DM (137 sample files)
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
face-complete compounds - the area total is still the correct reference.
