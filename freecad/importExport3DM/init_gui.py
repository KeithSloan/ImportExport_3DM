"""
init_gui.py — executed by FreeCAD during pkgutil-based GUI initialisation
(the second init phase, after all root InitGui.py files have run).
Registers the ImportExport 3DM preferences page under
Edit → Preferences → Import-Export.

Gui::PrefCheckBox does not save/restore correctly for third-party addon
preference pages in FreeCAD 1.x (reports "Cannot restore/save PrefCheckBox").
The page therefore uses plain QCheckBox widgets and a Python class that
implements loadSettings() / saveSettings() explicitly.
"""
import FreeCAD
import FreeCADGui
import os

_ui = os.path.join(
    os.path.dirname(__file__),
    "Resources", "ui", "ImportExport3DM_prefs.ui"
)

_PARAM_PATH = "User parameter:BaseApp/Preferences/Mod/ImportExport_3DM"


class ImportExport3DMPrefs:
    """Preference page for ImportExport_3DM.
    FreeCAD calls loadSettings() when the dialog opens and
    saveSettings() when the user clicks OK / Apply."""

    def __init__(self):
        self.form = FreeCADGui.UiLoader().load(_ui)

    def loadSettings(self):
        prefs = FreeCAD.ParamGet(_PARAM_PATH)
        self.form.ExportNativePrimitives.setChecked(
            prefs.GetBool("ExportNativePrimitives", False))
        self.form.ImportCreateGroups.setChecked(
            prefs.GetBool("ImportCreateGroups", True))

    def saveSettings(self):
        prefs = FreeCAD.ParamGet(_PARAM_PATH)
        prefs.SetBool("ExportNativePrimitives",
                      self.form.ExportNativePrimitives.isChecked())
        prefs.SetBool("ImportCreateGroups",
                      self.form.ImportCreateGroups.isChecked())


try:
    FreeCADGui.addPreferencePage(ImportExport3DMPrefs, "Import-Export")
    FreeCAD.Console.PrintMessage("ImportExport_3DM: preferences page registered\n")
except Exception as e:
    FreeCAD.Console.PrintMessage(f"ImportExport_3DM: preferences registration failed: {e}\n")
