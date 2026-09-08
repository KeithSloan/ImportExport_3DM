import FreeCAD, os, glob
FreeCAD.Console.PrintMessage("ImportExport_3DM: registering 3DM import/export handlers\n")
# One import type only ("3DM") -> import3DM.  import3DM handles everything and
# automatically uses the enhanced trimmed-Brep reader (the compiled trim3dm
# C++/OpenNURBS extension) when it is detected, giving complete trimmed solids
# (e.g. v4_TreeFrog) from the real 2D trim data.  Without a build it falls back
# to its native rhino3dm reconstruction.
#
# NOTE: an experimental "SubD as exact NURBS limit patches + control-net cage"
# path exists (import3DM_subd / importSubD.makeSubD, driven by
# import3DM._SUBD_AS = "subd"). It is NOT registered as a user-facing import
# type because the reconstruction is incomplete around extraordinary vertices
# (valence != 4) -> holes -> blocky tessellation. It is retained in the repo
# for future completion (Stam eigenbasis evaluation at extraordinary points).
FreeCAD.addImportType("3DM (*.3dm)",
                      "freecad.importExport3DM.import3DM")
FreeCAD.addExportType("3DM (*.3dm)", "freecad.importExport3DM.export3DM")


def _trim3dm_built():
    """True when a compiled trim3dm extension sits next to this addon (in the
    repo's trim3dm/ folder or the addon dir) — checked by filename so startup
    does not import the C extension."""
    here = os.path.dirname(os.path.abspath(__file__))
    for cand in (os.path.abspath(os.path.join(here, "..", "..", "trim3dm")),
                 here):
        if (glob.glob(os.path.join(cand, "trim3dm*.so"))
                or glob.glob(os.path.join(cand, "trim3dm*.pyd"))):
            return True
    return False


if _trim3dm_built():
    FreeCAD.Console.PrintMessage(
        "import 3DM - Trimmed Edges SUPPORTED (trim3dm extension found)\n")
else:
    FreeCAD.Console.PrintMessage(
        "import 3DM - Trimmed Edges NOT SUPPORTED - Please build Trim3D\n"
        "(compile trim3dm with trim3dm/build.sh and place the .so/.pyd next to "
        "this addon)\n")

# GUI initialisation (preferences page registration) is handled by init_gui.py,
# which FreeCAD executes during the pkgutil-based second GUI init phase.
