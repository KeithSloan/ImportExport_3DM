**Title:** Request: Rhino SubD sample files for testing SubD → AstoCAD Forms import

**Category:** Ideas / Show and tell

Hi all,

I'm prototyping a new importer for ImportExport_3DM, `importForms3DM`, that
brings **Rhino SubD** objects into [AstoCAD](https://www.astocad.com)'s new
**Forms** workbench as *editable* Forms. The SubD control net becomes the Form's
control cage, so after import you can keep reshaping with the Forms tools instead
of getting a fixed Part shape.

Details and first results are on the wiki: [[AstoCAD Forms|AstoCAD-Forms]].

So far the only SubD test file I have is the openNURBS sample
`v6_rhino_subd_logo.3dm`. All six of its SubDs import, matching Rhino's limit
surface exactly for the all-quad, creased parts. That file doesn't exercise
several features, though, so I'm looking for **Rhino SubD `.3dm` files** that
include any of:

- **Semi-sharp creases** (Rhino 8 edge sharpness between smooth and crease)
- **Varying sharpness** along an edge (different sharpness at each end)
- **Corner vertices**
- **Open boundaries** (SubDs that aren't closed solids)
- **Dense or production-style cages** (thousands of faces)
- **Triangles and n-gons** mixed with quads
- **Symmetric models** (ideally built symmetric about a world plane)
- **Files in non-millimetre units** (inches, metres) — to test unit scaling

Small, simple files are just as useful as complex ones; one feature per file
is ideal. Rhino 7 or 8 files are fine.

If you can help, please attach files here or point to a public download, and say:

1. Which Rhino version saved the file
2. What the file is meant to test (e.g. "semi-sharp 2.5 on the top rim")
3. That it's OK to include it in the repository's `testCases/` under the
   project's licence (or tell me it's for testing only and I won't commit it)

Thanks!
Keith
