import FreeCAD
print(f"Set Importer and exporter for 3dm")
FreeCAD.addImportType("3DM importer (*.3dm)","freecad.importExport3DM.import3DM")
FreeCAD.addExportType("3DM (*.3dm)","freecad.importExport3DM.export3DM")
FreeCAD.addExportType("3DM (*.3DM)","freecad.importExport3DM.export3DM")
