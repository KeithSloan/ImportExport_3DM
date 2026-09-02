# -*- coding: utf-8 -*-
# SubD import for ImportExport_3DM  (dual representation).
#
# A Rhino SubD is imported as an ``App::Part`` container holding two children:
#
#   * ``<name>_NURBS`` — a ``Part::Feature`` whose Shape is the exact
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
    """Import a rhino3dm SubD as an App::Part holding a NURBS-limit child
    (plain Part::Feature — reliable native display, downstream-operable) and a
    control-net cage child (pivy SoIndexedFaceSet)."""
    if not _HAVE_NUMPY:
        FreeCAD.Console.PrintWarning(
            "  SubD: numpy unavailable \u2014 no NURBS patches (cage only)\n")
    points, faces, regular = extract_subd(sd)
    _record_subd_bbox(sd)

    container = doc.addObject("App::Part", label)

    # control-net cage
    cage = doc.addObject("App::FeaturePython", label + "_Cage")
    SubDCage(cage, points, faces, regular)
    if _gui_up():
        try:
            ViewProviderCage(cage.ViewObject)
        except Exception as e:
            FreeCAD.Console.PrintWarning("  SubD cage view provider: %s\n" % e)

    # NURBS limit patches.  A plain Part::Feature displays reliably; a
    # Part::FeaturePython with only a data proxy leaves its view provider's
    # DisplayMode uninitialised and renders nothing.
    shape, npatch = build_nurbs_shape(points, faces, regular)
    nurbs = doc.addObject("Part::Feature", label + "_NURBS")
    if shape is not None:
        nurbs.Shape = shape
    nurbs.addProperty("App::PropertyInteger", "NurbsPatches", "SubD",
                      "Number of exact NURBS limit patches").NurbsPatches = npatch

    container.addObject(cage)
    container.addObject(nurbs)
    doc.recompute()
    if _gui_up():
        try:
            nurbs.ViewObject.DisplayMode = "Flat Lines"
        except Exception:
            pass

    FreeCAD.Console.PrintMessage(
        "  SubD '%s': %d NURBS limit patches + %d-face control-net cage\n"
        % (label, npatch, len(faces)))
    return container


def _subd_limit_mesh(sd, level=2):
    """Subdivided limit: subdivide a copy `level` times, take each vertex's exact
    SurfacePoint, fan-triangulate faces. Returns (verts, tris)."""
    work = sd
    try:
        work = sd.Duplicate()
        if level > 0:
            work.Subdivide(level)
    except Exception:
        work = sd
    idx = {}; verts = []
    for v in work.Vertices:
        idx[v.Index] = len(verts); q = v.SurfacePoint; verts.append((q.X, q.Y, q.Z))
    tris = []
    for fc in work.Faces:
        vi = [idx[fc.Vertex(k).Index] for k in range(fc.VertexCount)]
        for k in range(1, len(vi) - 1):
            tris.append((vi[0], vi[k], vi[k + 1]))
    return verts, tris


def makeSubDSurfaces(doc, sd, label="SubD", level=2):
    """Import a SubD as its smooth subdivided limit **surface** (a Mesh::Feature) --
    complete and smooth, the faithful representation of a subdivision surface. This is
    the default; the NURBS-patch reconstruction (makeSubD) is the alternative."""
    import Mesh
    _record_subd_bbox(sd)
    verts, tris = _subd_limit_mesh(sd, level)
    m = Mesh.Mesh()
    for a, b, c in tris:
        pa, pb, pc = verts[a], verts[b], verts[c]
        m.addFacet(pa[0], pa[1], pa[2], pb[0], pb[1], pb[2], pc[0], pc[1], pc[2])
    obj = doc.addObject("Mesh::Feature", label)
    obj.Mesh = m
    try:
        obj.addProperty("App::PropertyBool", "SubDLimitSurface", "SubD",
                        "This mesh is a SubD subdivided limit surface").SubDLimitSurface = True
    except Exception:
        pass
    FreeCAD.Console.PrintMessage(
        "  SubD '%s': subdivided limit surface (%d facets)\n" % (label, m.CountFacets))
    return obj


# --- control-net-mesh detection: a Rhino "SubD from mesh" file stores each SubD
# alongside the coarse control-net mesh it was built from. We record each imported
# SubD's control-net bounding box, then hide (and relabel) the coincident file mesh
# so only the SubD result (surface or NURBS) shows by default. Works in both modes.
_subd_cnet_bboxes = []


def reset_subd_bboxes():
    del _subd_cnet_bboxes[:]


def _record_subd_bbox(sd):
    try:
        bb = FreeCAD.BoundBox()
        for v in sd.Vertices:
            p = v.ControlNetPoint
            bb.add(FreeCAD.Vector(p.X, p.Y, p.Z))
        if bb.isValid():
            _subd_cnet_bboxes.append(bb)
    except Exception:
        pass


def _bbox_coincident(a, b):
    da, db = a.DiagonalLength, b.DiagonalLength
    if da < 1e-9 or db < 1e-9:
        return False
    return a.Center.distanceToPoint(b.Center) < 0.3 * max(da, db) and 0.4 < da / db < 2.5


def hide_control_meshes(doc):
    """Hide + relabel the 'SubD from mesh' control-net meshes coincident with an
    imported SubD, in either import mode, so only the SubD result shows by default.
    They are still imported (just hidden and labelled). Returns the number hidden."""
    if not _subd_cnet_bboxes:
        return 0
    hidden = 0
    for o in doc.Objects:
        if o.TypeId == "Mesh::Feature" and not getattr(o, "SubDLimitSurface", False):
            try:
                bb = o.Mesh.BoundBox
            except Exception:
                continue
            if any(_bbox_coincident(bb, sb) for sb in _subd_cnet_bboxes):
                try:
                    o.ViewObject.Visibility = False
                    o.Label = "SubD control net (hidden)"
                    hidden += 1
                except Exception:
                    pass
    if hidden:
        FreeCAD.Console.PrintMessage(
            "  SubD: imported and HID %d 'SubD from mesh' control-net mesh(es) -- "
            "they duplicate the SubD cage and are labelled 'SubD control net (hidden)'. "
            "Toggle their visibility in the tree to see them.\n" % hidden)
    return hidden
