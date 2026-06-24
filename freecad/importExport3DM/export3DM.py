# Mon Sep 19 10:36:46 AM PDT 2022
# **************************************************************************
# *                                                                        *
# *   Copyright (c) 2022 Keith Sloan <keith@sloan-home.co.uk>              *
# *                                                                        *
# *   This program is free software; you can redistribute it and/or modify *
# *   it under the terms of the GNU Lesser General Public License (LGPL)   *
# *   as published by the Free Software Foundation; either version 2 of    *
# *   the License, or (at your option) any later version.                  *
# *   for detail see the LICENCE text file.                                *
# *                                                                        *
# *   This program is distributed in the hope that it will be useful,      *
# *   but WITHOUT ANY WARRANTY; without even the implied warranty of       *
# *   MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the        *
# *   GNU Library General Public License for more details.                 *
# *                                                                        *
# *   You should have received a copy of the GNU Library General Public    *
# *   License along with this program; if not, write to the Free Software  *
# *   Foundation, Inc., 59 Temple Place, Suite 330, Boston, MA  02111-1307 *
# *   USA                                                                  *
# *                                                                        *
# **************************************************************************
__title__   = "FreeCAD - ImportExport 3DM Module"
__author__  = "Keith Sloan <keith@sloan-home.co.uk>"
__url__     = ["https://github.com/KeithSloan/ImportExport_3DM"]
__version__ = "0.3.0"

import FreeCAD, os, sys, Part, traceback
from FreeCAD import Units
import rhino3dm as r3

FreeCAD.Console.PrintMessage(
    f"ImportExport 3DM Module export3DM {__version__} "
    f"(rhino3dm {r3.__version__})\n"
)

# ---------------------------------------------------------------------------
# Export preferences
# Stored under User parameter:BaseApp/Preferences/Mod/ImportExport_3DM
# Change at runtime via the FreeCAD Python console, e.g.:
#   FreeCAD.ParamGet("User parameter:BaseApp/Preferences/Mod/ImportExport_3DM") \
#       .SetBool("ExportNativePrimitives", False)
# ---------------------------------------------------------------------------
def _prefs():
    return FreeCAD.ParamGet(
        "User parameter:BaseApp/Preferences/Mod/ImportExport_3DM")

def getExportNativePrimitives():
    """When True, Cylinder/Cone/Sphere/Torus faces are written using native
    rhino3dm primitives (exact analytic shape, smaller file).
    When False (default), FreeCAD's face.toNurbs() → segment() path is used,
    which produces a bounded BSplineSurface that trims reliably on re-import.

    Known issue with native primitives:
      Sphere (and potentially Cone/Cylinder) fillet faces often have a
      degenerate pole or seam edge whose length is zero.  _edgeToNurbsCurve3D
      returns None for it, so one boundary curve is skipped during export.
      On re-import the missing curve gap is closed with a straight-line
      segment; projecting that onto the unbounded full-sphere (or full-cylinder)
      NurbsSurface produces the wrong trim region — the face appears untrimmed
      or shows the complement of the intended patch.
      The generic toNurbs()/segment() path avoids this because the exported
      surface is already bounded to the actual face extent."""
    return _prefs().GetBool("ExportNativePrimitives", False)


def getExportTrimmedBreps():
    """When True (default), faces are written as TRIMMED Breps via the optional
    `trim3dm` extension — IF it is importable (built for this Python). If trim3dm
    is not available, a warning is printed and export falls back to untrimmed
    NurbsSurfaces + boundary curves (the standard behaviour). Set False to always
    use the untrimmed path. (trim3dm branch only.)"""
    return _prefs().GetBool("ExportTrimmedBreps", True)


# ---------------------------------------------------------------------------
# trim3dm integration (optional; trim3dm branch).
# Builds per-face "trim dicts" (surface + ordered loops of 3D edges + 2D
# pcurves) that trim3dm.add_trimmed_breps() turns into trimmed Breps. The 2D
# pcurves are sampled degree-1 polylines (v1; TODO: exact OCCT CurveOnSurface).
# ---------------------------------------------------------------------------
# Separator used to encode "{group}::{face}" in a trimmed Brep's name so the
# import side can rebuild the FreeCAD group tree. Must match import_trim_3DM.
_TRIM_GROUP_SEP = "::"


def _import_trim3dm():
    """Return the trim3dm extension only if importable AND actually built (has
    its functions). Guards against importing the `trim3dm/` *source* folder as an
    empty namespace package (which has no functions)."""
    import glob

    def _good(m):
        return (m is not None and hasattr(m, "add_trimmed_breps")
                and hasattr(m, "read_trimmed_breps"))

    try:
        import trim3dm
        if _good(trim3dm):
            return trim3dm
        sys.modules.pop("trim3dm", None)        # drop the namespace-package stub
    except ImportError:
        pass

    here = os.path.dirname(os.path.abspath(__file__))
    for cand in (os.path.join(here, "..", "..", "trim3dm"), here):
        cand = os.path.abspath(cand)
        # only add a directory that actually holds a built trim3dm binary
        if (glob.glob(os.path.join(cand, "trim3dm*.so"))
                or glob.glob(os.path.join(cand, "trim3dm*.pyd"))):
            if cand not in sys.path:
                sys.path.insert(0, cand)
    try:
        sys.modules.pop("trim3dm", None)
        import trim3dm
        if _good(trim3dm):
            return trim3dm
    except ImportError:
        pass
    return None


def _trimExpandKnots(knots, mults):
    seq = []
    for k, m in zip(knots, mults):
        seq.extend([k] * int(m))
    return seq[1:-1]            # OpenNURBS form (drop first & last)


def _trimXYZ(p):
    return (p.x, p.y, p.z) if hasattr(p, "x") else (p[0], p[1], p[2])


def _trimSurfaceDict(bs):
    nu, nv = bs.NbUPoles, bs.NbVPoles
    poles = bs.getPoles()
    try:
        wts = bs.getWeights()
    except Exception:
        wts = [[1.0] * nv for _ in range(nu)]
    cv = []
    for i in range(nu):
        row = []
        for j in range(nv):
            x, y, z = _trimXYZ(poles[i][j])
            w = wts[i][j]
            row.append([x * w, y * w, z * w, w])      # homogeneous
        cv.append(row)
    return {"degree_u": bs.UDegree, "degree_v": bs.VDegree, "cv": cv,
            "knots_u": _trimExpandKnots(bs.getUKnots(), bs.getUMultiplicities()),
            "knots_v": _trimExpandKnots(bs.getVKnots(), bs.getVMultiplicities())}


def _trimEdgeCurves(edge, bs, nsamp=24):
    """Sample edge in LOOP direction -> matching 3D and 2D (pcurve) degree-1
    polylines (so they correspond and neighbours share endpoints)."""
    t0, t1 = edge.FirstParameter, edge.LastParameter
    ts = [t0 + (t1 - t0) * i / nsamp for i in range(nsamp + 1)]
    if edge.Orientation == "Reversed":
        ts.reverse()
    cv3, cv2 = [], []
    for t in ts:
        p = edge.valueAt(t)
        cv3.append([p.x, p.y, p.z, 1.0])
        u, v = bs.parameter(p)
        cv2.append([u, v, 1.0])
    n = len(ts)
    knots = [float(k) for k in range(n)]
    return ({"degree": 1, "cv": cv3, "knots": knots},
            {"degree": 1, "cv": cv2, "knots": knots})


def _trimLoopUVArea(loop):
    pts = [(uvw[0], uvw[1]) for e in loop for uvw in e["c2"]["cv"]]
    a = 0.0
    n = len(pts)
    for i in range(n):
        x0, y0 = pts[i]
        x1, y1 = pts[(i + 1) % n]
        a += x0 * y1 - x1 * y0
    return a / 2.0


def _trimFaceDict(face, name):
    """Build a trim3dm face dict (surface + CCW-corrected, snapped loops)."""
    surf = face.Surface
    if not isinstance(surf, Part.BSplineSurface):
        nf = face.toNurbs().Faces[0]
        face, surf = nf, nf.Surface
    loops = []
    for wi, wire in enumerate(face.Wires):
        edges = wire.OrderedEdges if hasattr(wire, "OrderedEdges") else wire.Edges
        loop = []
        for e in edges:
            if not e.Vertexes:
                continue
            c3, c2 = _trimEdgeCurves(e, surf)
            loop.append({"c3": c3, "c2": c2, "rev3d": False})
        if not loop:
            continue
        # outer loop CCW in UV, inner loops CW
        area = _trimLoopUVArea(loop)
        if ((wi == 0) and area < 0) or ((wi != 0) and area > 0):
            loop.reverse()
            for e in loop:
                e["c3"]["cv"].reverse()
                e["c2"]["cv"].reverse()
        # snap the trim chain closed
        m = len(loop)
        for i in range(m):
            cur_end = loop[i]["c2"]["cv"][-1]
            nxt0 = loop[(i + 1) % m]["c2"]["cv"][0]
            nxt0[0], nxt0[1] = cur_end[0], cur_end[1]
        loops.append(loop)
    return {"name": name, "surface": _trimSurfaceDict(surf), "loops": loops}


#################################
# Switch functions
################################


class switch(object):
    value = None

    def __new__(class_, value):
        class_.value = value
        return True

def case(*args):
    return any((arg == switch.value for arg in args))



class rhinoModel():
    #import rhino3dm as r3
    #import rhino3dm
    def __init__(self):
        import rhino3dm
        self.model = r3.File3dm()
        self.model.ApplicationName = "ImportExport_3DM"
        self.model.ApplicationUrl = "https://github.com/KeithSloan/ImportExport_3DM"
        # Variables
        self.ControlPoints = []
        self._group_idx = -1       # set per-object in addObjToModel; -1 means no group
        self._current_label = ""   # obj.Label of the object currently being exported
        self._trim_export = False  # when True, processFaces collects trim dicts
        self._trim_faces = []      # trim3dm face dicts (added after write)
        self.layer = r3.Layer()
        self.layer.Name = "FC Layer"
        self.model.Layers.Add(self.layer)
        # create box brep
        pln = r3.Plane.WorldXY
        #box = r3.Box( pln, rhino3dm.Interval(0,1000), \
        #                rhino3dm.Interval(0,800), \
        #                rhino3dm.Interval(0,500) )
        boundBox = r3.BoundingBox(0,0,0, 1000, 800, 500)
        box = r3.Box(boundBox)
        brp = boundBox.ToBrep()

        # add brep to model
        #self.model.Objects.AddBrep(brp)

    def _makeAttrs(self):
        """Return an ObjectAttributes with the current object's name and group."""
        attrs = r3.ObjectAttributes()
        if self._current_label:
            attrs.Name = self._current_label
        if self._group_idx >= 0:
            attrs.AddToGroup(self._group_idx)
        return attrs

    def processNurbEdges(self, nurbs):
        self.curves = []
        for e in nurbs.Edges:
            if len(e.Vertexes) > 1:         # Avoid error degenerate edge
                nc = self._edgeToNurbsCurve3D(e)   # weight-preserving, exact arcs
                if nc is not None:
                    self.model.Objects.AddCurve(nc, self._makeAttrs())
                    self.curves.append(nc)


    def processNurbSurfaces(self, nurbs):
        pass  # not yet implemented

    def processNurbs(self, nurbs):
        if hasattr(nurbs, "Edges"):
            if len(nurbs.Edges) > 0:
                self.processNurbEdges(nurbs)
        if hasattr(nurbs, "Faces"):
            if len(nurbs.Faces) > 0:
                self.processNurbSurfaces(nurbs)


    def curvesToNurbs(self, obj):
        if hasattr(obj, "Shape"):
            if hasattr(obj.Shape, "toNurbs"):
                nurbs = obj.Shape.toNurbs()
                self.processNurbs(nurbs)

    def checkShapeForCurves(self, obj):
        # Not yet implemented — always returns False
        return False

    def checkShapeForSurface(self, obj):
        # Just check and return True or False
        return hasattr(obj, "Surface")

    # ------------------------------------------------------------------
    # Weight-preserving NURBS builders
    #
    # rhino3dm control points are HOMOGENEOUS: a Point4d(x, y, z, w) has the
    # Euclidean location (x/w, y/w, z/w).  To place a control point at the
    # Euclidean pole P with weight w you must write Point4d(P.x*w, P.y*w, P.z*w, w)
    # AND create the surface/curve as rational, otherwise the weights are
    # ignored.  The previous code created everything non-rational with all
    # weights forced to 1.0, which turned the rational profiles of cylinders,
    # cones, spheres and circles (degree-2 with weight ~0.707 corner points)
    # into rounded-square / straight-sided approximations.
    # ------------------------------------------------------------------
    @staticmethod
    def _expandKnots(knots, mults):
        """Expand FreeCAD (knots, multiplicities) into a flat sequence and drop
        the first and last entry for rhino3dm's convention
        (rhino knot count = nPoles + degree - 1)."""
        seq = []
        for k, m in zip(knots, mults):
            seq.extend([k] * int(m))
        return seq[1:-1]

    @staticmethod
    def _xyz(p):
        if hasattr(p, 'x'):
            return p.x, p.y, p.z
        return p[0], p[1], p[2]

    def _makeR3Surface(self, surface):
        """Build an r3.NurbsSurface from a Part.BSplineSurface, preserving
        rational weights.  Returns the surface or None on failure."""
        # rhino3dm NURBS use a clamped (non-periodic) knot vector.  A periodic /
        # closed FreeCAD surface — e.g. a full 360° cylinder, sphere or torus —
        # stores its poles and knots in periodic form, so the clamped knot
        # expansion below (drop first & last) would not match the pole count and
        # the surface would collapse to a distorted, straight-sided patch.
        # Convert any periodic direction to clamped form first (on a copy, so the
        # caller's geometry is left untouched).
        try:
            if surface.isUPeriodic() or surface.isVPeriodic():
                surface = surface.copy()
                if surface.isUPeriodic():
                    surface.setUNotPeriodic()
                if surface.isVPeriodic():
                    surface.setVNotPeriodic()
        except Exception as e:
            FreeCAD.Console.PrintMessage(f"  setNotPeriodic (surface) failed: {e}\n")
        UDegree, VDegree = surface.UDegree, surface.VDegree
        UPoles, VPoles   = surface.NbUPoles, surface.NbVPoles
        poles = surface.getPoles()
        try:
            weights = surface.getWeights()       # [u][v]
        except Exception:
            weights = None

        rational = False
        if weights is not None:
            for row in weights:
                if any(abs(w - 1.0) > 1e-9 for w in row):
                    rational = True
                    break

        ns = r3.NurbsSurface.Create(3, rational, UDegree + 1, VDegree + 1,
                                    UPoles, VPoles)
        if ns is None:
            FreeCAD.Console.PrintMessage(
                f"  NurbsSurface.Create failed (U{UDegree}/{UPoles} "
                f"V{VDegree}/{VPoles})\n")
            return None

        pts = ns.Points
        for u in range(UPoles):
            for v in range(VPoles):
                x, y, z = self._xyz(poles[u][v])
                w = weights[u][v] if (rational and weights is not None) else 1.0
                pts[u, v] = r3.Point4d(x * w, y * w, z * w, w)

        for i, k in enumerate(self._expandKnots(surface.getUKnots(),
                                                surface.getUMultiplicities())):
            ns.KnotsU[i] = k
        for i, k in enumerate(self._expandKnots(surface.getVKnots(),
                                                surface.getVMultiplicities())):
            ns.KnotsV[i] = k
        return ns

    def _makeR3Curve(self, bs):
        """Build an r3.NurbsCurve from a Part.BSplineCurve, preserving rational
        weights.  Returns the curve or None on failure."""
        # Clamp periodic (closed) curves — e.g. a full circle — for rhino3dm's
        # non-periodic knot convention (see _makeR3Surface).
        try:
            if bs.isPeriodic():
                bs = bs.copy()
                bs.setNotPeriodic()
        except Exception as e:
            FreeCAD.Console.PrintMessage(f"  setNotPeriodic (curve) failed: {e}\n")
        poles = bs.getPoles()
        n = len(poles)
        if n < 2:
            return None
        degree = bs.Degree
        try:
            weights = bs.getWeights()
        except Exception:
            weights = None
        rational = bool(weights) and any(abs(w - 1.0) > 1e-9 for w in weights)

        crv = r3.NurbsCurve(3, rational, degree + 1, n)
        for i, p in enumerate(poles):
            x, y, z = self._xyz(p)
            w = weights[i] if (rational and weights is not None) else 1.0
            crv.Points[i] = r3.Point4d(x * w, y * w, z * w, w)

        for i, k in enumerate(self._expandKnots(bs.getKnots(),
                                                bs.getMultiplicities())):
            crv.Knots[i] = k
        return crv

    def processSurfaceUV(self, surface):
        """Export a Part.BSplineSurface as an r3.NurbsSurface (weights kept).
        The former special-case ruled-surface branch was removed: it rebuilt
        cylinder rails non-rationally (dropping the circular weights) which is
        exactly what made cylinders come back with straight edges."""
        ns = self._makeR3Surface(surface)
        if ns is not None:
            self.model.Objects.AddSurface(ns, self._makeAttrs())
        else:
            FreeCAD.Console.PrintMessage("  processSurfaceUV: surface build failed\n")

    def checkForSurfaceUV(self, face):
        if hasattr(face, "Surface"):
            if hasattr(face.Surface, "UDegree") and \
               hasattr(face.Surface, "VDegree"):
               return True

    
    def processBSplineSurface(self, obj):
        if self.checkForSurfaceUV(obj):
            surface = obj.Surface
            # Segment the surface to the face's actual parameter range so the
            # exported surface matches the visible face extent rather than the
            # full underlying parametric domain (important for trimmed STEP faces).
            try:
                u1, u2, v1, v2 = obj.ParameterRange
                surface.segment(u1, u2, v1, v2)
            except Exception as e:
                FreeCAD.Console.PrintMessage(f"  segment() failed — using full surface: {e}\n")
            self.processSurfaceUV(surface)

    def processSurfacePlane(self, obj):
        """Export a bounded planar face.
        Strategy 1: face.toNurbs() — lets OCC convert the trimmed face to a
        proper BSplineSurface (same path used by processSurfaceGeneric).
        Strategy 2 fallback: bilinear corner patch from the four ParameterRange
        corners (less accurate for non-rectangular faces)."""
        # Strategy 1: OCC conversion via face.toNurbs()
        try:
            nurbs_shape = obj.toNurbs()
            for nf in nurbs_shape.Faces:
                if hasattr(nf, 'Surface') and isinstance(nf.Surface, Part.BSplineSurface):
                    self.processBSplineSurface(nf)
                    return
        except Exception as e:
            FreeCAD.Console.PrintMessage(f"  Plane toNurbs() failed: {e}\n")

        # Strategy 2: bilinear corner patch
        try:
            u1, u2, v1, v2 = obj.ParameterRange
            p00 = obj.valueAt(u1, v1)
            p10 = obj.valueAt(u2, v1)
            p01 = obj.valueAt(u1, v2)
            p11 = obj.valueAt(u2, v2)
            ns = r3.NurbsSurface.Create(3, False, 2, 2, 2, 2)
            if ns is None:
                FreeCAD.Console.PrintMessage("  Plane: NurbsSurface.Create failed\n")
                return
            pts = ns.Points
            pts[0, 0] = r3.Point4d(p00.x, p00.y, p00.z, 1.0)
            pts[1, 0] = r3.Point4d(p10.x, p10.y, p10.z, 1.0)
            pts[0, 1] = r3.Point4d(p01.x, p01.y, p01.z, 1.0)
            pts[1, 1] = r3.Point4d(p11.x, p11.y, p11.z, 1.0)
            ns.KnotsU[0] = 0.0;  ns.KnotsU[1] = 1.0
            ns.KnotsV[0] = 0.0;  ns.KnotsV[1] = 1.0
            if not ns.IsValid:
                FreeCAD.Console.PrintMessage("  Plane bilinear patch invalid — skipping\n")
                return
            self.model.Objects.AddSurface(ns, self._makeAttrs())
        except Exception as e:
            FreeCAD.Console.PrintMessage(f"  Plane export failed: {e}\n")
            traceback.print_exc()

    def _toBSplineAndProcess(self, obj, label):
        """Convert a surface to BSpline then pass to processSurfaceUV.
        Analytic surfaces (Sphere, Cylinder, Cone, Toroid) use no-arg toBSpline().
        Parametric surfaces (SurfaceOfExtrusion etc.) need the UV parameter range.
        Returns True on success, False on failure."""
        try:
            bspl = None
            # Try no-arg form first (analytic surfaces e.g. Sphere, Cylinder).
            # Catch any exception — Plane raises Part.OCCError (infinite surface),
            # others may raise TypeError if the signature differs.
            try:
                bspl = obj.Surface.toBSpline()
            except Exception:
                pass
            # Fall back to UV-range form (parametric surfaces)
            if bspl is None:
                u1, u2, v1, v2 = obj.ParameterRange
                bspl = obj.Surface.toBSpline(u1, u2, v1, v2)
            self.processSurfaceUV(bspl)
            return True
        except Exception as e:
            FreeCAD.Console.PrintMessage(f"  {label} toBSpline failed: {e}\n")
            return False

    # ------------------------------------------------------------------
    # Helpers shared by the native primitive exporters
    # ------------------------------------------------------------------

    def _addNurbsSurface(self, ns, label):
        """Add a NurbsSurface to the model; return True on success."""
        if ns is not None:
            self.model.Objects.AddSurface(ns, self._makeAttrs())
            return True
        FreeCAD.Console.PrintMessage(f"  {label}: ToNurbsSurface() returned None\n")
        return False

    def _axisPlane(self, obj):
        """Return (r3.Plane, v1, v2, radius) for a cylindrical/conical face.
        The plane origin is the bottom-centre of the axis; the plane normal
        is the surface axis direction."""
        u1, u2, v1, v2 = obj.ParameterRange
        u_mid = (u1 + u2) / 2
        p_surf = obj.valueAt(u_mid, v1)          # point on surface at base
        nrm    = obj.normalAt(u_mid, v1)          # radial outward normal
        radius = obj.Surface.Radius
        bottom = p_surf - nrm * radius            # project inward to axis
        axis   = obj.Surface.Axis
        rh_origin = r3.Point3d(bottom.x, bottom.y, bottom.z)
        rh_normal = r3.Vector3d(axis.x, axis.y, axis.z)
        return r3.Plane(rh_origin, rh_normal), v1, v2, radius

    # ------------------------------------------------------------------
    # Cylinder
    # ------------------------------------------------------------------

    def processSurfaceCylinder(self, obj):
        if getExportNativePrimitives() and self._exportNativeCylinder(obj):
            return
        self.processSurfaceGeneric(obj)

    def _exportNativeCylinder(self, obj):
        try:
            plane, v1, v2, radius = self._axisPlane(obj)
            circle = r3.Circle(radius)
            circle.Plane = plane
            rh_cyl = r3.Cylinder(circle, v2 - v1)
            if not rh_cyl.IsValid:
                return False
            ns = rh_cyl.ToNurbsSurface()
            return self._addNurbsSurface(ns, "Cylinder")
        except Exception as e:
            FreeCAD.Console.PrintMessage(f"  Native cylinder failed: {e}\n")
            return False

    # ------------------------------------------------------------------
    # Cone
    # ------------------------------------------------------------------

    def processSurfaceCone(self, obj):
        if getExportNativePrimitives() and self._exportNativeCone(obj):
            return
        self.processSurfaceGeneric(obj)

    def _exportNativeCone(self, obj):
        try:
            import math
            u1, u2, v1, v2 = obj.ParameterRange
            u_mid = (u1 + u2) / 2
            p_surf = obj.valueAt(u_mid, v1)
            nrm    = obj.normalAt(u_mid, v1)
            radius = obj.Surface.Radius            # base radius at v1
            bottom = p_surf - nrm * radius
            axis   = obj.Surface.Axis
            height = v2 - v1
            half_angle = obj.Surface.SemiAngle     # radians
            # rhino3dm Cone(plane, height, radius) — radius at the BASE circle.
            # FreeCAD's Cone surface is infinite; the face is trimmed to [v1,v2].
            # The base radius at v1 equals Surface.Radius + v1 * tan(SemiAngle)
            # but Surface.Radius is already evaluated at the apex offset, so use
            # the sampled radius directly.
            base_radius = radius
            rh_origin = r3.Point3d(bottom.x, bottom.y, bottom.z)
            rh_normal = r3.Vector3d(axis.x, axis.y, axis.z)
            rh_plane  = r3.Plane(rh_origin, rh_normal)
            rh_cone   = r3.Cone(rh_plane, height, base_radius)
            if not rh_cone.IsValid:
                return False
            ns = rh_cone.ToNurbsSurface()
            return self._addNurbsSurface(ns, "Cone")
        except Exception as e:
            FreeCAD.Console.PrintMessage(f"  Native cone failed: {e}\n")
            return False

    # ------------------------------------------------------------------
    # Sphere
    # ------------------------------------------------------------------

    def processSurfaceSphere(self, obj):
        # Native sphere export is intentionally bypassed regardless of the
        # ExportNativePrimitives preference.
        #
        # Why: _exportNativeSphere calls rh_sphere.ToNurbsSurface() which
        # produces an unbounded full-sphere NURBS.  Sphere fillet faces always
        # have a degenerate pole/seam edge (zero length); _edgeToNurbsCurve3D
        # returns None for it, so one boundary curve is silently skipped.
        # On re-import, ShapeFix_Wire reorders the remaining edges
        # non-deterministically, the gap-closing straight-line segment lands in
        # different positions across runs, and the resulting MakeFace trim is
        # sometimes the correct small patch and sometimes its complement — i.e.
        # the result is unreliable by design.
        #
        # The generic path (face.toNurbs() → segment()) exports a bounded
        # BSplineSurface whose extent already matches the face, so the trim
        # reconstruction works correctly and consistently.
        #
        # _exportNativeSphere is retained below for reference / future use.
        self.processSurfaceGeneric(obj)

    def _exportNativeSphere(self, obj):
        try:
            u1, u2, v1, v2 = obj.ParameterRange
            u_mid, v_mid = (u1 + u2) / 2, (v1 + v2) / 2
            p_surf = obj.valueAt(u_mid, v_mid)
            nrm    = obj.normalAt(u_mid, v_mid)
            radius = obj.Surface.Radius
            centre = p_surf - nrm * radius
            rh_centre = r3.Point3d(centre.x, centre.y, centre.z)
            rh_sphere = r3.Sphere(rh_centre, radius)
            if not rh_sphere.IsValid:
                return False
            ns = rh_sphere.ToNurbsSurface()
            return self._addNurbsSurface(ns, "Sphere")
        except Exception as e:
            FreeCAD.Console.PrintMessage(f"  Native sphere failed: {e}\n")
            return False

    # ------------------------------------------------------------------
    # Toroid
    # ------------------------------------------------------------------

    def processSurfaceToroid(self, obj):
        if getExportNativePrimitives() and self._exportNativeToroid(obj):
            return
        self.processSurfaceGeneric(obj)

    def _exportNativeToroid(self, obj):
        try:
            axis   = obj.Surface.Axis
            # Sample centre of torus: point on surface minus outward normal * minor radius
            u1, u2, v1, v2 = obj.ParameterRange
            u_mid, v_mid = (u1 + u2) / 2, (v1 + v2) / 2
            p_surf  = obj.valueAt(u_mid, v_mid)
            nrm     = obj.normalAt(u_mid, v_mid)
            r_minor = obj.Surface.MinorRadius
            r_major = obj.Surface.MajorRadius
            # Centre of the torus tube at this sample point
            tube_centre = p_surf - nrm * r_minor
            # Torus centre = tube_centre projected onto torus equatorial plane
            # (approximated as the point r_major from the axis)
            rh_origin = r3.Point3d(tube_centre.x, tube_centre.y, tube_centre.z)
            rh_normal = r3.Vector3d(axis.x, axis.y, axis.z)
            rh_plane  = r3.Plane(rh_origin, rh_normal)
            rh_torus  = r3.Torus(rh_plane, r_major, r_minor)
            if not rh_torus.IsValid:
                return False
            ns = rh_torus.ToNurbsSurface()
            return self._addNurbsSurface(ns, "Torus")
        except Exception as e:
            FreeCAD.Console.PrintMessage(f"  Native torus failed: {e}\n")
            return False

    def processSurfaceGeneric(self, obj):
        """Fallback for any surface type not explicitly handled.
        First tries face.toNurbs() which lets FreeCAD/OCC do the conversion,
        then falls back to surface.toBSpline() variants."""
        label = type(obj.Surface).__name__
        # Strategy 1: convert the face itself to NURBS via FreeCAD
        try:
            nurbs_shape = obj.toNurbs()
            for nf in nurbs_shape.Faces:
                if hasattr(nf, 'Surface') and isinstance(nf.Surface, Part.BSplineSurface):
                    self.processBSplineSurface(nf)
                    return
        except Exception as e:
            FreeCAD.Console.PrintMessage(f"  {label} toNurbs() failed: {e}\n")
        # Strategy 2: surface.toBSpline() variants
        if not self._toBSplineAndProcess(obj, label):
            FreeCAD.Console.PrintMessage(f"  Skipping face: no conversion for {label}\n")
    # ------------------------------------------------------------------
    # Brep export — trimmed faces
    # ------------------------------------------------------------------

    def _bsplineSurfaceToR3(self, surface):
        """Convert a Part.BSplineSurface to a (weight-preserving) r3.NurbsSurface."""
        return self._makeR3Surface(surface)

    def _arcEdgeToR3(self, edge, crv):
        """Build an EXACT rational degree-2 r3.NurbsCurve for a circular edge.

        FreeCAD's Circle/Arc.toBSpline() returns a high-degree (≈8) *non-rational*
        polynomial approximation.  That curve does not lie exactly on the rational
        cylinder surface, so on re-import the trim wire can't close cleanly and the
        importer bridges the gap with a straight segment — the "straight edge".

        The exact representation is the textbook NURBS arc: split into ≤90°
        segments, each a degree-2 rational Bézier with the middle control point at
        the tangent intersection and weight cos(half-angle)."""
        import math
        try:
            C = crv.Center
            r = crv.Radius
            t0 = edge.FirstParameter
            t1 = edge.LastParameter
        except Exception:
            return None
        total = t1 - t0
        if not (total > 1e-9) or not (r > 0):
            return None

        nseg = max(1, int(math.ceil(total / (math.pi / 2) - 1e-9)))
        dt = total / nseg
        half = dt / 2.0
        wmid = math.cos(half)
        if wmid < 1e-6:
            return None

        def val(t):
            p = crv.value(t)
            return (p.x, p.y, p.z)

        poles = [(*val(t0), 1.0)]
        for i in range(nseg):
            a = t0 + i * dt
            m = a + half
            b = a + dt
            mx, my, mz = val(m)
            # tangent-intersection control point: C + (Pm - C) / cos(half)
            poles.append((C.x + (mx - C.x) / wmid,
                          C.y + (my - C.y) / wmid,
                          C.z + (mz - C.z) / wmid, wmid))
            poles.append((*val(b), 1.0))

        n = len(poles)                      # 2*nseg + 1
        crv3 = r3.NurbsCurve(3, True, 3, n)  # dim 3, rational, order 3 (degree 2)
        for i, (x, y, z, w) in enumerate(poles):
            crv3.Points[i] = r3.Point4d(x * w, y * w, z * w, w)
        # Clamped knots; interior segment boundaries carry multiplicity 2.
        knots = [0.0, 0.0]
        for i in range(1, nseg):
            knots.append(float(i) / nseg)
            knots.append(float(i) / nseg)
        knots.extend([1.0, 1.0])            # count = n + 1 (= n + degree - 1)
        for i, k in enumerate(knots):
            crv3.Knots[i] = k
        return crv3

    def _edgeToNurbsCurve3D(self, edge):
        """Convert a FreeCAD edge to a 3D r3.NurbsCurve.
        Order of preference: exact rational arc (circles/arcs) → weight-preserving
        BSpline → discretised polyline."""
        # Some edges (degenerate, surface-bounded, or unknown type) raise when
        # accessing .Curve — catch here and fall back to discretisation.
        crv = None
        try:
            crv = edge.Curve
        except Exception:
            pass

        # Exact rational arc for circular edges (Circle/Arc carry Center+Radius+Axis;
        # ellipses have MajorRadius/MinorRadius, not Radius, so they are excluded).
        if (crv is not None and not isinstance(crv, Part.BSplineCurve)
                and hasattr(crv, 'Center') and hasattr(crv, 'Radius')
                and hasattr(crv, 'Axis')):
            try:
                arc = self._arcEdgeToR3(edge, crv)
                if arc is not None and arc.IsValid:
                    return arc
            except Exception as e:
                FreeCAD.Console.PrintMessage(f"  exact arc build failed: {e}\n")

        # Preferred path: get an exact (possibly rational) BSpline for the edge
        # and build a weight-preserving NurbsCurve.
        bs = None
        if isinstance(crv, Part.BSplineCurve):
            bs = crv
        elif crv is not None and hasattr(crv, 'toBSpline'):
            try:
                bs = crv.toBSpline(edge.FirstParameter, edge.LastParameter)
            except Exception:
                try:
                    bs = crv.toBSpline()
                except Exception:
                    bs = None
        if bs is not None:
            try:
                rh = self._makeR3Curve(bs)
                if rh is not None and rh.IsValid:
                    return rh
            except Exception as e:
                FreeCAD.Console.PrintMessage(f"  edge BSpline build failed: {e}\n")

        # Fallback: discretise to a degree-1 polyline
        try:
            pts = edge.discretize(64)
            rh_pts = [r3.Point3d(p.x, p.y, p.z) for p in pts]
        except Exception:
            if crv is not None:
                try:
                    t0, t1 = edge.FirstParameter, edge.LastParameter
                    pts = [crv.value(t0 + (t1 - t0) * i / 63) for i in range(64)]
                    rh_pts = [r3.Point3d(p.x, p.y, p.z) for p in pts]
                except Exception:
                    return None
            else:
                return None
        if len(rh_pts) < 2:
            return None
        return r3.NurbsCurve.Create(False, 1, rh_pts)

    def _edgeToUVCurve(self, edge, fc_surface):
        """Build an approximate UV trim curve for an edge on a surface.
        Projects N sampled 3D edge points into surface parameter space and
        returns a degree-1 r3.NurbsCurve with z=0 (used as 2-D trim curve)."""
        t0 = edge.FirstParameter
        t1 = edge.LastParameter
        N = 24
        uv_pts = []
        for i in range(N + 1):
            t = t0 + (t1 - t0) * i / N
            try:
                pt = edge.Curve.value(t)
                u, v = fc_surface.parameter(pt)
                uv_pts.append(r3.Point3d(u, v, 0.0))
            except Exception:
                continue

        if len(uv_pts) < 2:
            return None

        nc = r3.NurbsCurve.Create(False, 1, uv_pts)
        # rhino3dm trim curves must be dimension-2; try ChangeDimension if available
        if nc and hasattr(nc, 'ChangeDimension'):
            nc.ChangeDimension(2)
        return nc

    def processFaceAsBrep(self, fc_face):
        """Export a FreeCAD Part.Face as a trimmed rhino3dm Brep.
        Converts the face surface to NURBS (via toNurbs() for analytic types),
        builds a Brep with the surface, 3-D edge curves, and sampled UV trim
        curves, then validates and adds to the model.
        Returns True if a Brep was added, False to request fallback."""
        try:
            # ---- surface -----------------------------------------------
            fc_nurbs_face = fc_face
            surface = fc_face.Surface

            if not isinstance(surface, Part.BSplineSurface):
                try:
                    nurbs_shape = fc_face.toNurbs()
                    if nurbs_shape.Faces:
                        fc_nurbs_face = nurbs_shape.Faces[0]
                        surface = fc_nurbs_face.Surface
                except Exception as e:
                    FreeCAD.Console.PrintMessage(f"    toNurbs() failed: {e}\n")
                    return False
                if not isinstance(surface, Part.BSplineSurface):
                    return False

            ns = self._bsplineSurfaceToR3(surface)
            if ns is None:
                return False

            # ---- Brep skeleton -----------------------------------------
            # BrepSurfaceList.Add is not exposed in rhino3dm Python; use
            # CreateFromSurface instead — this registers the surface at
            # index 0 and creates one untrimmed face (also index 0).
            brep = r3.Brep.CreateFromSurface(ns)
            if brep is None:
                FreeCAD.Console.PrintMessage("    CreateFromSurface returned None\n")
                return False
            brep_face = brep.Faces[0]

            # ---- wires (outer loop + inner holes) ----------------------
            wires = fc_nurbs_face.Wires
            if not wires:
                return False

            # BrepLoopType enum is not exposed in rhino3dm Python;
            # use RhinoCommon integer values: Outer=1, Inner=2
            LOOP_OUTER = 1
            LOOP_INNER = 2

            for w_idx, wire in enumerate(wires):
                loop_type = LOOP_OUTER if w_idx == 0 else LOOP_INNER
                loop = brep.Loops.Add(loop_type, brep_face)

                edges = (wire.OrderedEdges
                         if hasattr(wire, 'OrderedEdges') else wire.Edges)

                for edge in edges:
                    if not edge.Vertexes:
                        continue                     # fully degenerate

                    nc3d = self._edgeToNurbsCurve3D(edge)
                    if nc3d is None:
                        continue
                    c3d_idx = brep.Curves3D.Add(nc3d)

                    v_s = edge.Vertexes[0].Point
                    v_e = edge.Vertexes[-1].Point
                    v0 = brep.Vertices.Add(r3.Point3d(v_s.x, v_s.y, v_s.z), 0.01)
                    v1 = brep.Vertices.Add(r3.Point3d(v_e.x, v_e.y, v_e.z), 0.01)
                    brep_edge = brep.Edges.Add(v0, v1, c3d_idx, 0.01)

                    nc2d = self._edgeToUVCurve(edge, surface)
                    if nc2d is None:
                        continue
                    c2d_idx = brep.Curves2D.Add(nc2d)

                    trim = brep.Trims.Add(brep_edge, False, loop, c2d_idx)
                    trim.SetTolerances(0.01, 0.01)

            # ---- validate ----------------------------------------------
            if not brep.IsValid:
                brep.Repair(0.01, True, True)

            if brep.IsValid:
                self.model.Objects.AddBrep(brep, self._makeAttrs())
                stype = type(fc_face.Surface).__name__
                FreeCAD.Console.PrintMessage(f"    {stype} → Brep added\n")
                return True

            FreeCAD.Console.PrintMessage(
                f"    Brep invalid for {type(fc_face.Surface).__name__}, "
                f"falling back to surface\n"
            )
            return False

        except Exception as e:
            FreeCAD.Console.PrintMessage(f"    processFaceAsBrep failed: {e}\n")
            traceback.print_exc()
            return False

    def processSurface(self, obj):
        if isinstance(obj.Surface, Part.BSplineSurface):
            self.processBSplineSurface(obj)
        elif isinstance(obj.Surface, Part.Plane):
            self.processSurfacePlane(obj)
        elif isinstance(obj.Surface, Part.Cylinder):
            self.processSurfaceCylinder(obj)
        elif isinstance(obj.Surface, Part.Cone):
            self.processSurfaceCone(obj)
        elif isinstance(obj.Surface, Part.Sphere):
            self.processSurfaceSphere(obj)
        elif isinstance(obj.Surface, Part.Toroid):
            self.processSurfaceToroid(obj)
        else:
            self.processSurfaceGeneric(obj)

    def processFaceBoundaryCurves(self, fc_face, face_label=""):
        """Export the 3D boundary edges of a face as NurbsCurve objects.
        These are grouped with the parent surface so the trim boundary is
        visible in Rhino even though the surface itself is untrimmed."""
        wires = getattr(fc_face, 'Wires', None)
        if not wires:
            return
        exported = skipped = 0
        for w_idx, wire in enumerate(wires):
            edges = (wire.OrderedEdges
                     if hasattr(wire, 'OrderedEdges') else wire.Edges)
            for e_idx, edge in enumerate(edges):
                try:
                    nc = self._edgeToNurbsCurve3D(edge)
                    if nc is None:
                        skipped += 1
                        continue
                    self.model.Objects.AddCurve(nc, self._makeAttrs())
                    exported += 1
                except Exception as e:
                    skipped += 1
                    FreeCAD.Console.PrintMessage(
                        f"  Boundary edge [w{w_idx}][e{e_idx}] skipped: {e}\n"
                    )
        if skipped:
            tag = f" ({face_label})" if face_label else ""
            FreeCAD.Console.PrintMessage(
                f"  {self._current_label} boundary{tag}: {exported} exported,"
                f" {skipped} skipped\n"
            )

    # Map FreeCAD surface types to the names used in rhino3dm / on re-import.
    # BSplineSurface → NurbsSurface matches the name import3DM creates on read-back.
    _SURF_TYPE_NAMES = {
        Part.BSplineSurface: "NurbsSurface",
        Part.Plane:          "Plane",
        Part.Cylinder:       "Cylinder",
        Part.Cone:           "Cone",
        Part.Sphere:         "Sphere",
        Part.Toroid:         "Torus",
    }

    def processFaces(self, obj):
        # NOTE: processFaceAsBrep is retained in the code but not called here.
        # rhino3dm 8.17.0 Python bindings do not expose the Brep topology tables
        # (Loops, Trims, Curves2D, Curves3D) needed to build trimmed Breps from
        # scratch. Until a newer rhino3dm release exposes these, faces are exported
        # as untrimmed NurbsSurfaces with their boundary curves alongside.
        faces = obj.Shape.Faces
        surf_ok = skip = 0
        base_label = self._current_label
        n_faces = len(faces)
        # Count per type so each gets a unique index: Fillet_NurbsSurface_0, _1, …
        type_counts = {}
        for i, f in enumerate(faces):
            if not self.checkShapeForSurface(f):
                continue
            if n_faces > 1:
                # Name by surface type only — the 3DM group already carries the
                # parent object label, so no need to repeat it here.
                surf_type = self._SURF_TYPE_NAMES.get(
                    type(f.Surface),
                    type(f.Surface).__name__
                )
                idx = type_counts.get(surf_type, 0)
                type_counts[surf_type] = idx + 1
                self._current_label = f"{surf_type}_{idx}"
            # Skip unbounded faces (no trim wires).  An unbounded face exports
            # a surface with no boundary curves; on re-import it becomes a large
            # untrimmed surface that obscures correctly-trimmed geometry.
            if not getattr(f, 'Wires', None):
                FreeCAD.Console.PrintMessage(
                    f"  Skipping unbounded face ({self._current_label}): no wires\n"
                )
                skip += 1
                continue
            # Trimmed-Brep path: collect a trim3dm face dict and skip the
            # untrimmed surface + boundary curves (the trimmed Brep replaces
            # them). On any failure, fall through to the untrimmed export below.
            if self._trim_export:
                try:
                    # Encode "{group}::{face}" in the Brep name (rhino3dm groups
                    # can't be set on trim3dm-written Breps). import_trim_3DM
                    # splits this back into a FreeCAD group, so the imported tree
                    # matches the untrimmed import: <object> group / <face>.
                    face_lbl = self._current_label
                    nm = (f"{base_label}{_TRIM_GROUP_SEP}{face_lbl}"
                          if base_label and base_label != face_lbl else face_lbl)
                    self._trim_faces.append(_trimFaceDict(f, nm))
                    surf_ok += 1
                    continue
                except Exception as e:
                    FreeCAD.Console.PrintMessage(
                        f"  trim dict failed ({self._current_label}): {e}"
                        f" — untrimmed fallback for this face\n")
            try:
                self.processSurface(f)
                # Boundary curves are NurbyCurve objects — name them by type,
                # not by the surface name; the group provides parent context.
                face_label = self._current_label   # e.g. "Plane_14"
                self._current_label = "NurbsCurve"
                self.processFaceBoundaryCurves(f, face_label)
                surf_ok += 1
            except Exception as e:
                FreeCAD.Console.PrintMessage(
                    f"  Face {type(f.Surface).__name__} failed: {e}\n"
                )
                skip += 1
        self._current_label = base_label
        if skip:
            FreeCAD.Console.PrintMessage(
                f"  {base_label}: {surf_ok} faces exported, {skip} failed\n"
            )
    def checkShape(self, obj):
        if not hasattr(obj, "Shape"):
            return
        if self.checkShapeForSurface(obj):
            self.processSurface(obj)
            return
        if self.checkShapeForCurves(obj):
            self.curvesToNurbs(obj)
            return
        self.processFaces(obj)

    # TypeIds that are *containers*: they hold other objects but carry no
    # exportable solid of their own — recurse into their children instead.
    _CONTAINER_TYPES = (
        "App::Part",
        "App::Link",
        "App::LinkGroup",
        "App::DocumentObjectGroup",
        "Std::Part",
    )

    # Helper / datum objects that have no exportable solid geometry.
    _SKIP_TYPES = (
        "App::Origin",
        "App::OriginGroup",
        "App::Line",
        "App::Plane",
        "App::OriginFeature",
        "PartDesign::Plane",
        "PartDesign::Line",
        "PartDesign::Point",
        "PartDesign::CoordinateSystem",
        "Sketcher::SketchObject",
    )

    def _children(self, obj):
        """Children to recurse into for a container object.
        Prefer .Group (clean list of contained objects, excludes Origin),
        fall back to .OutList."""
        grp = getattr(obj, "Group", None)
        if grp:
            return grp
        return getattr(obj, "OutList", []) or []

    def addObjToModel(self, obj, visited=None):
        """Export obj's geometry (recursing into container objects).

        The previous implementation switched on a fixed whitelist of TypeIds
        (Part::Feature, Part::FeaturePython and a few primitives) and only ever
        looked at the first selected object plus its direct OutList.  Any
        document whose geometry lived inside a PartDesign Body or a nested
        App::Part therefore produced an almost-empty .3dm, because the
        Body/feature TypeIds matched no case and the container was never
        descended into.

        This version:
          * recurses into container objects (App::Part, App::Link, groups …),
          * exports a PartDesign::Body's final solid exactly once (Body.Shape),
          * exports any other object that exposes a real (non-null) Shape,
        with a visited-set guard so shared/linked objects aren't exported twice.
        """
        if visited is None:
            visited = set()
        name = getattr(obj, "Name", None)
        if name is not None:
            if name in visited:
                return
            visited.add(name)

        tid = getattr(obj, "TypeId", "")

        # --- skip pure helper/datum objects --------------------------------
        if tid in self._SKIP_TYPES:
            return

        # --- containers: recurse into children, export nothing directly ----
        if tid in self._CONTAINER_TYPES:
            for child in self._children(obj):
                self.addObjToModel(child, visited)
            return

        # --- set up a named group for this object's geometry ---------------
        label = getattr(obj, "Label", None) or name or ""
        self._current_label = label
        if label:
            grp = r3.Group()
            grp.Name = label
            self.model.Groups.Add(grp)
            self._group_idx = len(self.model.Groups) - 1
        else:
            self._group_idx = -1

        # --- PartDesign Body: export the resulting solid only --------------
        # Iterating the Body's individual features (Pad, Pocket, Fillet …)
        # would export many overlapping intermediate solids; Body.Shape is the
        # final result.
        if tid == "PartDesign::Body":
            self.checkShape(obj)
            return

        # --- Part::Box fast path: exact box brep ---------------------------
        if tid == "Part::Box":
            box = r3.Box(r3.BoundingBox(
                0, 0, 0,
                length(obj.Length),
                length(obj.Width),
                length(obj.Height)))
            brp = r3.Brep.CreateFromBox(box)
            self.model.Objects.AddBrep(brp, self._makeAttrs())
            return

        # --- meshes are not handled ----------------------------------------
        if tid == "Mesh::Feature":
            return

        # --- anything else with a real Shape: export its faces/curves ------
        shape = getattr(obj, "Shape", None)
        if shape is not None:
            try:
                empty = shape.isNull()
            except Exception:
                empty = False
            if not empty:
                self.checkShape(obj)
                return

        # --- last resort: object had no shape but may hold children --------
        for child in self._children(obj):
            self.addObjToModel(child, visited)

    def write(self, filepath):
        self.model.Write(filepath, 0)


def exportDoc3DM(filepath, fileExt):
    rModel = rhinoModel()
    visited = set()
    # Export only top-level objects; addObjToModel recurses into containers,
    # so iterating every document object would double-export their children.
    for obj in FreeCAD.ActiveDocument.RootObjects:
        rModel.addObjToModel(obj, visited)
    rModel.write(filepath)

def export3DM(exportList, filepath, fileExt):
    rModel = rhinoModel()
    # FreeCAD passes a list of the selected objects (or, with nothing selected,
    # the document's objects). Export them all; addObjToModel recurses into any
    # container (App::Part, PartDesign::Body, …) so geometry nested inside is
    # found rather than silently dropped.
    if not isinstance(exportList, (list, tuple)):
        exportList = [exportList]
    labels = ", ".join(getattr(o, "Label", "?") for o in exportList)
    FreeCAD.Console.PrintMessage(f"Export 3DM {__version__}: {labels}\n")

    # Trimmed-Brep export via the optional trim3dm extension. If the preference
    # is on but trim3dm isn't built, warn and fall back to untrimmed export.
    trim3dm = None
    if getExportTrimmedBreps():
        trim3dm = _import_trim3dm()
        if trim3dm is None:
            FreeCAD.Console.PrintWarning(
                "ImportExport_3DM: ExportTrimmedBreps is enabled but the "
                "'trim3dm' extension is not available (not built for this "
                "Python). Exporting UNTRIMMED surfaces + boundary curves. "
                "Build trim3dm (see trim3dm/README.md) for trimmed export.\n")
        else:
            rModel._trim_export = True

    visited = set()
    for obj in exportList:
        rModel.addObjToModel(obj, visited)
    rModel.write(filepath)

    # Add the collected trimmed Breps to the file rhino3dm just wrote.
    if trim3dm is not None and rModel._trim_faces:
        try:
            ok = trim3dm.add_trimmed_breps(filepath, filepath, rModel._trim_faces)
            FreeCAD.Console.PrintMessage(
                f"  trim3dm: added {len(rModel._trim_faces)} trimmed Brep(s)"
                f" ({'ok' if ok else 'write failed'})\n")
        except Exception as e:
            FreeCAD.Console.PrintError(
                f"  trim3dm.add_trimmed_breps failed: {e}\n")

    FreeCAD.Console.PrintMessage(f"Written: {filepath}\n")
def length(lenQuantity):
    return Units.Quantity(lenQuantity).Value
    #return r3.Interval(0, Units.Quantity(lenQuantity).Value)


def export(exportList, filepath):
    "called when FreeCAD exports a file"
    import os

    path, fileExt = os.path.splitext(filepath)
    if fileExt.lower() == ".3dm":
        export3DM(exportList, filepath, fileExt)

