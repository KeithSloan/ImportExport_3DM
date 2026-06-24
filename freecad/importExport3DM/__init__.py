import FreeCAD, os
FreeCAD.Console.PrintMessage("ImportExport_3DM: registering 3DM import/export handlers\n")
# Two import types appear in the File > Open / Import format dropdown so the user
# chooses which importer to use:
#   "3DM Non Trimmed"  -> import3DM: untrimmed NurbsSurfaces + boundary curves
#   "3DM Trimmed …"    -> import_trim_3DM: rebuilds trimmed faces via trim3dm + OCP
FreeCAD.addImportType("3DM Non Trimmed (*.3dm)",
                      "freecad.importExport3DM.import3DM")
FreeCAD.addImportType("3DM Trimmed via trim3dm (*.3dm)",
                      "freecad.importExport3DM.import_trim_3DM")
FreeCAD.addExportType("3DM (*.3dm)", "freecad.importExport3DM.export3DM")
# improved_import3DM.py and improved_export3DM.py retired — unregistered

# GUI initialisation (preferences page registration) is handled by init_gui.py,
# which FreeCAD executes during the pkgutil-based second GUI init phase.
