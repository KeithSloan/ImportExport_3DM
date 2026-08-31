# -*- coding: utf-8 -*-
# SubD import for ImportExport_3DM  (dual representation).
#
# A Rhino SubD is imported as an ``App::Part`` container holding two children:
#
#   * ``<name>_NURBS`` — a ``Part::FeaturePython`` whose Shape is the exact
#     bicubic B-spline **limit patches** for every regular interior quad face
#     (Catmull-Clark limit == uniform bicubic B-spline there).  Poles are
#     B = M . P . M^T with M the uniform-cubic-B-spline central-span -> Bezier
#     matrix (verified vs rhino3dm SurfacePoint to ~1e-15).  Uses the native
#     Part view provider — real B-rep, downstream-operable.
#
#   * ``<name>_Cage`` — an ``App::FeaturePython`` carrying the control net as
#     point + face-index arrays, drawn by a lightweight pivy ``SoIndexedFaceSet``
#     view provider.  Quads are preserved exactly (``-1``-terminated polygons);
#     the scene graph is assembled with two bulk ``setValues`` crossings, so it
#     builds a 40k-quad cage in ~5 ms with no compiled dependency and no triangle
#     Mesh (FreeCAD's Mesh kernel is triangle-only and would split every quad).
#
# The cage is authoritative: the NURBS child links to it and rebuilds from it,
# so editing the control net re-drives the limit patches.

import FreeCAD
import Part

try:
    import numpy as _np
    _HAVE_NUMPY = True
except Exception:
    _HAVE_NUMPY = False

__all__ = ["makeSubD", "SubDCage", "SubDNurbs", "ViewProviderCage"]

if _HAVE_NUMPY:
    _M = _np.array([[1, 4, 1, 0],
                    [0, 4, 2, 0],
                    [0, 2, 4, 0],
                    [0, 1, 4, 1]], float) / 6.0


def _gui_up():
    return bool(getattr(FreeCAD, "GuiUp", False))


# --------------------------------------------------------------------------- #
#  Extraction from a rhino3dm SubD  (control net only — no mesh)
# --------------------------------------------------------------------------- #
def extract_subd(sd):
    """Return (points, faces, regular) from a rhino3dm SubD.

    points  : list of (x,y,z) control-net points, dense local index order
    faces   : list of tuples of local vertex indices (n-gons allowed)
    regular : list[bool] per vertex — valence-4, 4 edges, smooth
    NOTE: iterate the collections; indexing sd.Vertices[i] returns a dangling
    temporary whose .ControlNetPoint segfaults.
    """
    remap = {}
    points = []
    regular = []
    for v in sd.Vertices:
        remap[v.Index] = len(points)
        p = v.ControlNetPoint
        points.append((p.X, p.Y, p.Z))
        regular.append(v.FaceCount == 4 and v.EdgeCount == 4 and bool(v.IsSmooth))
    faces = []
    for fc in sd.Faces:
        faces.append(tuple(remap[fc.Vertex(k).Index] for k in range(fc.VertexCount)))
    return points, faces, regular


# --------------------------------------------------------------------------- #
#  Regular-quad exact limit patches  (PURE — no rhino3dm)
# --------------------------------------------------------------------------- #
def regular_bezier_patches(points, faces, regular):
    if not _HAVE_NUMPY:
        return []
    from collections import defaultdict
    edge2f = defaultdict(list)
    vert2f = defaultdict(list)
    for fid, fv in enumerate(faces):
        n = len(fv)
        for k in range(n):
            edge2f[frozenset((fv[k], fv[(k + 1) % n]))].append(fid)
        for a in fv:
            vert2f[a].append(fid)

    def neighbor(fid, a, b):
        fs = edge2f[frozenset((a, b))]
        return (fs[0] if fs[1] == fid else fs[1]) if len(fs) == 2 else None

    def other_two(fid, a, b):
        fv = faces[fid]
        if len(fv) != 4:
            return None
        rest = [v for v in fv if v not in (a, b)]
        if len(rest) != 2:
            return None
        pos = {v: k for k, v in enumerate(fv)}

        def adj(x, y):
            i = pos[x]
            return fv[(i + 1) % 4] == y or fv[(i - 1) % 4] == y
        pA = rest[0] if adj(a, rest[0]) else rest[1]
        pB = rest[1] if pA == rest[0] else rest[0]
        return pA, pB

    def diagonal(vk, exclude):
        for fid in vert2f[vk]:
            if fid in exclude:
                continue
            fv = faces[fid]
            if len(fv) == 4:
                return fv[(fv.index(vk) + 2) % 4]
        return None

    P = _np.array(points, float)
    patches = []
    for fid, fv in enumerate(faces):
        if len(fv) != 4:
            continue
        v0, v1, v2, v3 = fv
        if not all(regular[x] for x in fv):
            continue
        nb01, nb12 = neighbor(fid, v0, v1), neighbor(fid, v1, v2)
        nb23, nb30 = neighbor(fid, v2, v3), neighbor(fid, v3, v0)
        if None in (nb01, nb12, nb23, nb30):
            continue
        if any(len(faces[x]) != 4 for x in (nb01, nb12, nb23, nb30)):
            continue
        e01, e12 = other_two(nb01, v0, v1), other_two(nb12, v1, v2)
        e23, e30 = other_two(nb23, v2, v3), other_two(nb30, v3, v0)
        if None in (e01, e12, e23, e30):
            continue
        d0 = diagonal(v0, {fid, nb01, nb30})
        d1 = diagonal(v1, {fid, nb01, nb12})
        d2 = diagonal(v2, {fid, nb12, nb23})
        d3 = diagonal(v3, {fid, nb23, nb30})
        if None in (d0, d1, d2, d3):
            continue
        a01, b01 = e01
        a12, b12 = e12
        a23, b23 = e23
        a30, b30 = e30
        grid = [[d0,  a01, b01, d1],
                [b30, v0,  v1,  a12],
                [a30, v3,  v2,  b12],
                [d3,  b23, a23, d2]]
        cp = _np.array([[P[grid[r][c]] for c in range(4)] for r in range(4)])
        bz = _np.zeros((4, 4, 3))
        for k in range(3):
            bz[:, :, k] = _M @ cp[:, :, k] @ _M.T
        patches.append(bz)
    return patches


def build_nurbs_shape(points, faces, regular):
    patches = regular_bezier_patches(points, faces, regular)
    part_faces = []
    umults = vmults = [4, 4]
    uknots = vknots = [0.0, 1.0]
    for bz in patches:
        try:
            poles = [[FreeCAD.Vector(float(bz[i, j, 0]), float(bz[i, j, 1]),
                                     float(bz[i, j, 2])) for j in range(4)]
                     for i in range(4)]
            bs = Part.BSplineSurface()
            bs.buildFromPolesMultsKnots(poles, umults, vmults, uknots, vknots,
                                        False, False, 3, 3)
            f = bs.toShape()
            if f is not None and f.Area > 1e-12:
                part_faces.append(f)
        except Exception:
            continue
    if not part_faces:
        return None, 0
    try:
        shape = Part.makeShell(part_faces)
        if shape is None or not shape.Faces:
            raise Exception("empty shell")
    except Exception:
        shape = Part.Compound(part_faces)
    return shape, len(part_faces)


# --------------------------------------------------------------------------- #
#  Scripted objects
# --------------------------------------------------------------------------- #
class SubDCage:
    """App::FeaturePython carrying the authoritative control net."""

    def __init__(self, obj, points, faces, regular):
        obj.Proxy = self
        obj.addProperty("App::PropertyVectorList", "Points", "SubD",
                        "Control-net points").Points = \
            [FreeCAD.Vector(*p) for p in points]
        obj.addProperty("App::PropertyPythonObject", "Faces", "SubD",
                        "Control-net faces (vertex-index tuples)").Faces = list(faces)
        obj.addProperty("App::PropertyBoolList", "Regular", "SubD",
                        "Per-vertex regular flag").Regular = list(regular)
        obj.addProperty("App::PropertyInteger", "FaceCount", "SubD",
                        "Number of control-net faces").FaceCount = len(faces)

    def execute(self, obj):
        pass

    def __getstate__(self):
        return None

    def __setstate__(self, state):
        return None


class SubDNurbs:
    """Part::FeaturePython whose Shape is the SubD limit's regular patches,
    rebuilt from the linked cage (native Part view provider)."""

    def __init__(self, obj, cage):
        obj.Proxy = self
        obj.addProperty("App::PropertyLink", "Cage", "SubD",
                        "Control-net cage this NURBS shell is built from").Cage = cage
        obj.addProperty("App::PropertyInteger", "NurbsPatches", "SubD",
                        "Number of exact NURBS limit patches").NurbsPatches = 0

    def execute(self, obj):
        cage = getattr(obj, "Cage", None)
        if cage is None:
            obj.Shape = Part.Shape()
            return
        pts = [(v.x, v.y, v.z) for v in cage.Points]
        shape, n = build_nurbs_shape(pts, list(cage.Faces), list(cage.Regular))
        obj.NurbsPatches = n
        obj.Shape = shape if shape is not None else Part.Shape()

    def __getstate__(self):
        return None

    def __setstate__(self, state):
        return None


class ViewProviderCage:
    """pivy view provider: draws the control net as an SoIndexedFaceSet with two
    bulk setValues crossings (quads preserved, no triangle Mesh, no C++)."""

    def __init__(self, vobj):
        vobj.Proxy = self

    def attach(self, vobj):
        from pivy import coin
        self.obj = vobj.Object
        self.sep = coin.SoSeparator()
        self.mat = coin.SoMaterial()
        self.mat.diffuseColor = (0.55, 0.62, 0.75)
        self.mat.transparency = 0.35
        self.coords = coin.SoCoordinate3()
        self.faces = coin.SoIndexedFaceSet()
        self.sep.addChild(self.mat)
        self.sep.addChild(self.coords)
        self.sep.addChild(self.faces)
        vobj.addDisplayMode(self.sep, "Cage")
        self._rebuild()

    def _rebuild(self):
        obj = getattr(self, "obj", None)
        if obj is None:
            return
        pts = [(v.x, v.y, v.z) for v in obj.Points]
        self.coords.point.setValues(0, len(pts), pts)          # bulk crossing #1
        idx = []
        for fv in obj.Faces:
            idx.extend(list(fv))
            idx.append(-1)
        self.faces.coordIndex.setValues(0, len(idx), idx)      # bulk crossing #2

    def updateData(self, obj, prop):
        if prop in ("Points", "Faces"):
            try:
                self._rebuild()
            except Exception:
                pass

    def getDisplayModes(self, vobj):
        return ["Cage"]

    def getDefaultDisplayMode(self):
        return "Cage"

    def setDisplayMode(self, mode):
        return mode

    def __getstate__(self):
        return None

    def __setstate__(self, state):
        return None


# --------------------------------------------------------------------------- #
def makeSubD(doc, sd, label="SubD"):
    """Import a rhino3dm SubD as an App::Part holding a NURBS-limit child and a
    control-net cage child."""
    if not _HAVE_NUMPY:
        FreeCAD.Console.PrintWarning(
            "  SubD: numpy unavailable — no NURBS patches (cage only)\n")
    points, faces, regular = extract_subd(sd)

    container = doc.addObject("App::Part", label)

    cage = doc.addObject("App::FeaturePython", label + "_Cage")
    SubDCage(cage, points, faces, regular)
    if _gui_up():
        try:
            ViewProviderCage(cage.ViewObject)
        except Exception as e:
            FreeCAD.Console.PrintWarning("  SubD cage view provider: %s\n" % e)

    nurbs = doc.addObject("Part::FeaturePython", label + "_NURBS")
    SubDNurbs(nurbs, cage)

    container.addObject(cage)
    container.addObject(nurbs)
    doc.recompute()

    FreeCAD.Console.PrintMessage(
        "  SubD '%s': %d NURBS limit patches + %d-face control-net cage\n"
        % (label, getattr(nurbs, "NurbsPatches", 0), len(faces)))
    return container
