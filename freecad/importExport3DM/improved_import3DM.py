import FreeCAD, FreeCADGui
import Part, Draft, math, Mesh
import os
import rhino3dm as r3
from freecad.importExport3DM.objects3DM import ViewProvider

# -------------------------
# Utility Functions
# -------------------------

def toFCvec(r3pnt):
    return FreeCAD.Vector(r3pnt.X, r3pnt.Y, r3pnt.Z)

def toFCangle(center, start):
    return math.atan2(start.Y - center.Y, start.X - center.X) * 180 / math.pi

def getFCKnots(fknots):
    k = list(fknots)
    knots = sorted(set(k))
    mults = [k.count(kn) for kn in knots]
    mults[0] += 1
    mults[-1] += 1
    return knots, mults

# -------------------------
# Main 3DM Import Class
# -------------------------

class File3dm:
    def __init__(self, path):
        self.f3dm = r3.File3dm.Read(path)

    def parse_objects(self, doc=None):
        if not doc:
            doc = FreeCAD.newDocument("3dm_import")
        part = doc.addObject("App::Part", "Part")
        for rhino_obj in self.f3dm.Objects:
            fc_obj = self.import_geometry(doc, rhino_obj.Geometry)
            if fc_obj:
                part.addObject(fc_obj)

    # ---------------------
    # Import Geometry Types
    # ---------------------
    def import_geometry(self, doc, geo):
        if isinstance(geo, r3.Brep):
            return self.import_brep(doc, geo)
        elif isinstance(geo, (r3.NurbsCurve, r3.Curve)):
            return self.import_curve(doc, geo)
        elif isinstance(geo, r3.LineCurve):
            return self.import_line(doc, geo)
        elif isinstance(geo, r3.PolylineCurve):
            return self.import_polyline(doc, geo)
        elif isinstance(geo, r3.Mesh):
            return self.create_mesh(doc, geo)
        elif isinstance(geo, r3.NurbsSurface):
            return self.create_surface(doc, geo)
        else:
            FreeCAD.Console.PrintMessage(f"Geometry type {type(geo)} not yet handled\n")
            return None

    # ---------------------
    # Brep Handling
    # ---------------------
    def import_brep(self, doc, geo):
        shapes = []
        # If single surface
        if geo.IsSurface:
            obj = doc.addObject("Part::Feature", "BrepSurface")
            obj.Shape = self.create_surface(geo.Surfaces[0]).toShape()
            return obj
        # Otherwise create compound from edges
        for e in geo.Edges:
            shapes.append(self.create_curve(e).toShape())
        if shapes:
            obj = doc.addObject("Part::Feature", "BrepEdges")
            obj.Shape = Part.Compound(shapes)
            return obj

    # ---------------------
    # Curves
    # ---------------------
    def import_curve(self, doc, geo):
        obj = doc.addObject("Part::FeaturePython", "NurbsCurve")
        obj.Shape = self.create_curve(geo).toShape()
        ViewProvider(obj)
        return obj

    def import_line(self, doc, geo):
        obj = doc.addObject("Part::Line", "LineCurve")
        obj.X1, obj.Y1, obj.Z1 = geo.PointAtStart.X, geo.PointAtStart.Y, geo.PointAtStart.Z
        obj.X2, obj.Y2, obj.Z2 = geo.PointAtEnd.X, geo.PointAtEnd.Y, geo.PointAtEnd.Z
        obj.recompute()
        return obj

    def import_polyline(self, doc, geo):
        obj = doc.addObject("Part::Polygon", "PolyLineCurve")
        points = [toFCvec(geo.Point(i)) for i in range(geo.PointCount)]
        obj.Nodes = points
        obj.recompute()
        return obj

    # ---------------------
    # NURBS / Surface
    # ---------------------
    def create_curve(self, edge):
        nc = edge.ToNurbsCurve()
        pts = [FreeCAD.Vector(p.X / p.W, p.Y / p.W, p.Z / p.W) for p in nc.Points]
        weights = [p.W for p in nc.Points]
        ku, mu = getFCKnots(nc.Knots)
        bs = Part.BSplineCurve()
        bs.buildFromPolesMultsKnots(pts, mu, ku, False, nc.Degree, weights)
        return bs

    def create_surface(self, surf):
        nu = surf.ToNurbsSurface() if hasattr(surf, 'ToNurbsSurface') else surf
        pts, weights = [], []
        for u in range(nu.Points.CountU):
            row, wrow = [], []
            for v in range(nu.Points.CountV):
                p = nu.Points[u, v]
                row.append(FreeCAD.Vector(p.X / p.W, p.Y / p.W, p.Z / p.W))
                wrow.append(p.W)
            pts.append(row)
            weights.append(wrow)
        ku, mu = getFCKnots(nu.KnotsU)
        kv, mv = getFCKnots(nu.KnotsV)
        bs = Part.BSplineSurface()
        bs.buildFromPolesMultsKnots(pts, mu, mv, ku, kv, False, False, nu.Degree(0), nu.Degree(1), weights)
        return bs

    # ---------------------
    # Mesh
    # ---------------------
    def create_mesh(self, doc, r3mesh):
        fcMesh = Mesh.Mesh()
        for i in range(r3mesh.Faces.TriangleCount):
            f = r3mesh.Faces[i]
            verts = [(r3mesh.Vertices[idx].X, r3mesh.Vertices[idx].Y, r3mesh.Vertices[idx].Z) for idx in f[:3]]
            fcMesh.addFacet(*[coord for vertex in verts for coord in vertex])
        obj = doc.addObject("Mesh::Feature", "Mesh")
        obj.Mesh = fcMesh
        return obj

# -------------------------
# Main Functions
# -------------------------

def open(filename):
    docname = os.path.splitext(os.path.basename(filename))[0]
    doc = FreeCAD.newDocument(docname)
    if filename.lower().endswith(".3dm"):
        process3DM(doc, filename)
    return doc

def insert(filename, docname):
    try:
        doc = FreeCAD.getDocument(docname)
    except NameError:
        doc = FreeCAD.newDocument(docname)
    if filename.lower().endswith(".3dm"):
        process3DM(doc, filename)

def process3DM(doc, filename):
    FreeCAD.Console.PrintMessage(f"Import 3DM file: {filename}\n")
    fi = File3dm(filename)
    fi.parse_objects(doc)
    FreeCADGui.SendMsgToActiveView("ViewFit")
    FreeCAD.Console.PrintMessage("3DM File Imported\n")

