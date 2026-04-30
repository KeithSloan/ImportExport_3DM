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
__version__ = "0.2.14"

import FreeCAD, os, Part, traceback
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

    def addControlPoint(self, x, y, z):
        import rhino3dm
        cp = r3.Point3d(x,y,z)
        #cp = rhino3dm.Point3d(x,y,z)
        self.ControlPoints.append(cp)

    def createNurbsCurve(self, degree, poles):
        polesList = []
        for p in poles:
            # getPoles() returns FreeCAD.Vector objects (.x/.y/.z);
            # curve poles from getPoles() may be tuples — handle both
            if hasattr(p, 'x'):
                polesList.append(r3.Point3d(p.x, p.y, p.z))
            else:
                polesList.append(r3.Point3d(p[0], p[1], p[2]))
        if len(polesList) < degree + 1:
            FreeCAD.Console.PrintMessage(f"  createNurbsCurve: {len(polesList)} poles insufficient for degree {degree}\n")
            return None
        NurbsCurve = r3.NurbsCurve(degree, len(polesList))
        nc = NurbsCurve.Create(False, degree, polesList)
        return nc

    def addNurbsCurve(self, degree, knots, mults, poles):
        polesList = []
        for p in poles:
            if hasattr(p, 'x'):
                polesList.append(r3.Point3d(p.x, p.y, p.z))
            else:
                polesList.append(r3.Point3d(p[0], p[1], p[2]))
        NurbsCurve = r3.NurbsCurve(degree, len(polesList))
        nc = NurbsCurve.Create(False, degree, polesList)
        self.model.Objects.AddCurve(nc, self._makeAttrs())

    def processNurbEdges(self, nurbs):
        valid = False
        self.curves = []
        for e in nurbs.Edges:
            if len(e.Vertexes) > 1:         # Avoid error degenerate edge
                if hasattr(e, 'Curve'):
                    degree = e.Curve.Degree
                    knots = e.Curve.getKnots()
                    mults = e.Curve.getMultiplicities()
                    poles = e.Curve.getPoles()
                    self.curves.append(self.addNurbsCurve(degree, knots, mults, poles))
                valid = True
        #if valid: self.addNurbsCurve(3)        # degree 3
        #degree =  e.Curve.NbKnots - e.Curve.NbPoles - 1
        #print(f"Degree = {degree}")
        #if valid: self.addNurbsCurve(degree)


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

    def processSurfaceUV(self, surface):
        UDegree = surface.UDegree
        UOrder = UDegree + 1
        VDegree = surface.VDegree
        VOrder = VDegree + 1
        UPoles = surface.NbUPoles
        VPoles = surface.NbVPoles
        poles = surface.getPoles()
        # poles[u][v] — shape is UPoles x VPoles
        if VDegree == 1 and VPoles == 2:
            # Ruled surface: two boundary U-curves at V=0 and V=VPoles-1
            # Each rail has UPoles points and runs at UDegree
            rail0 = [poles[u][0]          for u in range(UPoles)]
            rail1 = [poles[u][VPoles - 1] for u in range(UPoles)]
            curve0 = self.createNurbsCurve(UDegree, rail0)
            curve1 = self.createNurbsCurve(UDegree, rail1)
            if curve0 is None or curve1 is None:
                FreeCAD.Console.PrintMessage(f"  processSurfaceUV: ruled surface rail creation failed\n")
                return
            nurbSurf = r3.NurbsSurface.Create(3, False, UOrder, VOrder, UPoles, VPoles)
            ns = nurbSurf.CreateRuledSurface(curve0, curve1)
            if ns is not None:
                self.model.Objects.AddSurface(ns, self._makeAttrs())
            else:
                FreeCAD.Console.PrintMessage(f"  processSurfaceUV: CreateRuledSurface returned None\n")
        else:
            self.processSurfaceUVGeneral(surface, UDegree, UOrder, VDegree, VOrder,
                                         UPoles, VPoles, poles)

    def processSurfaceUVGeneral(self, surface, UDegree, UOrder, VDegree, VOrder,
                                UPoles, VPoles, poles):
        """General BSpline surface: set all control points and knots directly.
        Requires rhino3dm >= 8.0.0 for NurbsSurfacePointList.SetPoint."""
        nurbSurf = r3.NurbsSurface.Create(3, False, UOrder, VOrder, UPoles, VPoles)
        if nurbSurf is None:
            FreeCAD.Console.PrintMessage(f"  NurbsSurface.Create failed UOrder={UOrder} VOrder={VOrder} "
                  f"UPoles={UPoles} VPoles={VPoles}\n")
            return

        # Control points — poles[u][v]
        pts = nurbSurf.Points
        for u in range(UPoles):
            for v in range(VPoles):
                p = poles[u][v]
                pt = r3.Point3d(p.x, p.y, p.z) if hasattr(p, 'x') \
                     else r3.Point3d(p[0], p[1], p[2])
                # Try each known API variant for setting a control point.
                # The diagnostic print above will show what's available.
                # rhino3dm 8.x: __setitem__ takes a (u, v) tuple with Point4d
                pts[u, v] = r3.Point4d(pt.X, pt.Y, pt.Z, 1.0)

        # Knot vectors: expand FreeCAD (knots + mults), then drop first and last
        # for rhino3dm's convention (rhino count = nPoles + degree - 1)
        def expandKnots(knots, mults):
            seq = []
            for k, m in zip(knots, mults):
                seq.extend([k] * int(m))
            return seq[1:-1]     # drop first and last

        uSeq = expandKnots(surface.getUKnots(), surface.getUMultiplicities())
        vSeq = expandKnots(surface.getVKnots(), surface.getVMultiplicities())

        for i, k in enumerate(uSeq):
            nurbSurf.KnotsU[i] = k
        for i, k in enumerate(vSeq):
            nurbSurf.KnotsV[i] = k

        self.model.Objects.AddSurface(nurbSurf, self._makeAttrs())


    def processSurfaceUV3(self, surface):
        FreeCAD.Console.PrintMessage(f"=========== Process Surface UV\n")
        plane = r3.Plane.WorldXY
        planeSurf = r3.PlaneSurface(plane, 10, 5)
        ns = planeSurface.ToNurbsSurface()
        u_interval = r3.Interval(0.0, 15.0)
        v_interval = r3.Interval(0.0, 7.5)
        u_degree = 2
        v_degree = 2
        u_points = 10
        v_points = 10
        srf = r3.NurbsSurface.CreateFromPlane(plane, u_interval, v_interval, u_degree, v_degree, u_points, v_points)
        if srf and srf.IsValid:
            return srf
        return None


    def processSurfaceUV2(self, surface):
        FreeCAD.Console.PrintMessage(f"=========== Process Surface UV\n")
        plane = r3.Plane.WorldXY
        u_interval = r3.Interval(0.0, 15.0)
        v_interval = r3.Interval(0.0, 7.5)
        u_degree = 2
        v_degree = 2
        u_points = 10
        v_points = 10
        srf = r3.NurbsSurface.CreateFromPlane(plane, u_interval, v_interval, u_degree, v_degree, u_points, v_points)
        if srf and srf.IsValid:
            return srf
        return None


    def createSpline(self, knots):
        spline = r3.Curve
        #spline.CreateControlPointCurve(


    def checkForSurfaceUV(self, face):
        if hasattr(face, "Surface"):
            if hasattr(face.Surface, "UDegree") and \
               hasattr(face.Surface, "VDegree"):
               #USpline = self.createSpline(face.Surface.NbUKnots)
               #USpline = self.createSpline(face.Surface.getUKnots())
               #VSpline = self.createSpline(face.Surface.NbVKnots)
               #VSpline = self.createSpline(face.Surface.getVKnots())
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
        """Convert a Part.BSplineSurface to r3.NurbsSurface.
        Shares logic with processSurfaceUVGeneral but returns the object."""
        UDegree = surface.UDegree
        VDegree = surface.VDegree
        UPoles  = surface.NbUPoles
        VPoles  = surface.NbVPoles
        poles   = surface.getPoles()

        ns = r3.NurbsSurface.Create(3, False, UDegree + 1, VDegree + 1, UPoles, VPoles)
        if ns is None:
            return None

        pts = ns.Points
        for u in range(UPoles):
            for v in range(VPoles):
                p = poles[u][v]
                if hasattr(p, 'x'):
                    pts[u, v] = r3.Point4d(p.x, p.y, p.z, 1.0)
                else:
                    pts[u, v] = r3.Point4d(p[0], p[1], p[2], 1.0)

        def _expand(knots, mults):
            seq = []
            for k, m in zip(knots, mults):
                seq.extend([k] * int(m))
            return seq[1:-1]

        for i, k in enumerate(_expand(surface.getUKnots(), surface.getUMultiplicities())):
            ns.KnotsU[i] = k
        for i, k in enumerate(_expand(surface.getVKnots(), surface.getVMultiplicities())):
            ns.KnotsV[i] = k

        return ns

    def _edgeToNurbsCurve3D(self, edge):
        """Convert a FreeCAD edge to a 3D r3.NurbsCurve (poles only — knots
        are recalculated by rhino3dm, which is accurate for degree-1 and
        sufficient for trimming purposes)."""
        # Some edges (degenerate, surface-bounded, or unknown type) raise when
        # accessing .Curve — catch here and fall back to discretisation.
        crv = None
        try:
            crv = edge.Curve
        except Exception:
            pass

        if crv is not None and isinstance(crv, Part.BSplineCurve):
            poles = crv.getPoles()
            rh_pts = [r3.Point3d(p.x, p.y, p.z) for p in poles]
            degree = min(crv.Degree, len(rh_pts) - 1)
        else:
            # Line, Arc, Circle, undefined type, etc. — discretise to a polyline
            try:
                pts = edge.discretize(32)
                rh_pts = [r3.Point3d(p.x, p.y, p.z) for p in pts]
            except Exception:
                if crv is not None:
                    try:
                        t0, t1 = edge.FirstParameter, edge.LastParameter
                        pts = [crv.value(t0 + (t1 - t0) * i / 31) for i in range(32)]
                        rh_pts = [r3.Point3d(p.x, p.y, p.z) for p in pts]
                    except Exception:
                        return None
                else:
                    return None
            degree = 1

        if len(rh_pts) < degree + 1:
            degree = len(rh_pts) - 1
        if degree < 1 or len(rh_pts) < 2:
            return None
        return r3.NurbsCurve.Create(False, degree, rh_pts)

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

    def addObjToModel(self, obj):
        # Create a named group for this FreeCAD object so all its faces/curves
        # are grouped together in the .3dm file under obj.Label.
        label = getattr(obj, "Label", None) or getattr(obj, "Name", None) or ""
        self._current_label = label
        if label:
            grp = r3.Group()
            grp.Name = label
            self.model.Groups.Add(grp)
            self._group_idx = len(self.model.Groups) - 1
        else:
            self._group_idx = -1

        while switch(obj.TypeId):
            if case("App::Part"):
                break

            if case("Part::FeaturePython"):
                self.checkShape(obj)
                break

            if case("Part::Feature"):
                self.checkShape(obj)
                break

            if case("Part::Sphere", "Part::Cylinder", "Part::Cone", "Part::Torus"):
                # Primitive solids — export via their faces
                self.checkShape(obj)
                break

            if case("Part::Box"):
                box = r3.Box(r3.BoundingBox(
                    0, length(obj.Length),
                    0, length(obj.Width),
                    0, length(obj.Height)))
                brp = r3.Brep.CreateFromBox(box)
                self.model.Objects.AddBrep(brp, self._makeAttrs())
                break

            if case("Part::Prism", "Part::RegularPolygon", "Part::Extrusion"):
                self.checkShape(obj)
                break

            if case("Mesh::Feature"):
                break

            break

    def write(self, filepath):
        self.model.Write(filepath, 0)


def exportDoc3DM(filepath, fileExt):
    rModel = rhinoModel()
    for obj in FreeCAD.ActiveDocument.Objects:
        addObjToModel(obj)
    rModel.Write(filepath, 0)

def export3DM(first, filepath, fileExt):
    FreeCAD.Console.PrintMessage(f"Export 3DM {__version__}: {first.Label}\n")
    rModel = rhinoModel()
    rModel.addObjToModel(first)
    if hasattr(first, "OutList"):
        for obj in first.OutList:
            rModel.addObjToModel(obj)
    rModel.write(filepath)
    FreeCAD.Console.PrintMessage(f"Written: {filepath}\n")
def length(lenQuantity):
    return Units.Quantity(lenQuantity).Value
    #return r3.Interval(0, Units.Quantity(lenQuantity).Value)


def export(exportList, filepath):
    "called when FreeCAD exports a file"
    import os

    first = exportList[0]
    path, fileExt = os.path.splitext(filepath)
    if fileExt.lower() == ".3dm":
        export3DM(first, filepath, fileExt)

