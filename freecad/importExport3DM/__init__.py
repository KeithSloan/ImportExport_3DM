import FreeCAD, os
FreeCAD.Console.PrintMessage("ImportExport_3DM: registering 3DM import/export handlers\n")
FreeCAD.addImportType("3DM (*.3dm)", "freecad.importExport3DM.import3DM")
FreeCAD.addExportType("3DM (*.3dm)", "freecad.importExport3DM.export3DM")
# improved_import3DM.py and improved_export3DM.py retired — unregistered

# GUI initialisation (preferences page registration) is handled by init_gui.py,
# which FreeCAD executes during the pkgutil-based second GUI init phase.
