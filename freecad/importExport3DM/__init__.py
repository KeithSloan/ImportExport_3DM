import FreeCAD
print(f"Set Importer and exporter for 3dm")
FreeCAD.addImportType("3DM Importer (*.3dm)","freecad.importExport3DM.import3DM")
FreeCAD.addImportType("3DM Improved Importer (*.3dm)","freecad.importExport3DM.improved_import3DM")
FreeCAD.addExportType("3DM (*.3dm)","freecad.importExport3DM.export3DM")
FreeCAD.addExportType("3DM Improved Exporter (*.3dm)","freecad.importExport3DM.improved_export3DM")
#FreeCAD.addExportType("3DM (*.3DM)","freecad.importExport3DM.export3DM")
