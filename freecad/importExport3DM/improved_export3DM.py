# **************************************************************************
# *   FreeCAD -> Rhino3DM Exporter                                        *
# *   Author: Keith Sloan <keith@sloan-home.co.uk>                         *
# **************************************************************************
__title__ = "FreeCAD - Export 3DM"
__author__ = "Keith Sloan <keith@sloan-home.co.uk>"

import FreeCAD, Part
from FreeCAD import Units
import rhino3dm as r3


def length(q):
    """Convert FreeCAD Quantity to float"""
    return Units.Quantity(q).Value if q else 0.0


class RhinoModel:
    """Handles creation of Rhino3DM model"""

    def __init__(self):
        self.model = r3.File3dm()
        self.model.ApplicationName = "ImportExport_3DM"
        self.model.ApplicationUrl = "https://github.com/KeithSloan/ImportExport_3DM"

    def add_brep(self, brep):
        """Add a BRep to the Rhino model"""
        if brep:
            self.model.Objects.AddBrep(brep)

    def add_curve(self, curve):
        """Add a curve to the Rhino model"""
        if curve:
            self.model.Objects.AddCurve(curve)

    def write(self, filepath):
        """Write the 3DM file"""
        self.model.Write(filepath, 0)
        FreeCAD.Console.PrintMessage(f"3DM exported to {filepath}\n")


class Exporter3DM:
    """Convert FreeCAD objects to Rhino3DM"""

    def __init__(self):
        self.rmodel = RhinoModel()

    def process_object(self, obj):
        """Dispatch object processing based on TypeId"""
        tid = obj.TypeId
        if tid in ("Part::Feature", "Part::FeaturePython"):
            self.process_shape(obj)
        elif tid == "Mesh::Feature":
            self.process_mesh(obj)
        else:
            FreeCAD.Console.PrintMessage(f"Unsupported object type: {tid}\n")

    def process_shape(self, obj):
        """Process FreeCAD Part Shape"""
        shape = getattr(obj, "Shape", None)
        if not shape:
            return

        # Process Faces (surfaces)
        for f in shape.Faces:
            if isinstance(f.Surface, Part.BSplineSurface):
                self.process_bspline_surface(f.Surface)
            elif isinstance(f.Surface, Part.Plane):
                # Planes not yet handled, skip
                FreeCAD.Console.PrintMessage("Plane surface skipped.\n")
            else:
                FreeCAD.Console.PrintMessage(f"Unsupported surface type: {type(f.Surface)}\n")

        # Process Edges (curves)
        for e in shape.Edges:
            bs = e.Curve.toNurbs()
            if bs:
                self.add_nurbs_curve(bs)

    def process_bspline_surface(self, surface):
        """Convert FreeCAD BSplineSurface to Rhino3DM NurbsSurface"""
        UDegree = surface.DegreeU
        VDegree = surface.DegreeV
        poles = [[r3.Point3d(p.X, p.Y, p.Z) for p in row] for row in surface.getPoles()]
        knotsU = surface.getUKnots()
        knotsV = surface.getVKnots()
        multsU = surface.getUMultiplicities()
        multsV = surface.getVMultiplicities()

        ns = r3.NurbsSurface.Create(3, False, UDegree + 1, VDegree + 1, len(poles), len(poles[0]))
        # Note: Full pole/weight insertion is not fully implemented yet
        # Placeholder for proper BSpline surface construction
        FreeCAD.Console.PrintMessage(f"Processed BSplineSurface U:{UDegree} V:{VDegree}\n")

    def add_nurbs_curve(self, bs_curve):
        """Convert FreeCAD BSplineCurve to Rhino3DM NurbsCurve"""
        degree = bs_curve.Degree
        poles = [r3.Point3d(p.X, p.Y, p.Z) for p in bs_curve.getPoles()]
        knots = bs_curve.getKnots()
        mults = bs_curve.getMultiplicities()
        nc = r3.NurbsCurve.Create(False, degree, poles)
        self.rmodel.add_curve(nc)

    def process_mesh(self, mesh_obj):
        """Process FreeCAD Mesh"""
        # TODO: implement mesh conversion
        FreeCAD.Console.PrintMessage("Mesh export not yet implemented.\n")

    def export_document(self, filepath):
        """Export all objects from FreeCAD ActiveDocument"""
        for obj in FreeCAD.ActiveDocument.Objects:
            self.process_object(obj)
        self.rmodel.write(filepath)


def export3DM(filepath):
    """Main entry point for FreeCAD Export"""
    exporter = Exporter3DM()
    exporter.export_document(filepath)

