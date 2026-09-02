import FreeCAD, os
FreeCAD.Console.PrintMessage("ImportExport_3DM: registering 3DM import/export handlers\n")
# Import types shown in the File > Open / Import format dropdown (first = default):
#   "3DM"  -> import3DM: native Rhino files, curves, NurbsSurfaces, trimmed
#             Breps (official rhino3dm path). SubD objects are imported as their
#             subdivided limit SURFACE (smooth mesh), with the Rhino control-net
#             meshes auto-hidden.
#   "3DM Trimmed via trim3dm" -> import_trim_3DM: rebuilds trimmed faces via the
#             trim3dm C++/OpenNURBS extension (robust on complex trimmed solids
#             and FreeCAD-exported trimmed files).
#
# NOTE: an experimental "SubD as exact NURBS limit patches + control-net cage"
# path exists (import3DM_subd / importSubD.makeSubD, driven by
# import3DM._SUBD_AS = "subd"). It is NOT registered as a user-facing import
# type because the reconstruction is incomplete around extraordinary vertices
# (valence != 4) -> holes -> blocky tessellation. It is retained in the repo
# for future completion (Stam eigenbasis evaluation at extraordinary points).
FreeCAD.addImportType("3DM (*.3dm)",
                      "freecad.importExport3DM.import3DM")
FreeCAD.addImportType("3DM Trimmed via trim3dm (*.3dm)",
                      "freecad.importExport3DM.import_trim_3DM")
FreeCAD.addExportType("3DM (*.3dm)", "freecad.importExport3DM.export3DM")

# GUI initialisation (preferences page registration) is handled by init_gui.py,
# which FreeCAD executes during the pkgutil-based second GUI init phase.
