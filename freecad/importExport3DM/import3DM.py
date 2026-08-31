# **************************************************************************
# *                                                                        *
# *   Copyright (c) 2020 Keith Sloan <keith@sloan-home.co.uk>              *
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
# *   Acknowledgements :                                                   *
# *                                                                        *
# *                                                                        *
# **************************************************************************

__version__ = "0.3.1"

import FreeCAD
import os, io, sys
import FreeCADGui
import Part, Draft, math


# try:
#  import rhino3dm as r3
#
# except:
#  FreeCAD.Console.PrintError("You must install rhino3dm first !")
#  exit(0)

import rhino3dm as r3

# Check which OCC face-construction paths are available.
# pythonOCC (via ifcOpenShell) gives access to BRepBuilderAPI_MakeFace which
# can trim a surface to an arbitrary wire — needed for proper trim reconstruction.
_PYTHONOCC = False
_FREECAD_MAKE_FACE = False
try:
    from OCC.Core.BRepBuilderAPI import BRepBuilderAPI_MakeFace  # noqa
    _PYTHONOCC = True
except ImportError:
    pass
try:
    # FreeCAD Part.Face(surface, wire) — available in some builds
    import Part as _Part
    _FREECAD_MAKE_FACE = hasattr(_Part, 'Face')
except ImportError:
    pass

# ── Official rhino3dm trim-topology read API (issue #712) ──────────────────────
# rhino3dm >= ~8.32 exposes Brep trim topology to Python: BrepFace.Loops/OuterLoop,
# BrepLoop.LoopType/Trims, BrepTrim.EdgeIndex/IsReversed.  When present (together
# with pythonOCC) we import real Rhino trimmed Breps by reading their loop/trim
# topology directly, instead of the export-driven surface+boundary-curve pairing
# reconstruction used for FreeCAD-authored files and older rhino3dm.
try:
    _HAS_TRIM_API = hasattr(r3.BrepFace, "OuterLoop") and hasattr(r3.BrepFace, "Loops")
except Exception:
    _HAS_TRIM_API = False

# numpy is used to fit analytic primitives (cylinder/cone/sphere/plane) from the
# Brep face geometry when ImportNativePrimitives is on.  If it is unavailable the
# importer simply uses NURBS surfaces for every face.
try:
    import numpy as _np
    _HAVE_NUMPY = True
except Exception:
    _HAVE_NUMPY = False

FreeCAD.Console.PrintMessage(
    f"import3DM {__version__}: pythonOCC={_PYTHONOCC}  Part.Face={_FREECAD_MAKE_FACE}"
    f"  BrepTrimAPI={_HAS_TRIM_API}  (rhino3dm {getattr(r3, '__version__', '?')})\n"
)

# ── pythonOCC helpers ─────────────────────────────────────────────────────────

def _occ_knots_mults(rh_knots):
    """Convert a rhino3dm internal knot list to (OCC_knots_array, OCC_mults_array).
    rhino3dm drops the first and last knot value; we restore them then compress
    into unique-knot + multiplicity form that OCC expects."""
    from OCC.Core.TColStd import TColStd_Array1OfReal, TColStd_Array1OfInteger
    full = [rh_knots[0]] + list(rh_knots) + [rh_knots[-1]]
    unique_k, mults = [], []
    eps = 1e-10
    for k in full:
        if unique_k and abs(k - unique_k[-1]) < eps:
            mults[-1] += 1
        else:
            unique_k.append(k)
            mults.append(1)
    n = len(unique_k)
    occ_k = TColStd_Array1OfReal(1, n)
    occ_m = TColStd_Array1OfInteger(1, n)
    for i, (k, m) in enumerate(zip(unique_k, mults)):
        occ_k.SetValue(i + 1, k)
        occ_m.SetValue(i + 1, m)
    return occ_k, occ_m


def _r3ns_to_occ(nu):
    """Build a Geom_BSplineSurface from a rhino3dm NurbsSurface."""
    from OCC.Core.Geom import Geom_BSplineSurface
    from OCC.Core.TColgp import TColgp_Array2OfPnt
    from OCC.Core.gp import gp_Pnt

    u_n, v_n = nu.Points.CountU, nu.Points.CountV
    u_deg, v_deg = nu.Degree(0), nu.Degree(1)

    poles = TColgp_Array2OfPnt(1, u_n, 1, v_n)
    rational = False
    wdata = []
    for u in range(u_n):
        wrow = []
        for v in range(v_n):
            p = nu.Points[u, v]
            w = p.W
            poles.SetValue(u + 1, v + 1, gp_Pnt(p.X / w, p.Y / w, p.Z / w))
            wrow.append(w)
            if abs(w - 1.0) > 1e-10:
                rational = True
        wdata.append(wrow)

    u_k, u_m = _occ_knots_mults(list(nu.KnotsU))
    v_k, v_m = _occ_knots_mults(list(nu.KnotsV))

    if rational:
        from OCC.Core.TColStd import TColStd_Array2OfReal
        weights = TColStd_Array2OfReal(1, u_n, 1, v_n)
        for u in range(u_n):
            for v in range(v_n):
                weights.SetValue(u + 1, v + 1, wdata[u][v])
        return Geom_BSplineSurface(
            poles, weights, u_k, v_k, u_m, v_m, u_deg, v_deg, False, False)
    else:
        return Geom_BSplineSurface(
            poles, u_k, v_k, u_m, v_m, u_deg, v_deg, False, False)


def _r3nc_to_occ(geo):
    """Build a Geom_BSplineCurve from a rhino3dm curve (any type)."""
    from OCC.Core.Geom import Geom_BSplineCurve
    from OCC.Core.TColgp import TColgp_Array1OfPnt
    from OCC.Core.gp import gp_Pnt

    nc = geo.ToNurbsCurve()
    n = len(nc.Points)
    deg = nc.Degree

    poles = TColgp_Array1OfPnt(1, n)
    rational = False
    wdata = []
    for i in range(n):
        p = nc.Points[i]
        w = p.W
        poles.SetValue(i + 1, gp_Pnt(p.X / w, p.Y / w, p.Z / w))
        wdata.append(w)
        if abs(w - 1.0) > 1e-10:
            rational = True

    k, m = _occ_knots_mults(list(nc.Knots))

    if rational:
        from OCC.Core.TColStd import TColStd_Array1OfReal
        weights = TColStd_Array1OfReal(1, n)
        for i, w in enumerate(wdata):
            weights.SetValue(i + 1, w)
        return Geom_BSplineCurve(poles, weights, k, m, deg)
    else:
        return Geom_BSplineCurve(poles, k, m, deg)


def _plane_from_nurbs(nu, tol=1.0):
    """Return a gp_Pln if all control points of *nu* lie within *tol* of a
    common plane, otherwise return None.

    Works directly on the rhino3dm NurbsSurface control points so it is
    independent of the OCC surface reconstruction and UV-domain issues.
    *tol* is in the same units as the model (mm for typical FreeCAD models).
    """
    try:
        from OCC.Core.gp import gp_Pnt, gp_Vec, gp_Dir, gp_Pln

        # Collect Cartesian control points (divide by weight for rational)
        pts = []
        for u in range(nu.Points.CountU):
            for v in range(nu.Points.CountV):
                p = nu.Points[u, v]
                w = p.W if p.W != 0.0 else 1.0
                pts.append((p.X / w, p.Y / w, p.Z / w))

        if len(pts) < 3:
            return None

        p0 = pts[0]

        # Find a second point far enough away to define a direction
        v1 = None
        for pt in pts[1:]:
            dx, dy, dz = pt[0] - p0[0], pt[1] - p0[1], pt[2] - p0[2]
            mag = (dx * dx + dy * dy + dz * dz) ** 0.5
            if mag > 1e-3:
                v1 = (dx / mag, dy / mag, dz / mag)
                break
        if v1 is None:
            return None  # all points coincident

        # Find a third point not collinear with p0→v1 to get a normal
        normal = None
        for pt in pts:
            dx, dy, dz = pt[0] - p0[0], pt[1] - p0[1], pt[2] - p0[2]
            nx = v1[1] * dz - v1[2] * dy
            ny = v1[2] * dx - v1[0] * dz
            nz = v1[0] * dy - v1[1] * dx
            mag = (nx * nx + ny * ny + nz * nz) ** 0.5
            if mag > 1e-6:
                normal = (nx / mag, ny / mag, nz / mag)
                break
        if normal is None:
            return None  # all points collinear

        # Check every control point is within *tol* of this plane
        for pt in pts:
            dist = abs(
                (pt[0] - p0[0]) * normal[0]
                + (pt[1] - p0[1]) * normal[1]
                + (pt[2] - p0[2]) * normal[2]
            )
            if dist > tol:
                return None  # not planar within tolerance

        return gp_Pln(gp_Pnt(p0[0], p0[1], p0[2]),
                      gp_Dir(normal[0], normal[1], normal[2]))
    except Exception:
        return None


def _gap_close_wire(wire):
    """If *wire* is open, insert a straight-line segment to close the gap.

    Walks the wire in topological order to find the first and last free
    vertices.  If their distance is non-trivial (> 1e-4) a single closing
    edge is appended.

    Returns (new_wire, n_segs_inserted).
    Returns (None, 0) if the topology can't be walked or the new wire can't
    be built (caller should fall back to the original wire).
    """
    try:
        from OCC.Core.BRepTools import BRepTools_WireExplorer
        from OCC.Core.BRep import BRep_Tool
        from OCC.Core.TopExp import topexp
        from OCC.Core.BRepBuilderAPI import (BRepBuilderAPI_MakeEdge,
                                              BRepBuilderAPI_MakeWire)

        exp = BRepTools_WireExplorer(wire)
        if not exp.More():
            return None, 0

        first_v = exp.CurrentVertex()
        last_edge = exp.Current()
        while exp.More():
            last_edge = exp.Current()
            exp.Next()

        # Last vertex of the last edge (honouring wire orientation)
        last_v = topexp.LastVertex(last_edge, True)

        if first_v.IsNull() or last_v.IsNull():
            return None, 0

        p0 = BRep_Tool.Pnt(first_v)
        p1 = BRep_Tool.Pnt(last_v)
        dist = p0.Distance(p1)

        if dist < 1e-4:
            return wire, 0   # already closed

        # Insert a straight closing segment regardless of gap size — let
        # ShapeFix_Wire and BRepBuilderAPI_MakeFace validate afterwards.
        em = BRepBuilderAPI_MakeEdge(p0, p1)
        if not em.IsDone():
            return None, 0

        wm = BRepBuilderAPI_MakeWire(wire)
        wm.Add(em.Edge())
        if not wm.IsDone():
            return None, 0

        return wm.Wire(), 1

    except Exception:
        return None, 0


# ─────────────────────────────────────────────────────────────────────────────

def _add_as_shell(doc, add_fn, shapes, labels, label='Shell'):
    """Try to stitch *shapes* into a Part shell (and solid if closed).

    *add_fn* is called with the resulting Part::Feature.  If stitching fails,
    individual NurbsSurface features are added instead so nothing is lost.

    *label* is used as the object label for the shell/solid or as a prefix
    for the fallback individual objects.
    """
    result_shape = None
    try:
        shell = Part.makeShell(shapes)
        try:
            solid = Part.makeSolid(shell)
            result_shape = solid
            FreeCAD.Console.PrintMessage(
                f'  {label}: solid from {len(shapes)} surfaces\n')
        except Exception:
            result_shape = shell
            FreeCAD.Console.PrintMessage(
                f'  {label}: shell from {len(shapes)} surfaces'
                f' (could not close into solid)\n')
    except Exception as e:
        FreeCAD.Console.PrintMessage(
            f'  {label}: makeShell failed ({e})'
            f' — importing {len(shapes)} surfaces individually\n')

    if result_shape is not None:
        obj = doc.addObject('Part::Feature', label)
        obj.Shape = result_shape
        obj.Label = label
        add_fn(obj)
    else:
        for shape, lbl in zip(shapes, labels):
            obj = doc.addObject('Part::Feature', 'NurbsSurface')
            obj.Shape = shape
            obj.Label = lbl
            add_fn(obj)


if open.__module__ == "__builtin__":
    pythonopen = (
        open  # to distinguish python built-in open function from the one declared here
    )


def open(filename):
    "called when freecad opens a file."
    global doc
    docname = os.path.splitext(os.path.basename(filename))[0]
    doc = FreeCAD.newDocument(docname)
    if filename.lower().endswith(".3dm"):
        process3DM(doc, filename)
    return doc


def insert(filename, docname):
    "called when freecad imports a file"
    global doc
    groupname = os.path.splitext(os.path.basename(filename))[0]
    try:
        doc = FreeCAD.getDocument(docname)
    except NameError:
        doc = FreeCAD.newDocument(docname)
    if filename.lower().endswith(".3dm"):
        process3DM(doc, filename)


def toFCvec(r3Dpnt):
    return FreeCAD.Vector(r3Dpnt.X, r3Dpnt.Y, r3Dpnt.Z)


def toFCangle(center, start):
    return math.atan((start.Y - center.Y) / (start.X - center.Y)) * math.pi / 180


class File3dm:
    def __init__(self, path):
        self.f3dm = r3.File3dm.Read(path)

    def _try_trim_reconstruction(self, doc, ns_geo, curve_geos, label):
        """Build a properly trimmed Part::Feature from a rhino3dm NurbsSurface
        and its boundary NurbsCurves using pythonOCC BRepBuilderAPI_MakeFace.
        Returns a FreeCAD document object on success, None on failure."""
        try:
            from OCC.Core.BRepBuilderAPI import (BRepBuilderAPI_MakeFace,
                                                  BRepBuilderAPI_MakeEdge)
            from OCC.Core.BRep import BRep_Builder
            from OCC.Core.TopoDS import TopoDS_Wire
            from OCC.Core.BRepLib import breplib
            from OCC.Core.ShapeFix import ShapeFix_Wire
            import tempfile, os

            occ_surf = _r3ns_to_occ(ns_geo)

            # For planar surfaces use an analytical gp_Pln rather than the NURBS.
            # Projecting 3D boundary curves onto an analytical plane is exact —
            # no UV-domain mismatch from the rhino3dm round-trip can affect it.
            # _plane_from_nurbs checks the raw rhino3dm control points directly,
            # which is more robust than checking the OCC-reconstructed surface.
            gp_plane = _plane_from_nurbs(ns_geo, tol=1.0)
            face_surf = gp_plane if gp_plane is not None else occ_surf

            # Build edges individually — no connectivity check at this stage.
            # BRepBuilderAPI_MakeWire rejects disconnected edges (error 2) before
            # ShapeFix gets a chance to stitch them; using BRep_Builder bypasses that.
            raw_edges = []
            for cg in curve_geos:
                try:
                    occ_crv = _r3nc_to_occ(cg)
                    em = BRepBuilderAPI_MakeEdge(occ_crv)
                    if em.IsDone():
                        raw_edges.append(em.Edge())
                except Exception:
                    pass

            if not raw_edges:
                self._trim_fail = f"no edges built from {len(curve_geos)} curves"
                return None

            # Assemble edges into a raw wire without enforcing connectivity
            b = BRep_Builder()
            raw_wire = TopoDS_Wire()
            b.MakeWire(raw_wire)
            for e in raw_edges:
                b.Add(raw_wire, e)

            # ShapeFix_Wire: reorders edges, stitches gaps, fixes orientation.
            # Tolerance 50 mm — gaps arise when boundary curves don't share exact
            # endpoints (curve conversion rounding or missing export edges).
            sfw = ShapeFix_Wire()
            sfw.Load(raw_wire)
            sfw.SetMaxTolerance(50.0)
            sfw.Perform()
            fixed_wire = sfw.Wire()

            # If the fixed wire is still open (e.g. a boundary edge was not exported
            # at all), close the remaining gap with a straight-line segment.
            closed_wire, n_segs = _gap_close_wire(fixed_wire)
            wire = closed_wire if closed_wire is not None else fixed_wire
            if n_segs:
                gap_note = f", +{n_segs} closing seg"
                FreeCAD.Console.PrintMessage(
                    f"  Gap-closed: {label} ({len(raw_edges)} curves)\n"
                )
            else:
                gap_note = ""

            # Build trimmed face.  face_surf is gp_Pln for planar surfaces (exact
            # projection) or Geom_BSplineSurface for curved surfaces.
            #
            # BRepBuilderAPI_MakeFace(surface, wire, Inside):
            #   Inside=True  → face is the region ENCLOSED by the wire (correct)
            #   Inside=False → face is the region OUTSIDE the wire (complement)
            #
            # For gp_Pln (infinite plane) we must use Inside=True so the face is
            # the bounded region.  With Inside=False the orientation-check
            # (BRepCheck_Face.OrientationOfWires) normally catches and reverses the
            # complement — but it silently misses some cases (e.g. Plane_24), leaving
            # a large inverted face.  Using True avoids the problem entirely.
            #
            # For Geom_BSplineSurface (bounded NURBS) False keeps the existing
            # behaviour where the UV-domain bounds the face; the orientation check
            # still runs as a safety net.
            inside = (gp_plane is not None)   # True for gp_Pln, False for NURBS
            fm = BRepBuilderAPI_MakeFace(face_surf, wire, inside)
            if not fm.IsDone():
                self._trim_fail = (
                    f"MakeFace failed: error={fm.Error()} "
                    f"edges={len(raw_edges)}{gap_note}"
                )
                return None

            occ_face = fm.Face()

            # Verify that the face actually received the wire as its trim boundary.
            # BRepBuilderAPI_MakeFace can return IsDone()=True but silently fall back
            # to the surface's natural bounds when projection of the wire onto the
            # surface fails.  A properly trimmed face has at least one TopoDS_Wire.
            from OCC.Core.TopExp import TopExp_Explorer
            from OCC.Core.TopAbs import TopAbs_WIRE
            wire_exp = TopExp_Explorer(occ_face, TopAbs_WIRE)
            face_wire_count = 0
            while wire_exp.More():
                face_wire_count += 1
                wire_exp.Next()
            if face_wire_count == 0:
                # The wire was not projected onto the surface — wire curves are
                # probably slightly off the surface due to rhino3dm round-trip.
                # Retry: create a base face first, project the wire onto it with
                # SameParameter, then add the wire as a trim boundary.
                try:
                    from OCC.Core.BRepLib import breplib as _breplib2
                    base_fm = BRepBuilderAPI_MakeFace(face_surf, 1e-3)
                    if base_fm.IsDone():
                        _breplib2.BuildPCurveForEdgesOnFace(wire, base_fm.Face())
                        fm2 = BRepBuilderAPI_MakeFace(face_surf, wire, False)
                        if fm2.IsDone():
                            occ_face = fm2.Face()
                            wire_exp2 = TopExp_Explorer(occ_face, TopAbs_WIRE)
                            face_wire_count = 0
                            while wire_exp2.More():
                                face_wire_count += 1
                                wire_exp2.Next()
                except Exception:
                    pass
            if face_wire_count == 0:
                self._trim_fail = (
                    f"MakeFace returned untrimmed face (wire not projected onto surface)"
                    f" edges={len(raw_edges)}{gap_note}"
                )
                return None

            breplib.BuildCurves3d(occ_face)

            # Ensure the outer wire is oriented correctly relative to the surface
            # normal (CCW when viewed from outside).  A reversed wire makes the
            # face show as the complement of the intended trim — the large
            # underlying rectangle rather than the small trimmed shape.
            # BRepLib.OrientClosedSolid does not apply to bare faces, so we use
            # BRepCheck_Face to detect the problem and reverse the wire if needed.
            try:
                from OCC.Core.BRepCheck import BRepCheck_Face, BRepCheck_InvalidPolygonOnTriangulation
                from OCC.Core.BRepCheck import BRepCheck_NoError
                from OCC.Core.BRep import BRep_Builder as _BRep_Builder
                from OCC.Core.TopoDS import topods as _topods
                from OCC.Core.TopExp import TopExp_Explorer as _TopExp_Explorer
                from OCC.Core.TopAbs import TopAbs_WIRE as _TopAbs_WIRE

                chk = BRepCheck_Face(occ_face)
                chk.InContext()          # fill in check results
                orient_ok = chk.OrientationOfWires()
                if orient_ok != BRepCheck_NoError:
                    # Reverse the face (which reverses all wires relative to surface)
                    occ_face = occ_face.Reversed()
                    breplib.BuildCurves3d(occ_face)
            except Exception:
                pass   # orientation check optional — don't abort on failure

            # Bridge back to FreeCAD via BREP temp file
            with tempfile.NamedTemporaryFile(suffix='.brep', delete=False) as tf:
                path = tf.name
            from OCC.Core.BRepTools import breptools
            breptools.Write(occ_face, path)

            fc_shape = Part.Shape()
            fc_shape.importBrep(path)
            os.unlink(path)

            if fc_shape.isNull():
                return None

            # The reconstructed face often comes back without valid pcurves —
            # a zero-area, invalid face.  Simple wires still render acceptably,
            # but irregularly-trimmed faces (mixed arc/line/blend boundaries)
            # collapse and display as straight/flat patches.  Try to repair the
            # face; if it is still degenerate, signal a fallback to the untrimmed
            # surface, which is valid and correctly curved (the exporter already
            # segments each surface to the exact face extent).
            def _degenerate(shp):
                try:
                    return shp.isNull() or (not shp.isValid()) or shp.Area < 1e-6
                except Exception:
                    return True

            if _degenerate(fc_shape):
                try:
                    fixed = fc_shape.copy()
                    fixed.fix(1e-6, 1e-6, 1e-6)
                    if not _degenerate(fixed):
                        fc_shape = fixed
                except Exception:
                    pass

            if _degenerate(fc_shape):
                self._trim_fail = "reconstructed face invalid / zero-area"
                return None

            obj = doc.addObject("Part::Feature", "NurbsSurface")
            obj.Shape = fc_shape
            # Record gap-closing so it shows up in the parse_objects summary
            if n_segs:
                self._trim_gap_closed = getattr(self, '_trim_gap_closed', 0) + n_segs
            return obj

        except Exception as e:
            self._trim_fail = f"{type(e).__name__}: {str(e)[:80]}"
            return None

    # ══════════════════════════════════════════════════════════════════════════
    #  Official Brep-topology import  (rhino3dm >= 8.32 read API + pythonOCC)
    # ══════════════════════════════════════════════════════════════════════════

    def parse_objects(self, doc=None):
        """Dispatch importer.  Use the official Brep trim-topology reader for
        files that contain real (Rhino-authored) trimmed Breps whenever the
        rhino3dm read API is present; otherwise fall back to the legacy pairing
        reconstruction (FreeCAD-exported files, older rhino3dm).

        The official path is built entirely on FreeCAD's own ``Part``/OCCT API,
        so it needs **no pythonOCC (OCC.Core)** — only rhino3dm >= 8.32."""
        if not doc:
            doc = FreeCAD.newDocument("3dm import")
        has_trimmed_brep = False
        try:
            for o in self.f3dm.Objects:
                g = o.Geometry
                if isinstance(g, r3.Brep) and (len(g.Faces) > 1 or not g.IsSurface):
                    has_trimmed_brep = True
                    break
        except Exception:
            has_trimmed_brep = False
        if _HAS_TRIM_API and has_trimmed_brep:
            FreeCAD.Console.PrintMessage(
                "  import path: OFFICIAL Brep trim topology (native Part)\n")
            return self.parse_rhino_breps(doc)
        FreeCAD.Console.PrintMessage(
            f"  import path: legacy (TrimAPI={_HAS_TRIM_API} "
            f"pythonOCC={_PYTHONOCC} trimmedBrep={has_trimmed_brep})\n")
        return self.parse_objects_legacy(doc)

    # ---- native (FreeCAD Part) face construction from Brep loop/trim topology --
    #
    # These reuse self.create_nurbs_surface() / self.create_curve() (Part.BSpline*)
    # and build trimmed faces with Part.Face(surface, wire) — no OCC.Core needed.

    def _bspline_edge(self, nc):
        """Part.Edge from a rhino3dm NurbsCurve (clamped boundary edge)."""
        pts = []
        weights = []
        for i in range(len(nc.Points)):
            p = nc.Points[i]
            pts.append(FreeCAD.Vector(p.X / p.W, p.Y / p.W, p.Z / p.W))
            weights.append(p.W)
        knots, mults = self.getFCKnots(nc.Knots)
        bs = Part.BSplineCurve()
        bs.buildFromPolesMultsKnots(pts, mults, knots, False, nc.Degree, weights)
        return bs.toShape()

    def _loop_wire(self, brep, loop):
        """Return (Part.Wire, [Part.Edge]) for a BrepLoop, skipping singular
        trims (EdgeIndex < 0, e.g. cone apex / sphere pole)."""
        edges = []
        try:
            trims = loop.Trims
        except Exception:
            return None, None
        for t in trims:
            ei = getattr(t, "EdgeIndex", -1)
            if ei is None or ei < 0:
                continue
            try:
                edges.append(self._bspline_edge(brep.Edges[ei].ToNurbsCurve()))
            except Exception:
                pass
        if not edges:
            return None, None
        try:
            return Part.Wire(Part.__sortEdges__(edges)), edges
        except Exception:
            try:
                return Part.Wire(edges), edges
            except Exception:
                return None, edges

    # ---- analytic primitive fitting (ImportNativePrimitives) -----------------
    # rhino3dm exposes only the Is<Type>() flag on a Brep face, not the analytic
    # parameters, so we fit them from the underlying surface (sampled via PointAt
    # / NormalAt) and build a native OCCT Plane/Cylinder/Cone/Sphere.  Each fit is
    # validated by max deviation of the samples; over tolerance -> NURBS instead.

    _FIT_TOL = 0.05   # max sample deviation (model units) to accept an analytic fit

    @staticmethod
    def _sample_surface(us, nu=13, nv=5):
        du = us.Domain(0)
        dv = us.Domain(1)
        P = []
        for iu in range(nu):
            for iv in range(nv):
                u = du.T0 + (du.T1 - du.T0) * iu / (nu - 1)
                v = dv.T0 + (dv.T1 - dv.T0) * iv / (nv - 1)
                p = us.PointAt(u, v)
                P.append([p.X, p.Y, p.Z])
        return _np.array(P), du, dv

    @staticmethod
    def _fit_ring(us, vp, du, nu=24):
        r = []
        for iu in range(nu):
            u = du.T0 + (du.T1 - du.T0) * iu / (nu - 1)
            p = us.PointAt(u, vp)
            r.append([p.X, p.Y, p.Z])
        r = _np.array(r)
        c = r.mean(0)
        return c, float(_np.mean(_np.linalg.norm(r - c, axis=1)))

    def _fit_analytic_surface(self, face):
        """Return (Part surface, kind_str) fitted from *face*, or (None, None)."""
        if not (_HAVE_NUMPY and getattr(self, "_native_primitives", True)):
            return None, None
        try:
            us = face.UnderlyingSurface()
            P, du, dv = self._sample_surface(us)
            if face.IsPlanar():
                c = P.mean(0)
                _, _, Vt = _np.linalg.svd(P - c)
                n = Vt[2]
                if float(_np.max(_np.abs((P - c) @ n))) < self._FIT_TOL:
                    return Part.Plane(FreeCAD.Vector(*c), FreeCAD.Vector(*n)), "Plane"
            elif face.IsCylinder() and len(face.Loops) <= 1:
                # NOTE: Part.Cylinder is an *infinite* surface; trimming it with an
                # inner-loop hole (e.g. a branch cut in a T-joint) can crash OCCT
                # uncatchably.  Only fit analytic cylinders for hole-free faces;
                # holed cylinder walls fall through to the domain-bounded NURBS path.
                N = []
                for iu in range(9):
                    for iv in range(3):
                        u = du.T0 + (du.T1 - du.T0) * iu / 8.0
                        v = dv.T0 + (dv.T1 - dv.T0) * iv / 2.0
                        nn = us.NormalAt(u, v)
                        N.append([nn.X, nn.Y, nn.Z])
                N = _np.array(N)
                _, S, Vt = _np.linalg.svd(N - N.mean(0))
                axis = Vt[int(_np.argmin(S))]
                axis = axis / _np.linalg.norm(axis)
                c0 = P.mean(0)
                e1 = _np.cross(axis, [1, 0, 0])
                if _np.linalg.norm(e1) < 1e-6:
                    e1 = _np.cross(axis, [0, 1, 0])
                e1 = e1 / _np.linalg.norm(e1)
                e2 = _np.cross(axis, e1)
                pr = _np.array([[(P[i] - c0) @ e1, (P[i] - c0) @ e2] for i in range(len(P))])
                A = _np.column_stack([pr[:, 0], pr[:, 1], _np.ones(len(pr))])
                s, *_ = _np.linalg.lstsq(A, -(pr[:, 0] ** 2 + pr[:, 1] ** 2), rcond=None)
                cx, cy = -s[0] / 2, -s[1] / 2
                R = _np.sqrt(max(cx * cx + cy * cy - s[2], 0.0))
                cen = c0 + cx * e1 + cy * e2
                dev = max(abs(_np.linalg.norm((P[i] - cen) - ((P[i] - cen) @ axis) * axis) - R)
                          for i in range(len(P)))
                if dev < self._FIT_TOL and R > 1e-6:
                    c = Part.Cylinder()
                    c.Radius = float(R)
                    c.Center = FreeCAD.Vector(*cen)
                    c.Axis = FreeCAD.Vector(*axis)
                    return c, "Cylinder"
            elif face.IsCone() and len(face.Loops) <= 1:
                # same infinite-surface caution as the cylinder case above
                c0, r0 = self._fit_ring(us, dv.T0 + 0.05 * (dv.T1 - dv.T0), du)
                c1, r1 = self._fit_ring(us, dv.T1 - 0.05 * (dv.T1 - dv.T0), du)
                axis = c1 - c0
                d = _np.linalg.norm(axis)
                if d > 1e-9:
                    axis = axis / d
                    ha = float(_np.arctan2(abs(r1 - r0), d))
                    cone = Part.Cone()
                    cone.Center = FreeCAD.Vector(*c0)
                    cone.Radius = float(r0)
                    cone.SemiAngle = ha
                    cone.Axis = FreeCAD.Vector(*axis)
                    return cone, "Cone"
            elif face.IsSphere():
                A = _np.column_stack([2 * P[:, 0], 2 * P[:, 1], 2 * P[:, 2], _np.ones(len(P))])
                s, *_ = _np.linalg.lstsq(A, (P ** 2).sum(1), rcond=None)
                cen = s[:3]
                R = float(_np.sqrt(max(s[3] + cen @ cen, 0.0)))
                dev = max(abs(_np.linalg.norm(P[i] - cen) - R) for i in range(len(P)))
                if dev < self._FIT_TOL and R > 1e-6:
                    sp = Part.Sphere()
                    sp.Radius = R
                    sp.Center = FreeCAD.Vector(*cen)
                    return sp, "Sphere"
        except Exception:
            pass
        return None, None

    def _face_from_brepface(self, brep, face):
        """Reconstruct a trimmed Part.Face from a rhino3dm BrepFace using the
        native Part API.  Preference order per face:
          0. native analytic surface (Plane/Cylinder/Cone/Sphere) when
             ImportNativePrimitives is on and the fit is within tolerance
          1. Part.Face on the NURBS surface (outer[, holes])
          2. Part.makeFilledFace(boundary) for free-form faces whose 3-D wire
             will not project onto the surface
          3. the untrimmed surface (surf.toShape()) — keeps the face
        Returns (Part.Face, how) or (None, 'fail')."""
        outer = None
        outer_edges = None
        inners = []
        try:
            loops = face.Loops
        except Exception:
            loops = []
        for lp in loops:
            w, ed = self._loop_wire(brep, lp)
            if w is None:
                continue
            if str(getattr(lp, "LoopType", "")).endswith("Outer") and outer is None:
                outer = w
                outer_edges = ed
            else:
                inners.append(w)
        if outer is None:
            return None, "no-outer"

        def _mk(surf):
            try:
                f = Part.Face(surf, [outer] + inners) if inners else Part.Face(surf, outer)
                try:
                    f.fix(1e-3, 1e-3, 1e-3)
                except Exception:
                    pass
                if f.Area > 1e-9:
                    return f
            except Exception:
                pass
            return None

        # tier 0 — native analytic primitive.  Part.Face on a full analytic
        # surface (sphere/cylinder) can trim to the COMPLEMENT — the large rest of
        # the surface rather than the small patch — in which case the face is far
        # bigger than its outer boundary wire.  Reject that and fall back to NURBS
        # (whose domain-limited patch trims to the intended region).
        asurf, kind = self._fit_analytic_surface(face)
        if asurf is not None:
            f = _mk(asurf)
            if f is not None:
                wd = outer.BoundBox.DiagonalLength
                if wd < 1e-9 or f.BoundBox.DiagonalLength <= 2.0 * wd:
                    return f, kind
        # tier 1 — NURBS surface
        try:
            nsurf = self.create_nurbs_surface(face.UnderlyingSurface().ToNurbsSurface())
        except Exception:
            nsurf = None
        if nsurf is not None:
            f = _mk(nsurf)
            if f is not None:
                return f, "NURBS"
        # tier 2 — filled face from the 3-D boundary
        if outer_edges:
            try:
                f = Part.makeFilledFace(outer_edges)
                if f is not None and f.Area > 1e-9:
                    if inners:
                        try:
                            fh = f.cutHoles(inners)
                            fh.fix(1e-3, 1e-3, 1e-3)
                            if fh.Area > 1e-9:
                                f = fh
                        except Exception:
                            pass
                    return f, "filled"
            except Exception:
                pass
        # tier 3 — untrimmed surface
        if nsurf is not None:
            try:
                f = nsurf.toShape()
                if f.Area > 1e-9:
                    return f, "untrimmed"
            except Exception:
                pass
        return None, "fail"

    def _import_brep_official(self, doc, brep, label):
        """Reconstruct a full Rhino Brep as a trimmed Part::Feature — a solid if
        the shell closes, otherwise a shell/compound of correctly-trimmed faces.
        Returns (obj, (n_ok, n_fail, how)) or (None, stats)."""
        faces = []
        n_ok = n_fail = 0
        how = {}
        for i in range(len(brep.Faces)):
            f = None
            h = "fail"
            try:
                f, h = self._face_from_brepface(brep, brep.Faces[i])
            except Exception:
                f = None
            how[h] = how.get(h, 0) + 1
            if f is not None:
                faces.append(f)
                n_ok += 1
            else:
                n_fail += 1
        if not faces:
            return None, (n_ok, n_fail, "no faces")
        # sew natively — solid if the shell closes, else shell, else compound
        shape = None
        kind = "?"
        try:
            shell = Part.Shell(faces)
            # Only attempt a Solid on a genuinely closed shell.  Part.Solid()
            # on an open shell (a single trimmed face, or a shell containing a
            # holed face) can raise an OCCT Standard_Failure that is *not*
            # surfaced as a catchable Python exception -- it aborts / segfaults
            # FreeCAD instead of being caught below.  Guarding on isClosed()
            # means an open shell never reaches Part.Solid.
            # (Ref: v1_T-Joint2.3dm hard crash on the first freeform holed face.)
            if shell.isClosed():
                try:
                    solid = Part.Solid(shell)
                    if solid.Volume < 0:
                        solid.reverse()
                    shape = solid
                    kind = "Solid"
                except Exception:
                    shape = shell
                    kind = "Shell"
            else:
                shape = shell
                kind = "Shell(open)"
        except Exception:
            comp = Part.Compound(faces)
            try:
                comp = comp.removeSplitter()
            except Exception:
                pass
            shape = comp
            kind = "Compound"
        obj = doc.addObject("Part::Feature", "Brep")
        obj.Shape = shape
        obj.Label = label
        detail = kind + " [" + " ".join(f"{k}:{v}" for k, v in sorted(how.items())) + "]"
        return obj, (n_ok, n_fail, detail)

    def parse_rhino_breps(self, doc=None):
        """Import a Rhino-authored .3dm: Breps via official trim-topology
        reconstruction, other geometry via import_geometry.  Mirrors 3DM groups
        as FreeCAD groups when ImportCreateGroups is set."""
        if not doc:
            doc = FreeCAD.newDocument("3dm import")
        prefs = FreeCAD.ParamGet(
            "User parameter:BaseApp/Preferences/Mod/ImportExport_3DM")
        create_groups = prefs.GetBool("ImportCreateGroups", True)
        # ImportNativePrimitives: fit analytic Plane/Cylinder/Cone/Sphere surfaces
        # (needs numpy); default on, falls back to NURBS per face when the fit is
        # out of tolerance or numpy is unavailable.
        self._native_primitives = prefs.GetBool("ImportNativePrimitives", True) and _HAVE_NUMPY
        FreeCAD.Console.PrintMessage(
            f"  ImportNativePrimitives={self._native_primitives}\n")

        grp_names = {}
        for gi in range(len(self.f3dm.Groups)):
            g = self.f3dm.Groups[gi]
            grp_names[gi] = g.Name if g.Name else f"Group_{gi}"
        fc_groups = {}
        part = doc.addObject("App::Part", "Part")

        def container_for(attrs):
            if not create_groups or attrs.GroupCount == 0:
                return part
            gi = attrs.GetGroupList()[0]
            if gi not in fc_groups:
                grp = doc.addObject("App::DocumentObjectGroup",
                                    grp_names.get(gi, f"Group_{gi}"))
                grp.Label = grp_names.get(gi, f"Group_{gi}")
                part.addObject(grp)
                fc_groups[gi] = grp
            return fc_groups[gi]

        n_brep = n_other = 0
        for i in range(len(self.f3dm.Objects)):
            r3_obj = self.f3dm.Objects[i]
            geo = r3_obj.Geometry
            attrs = r3_obj.Attributes
            name = attrs.Name
            cont = container_for(attrs)
            if isinstance(geo, r3.Brep) and (len(geo.Faces) > 1 or not geo.IsSurface):
                label = name if name else "Brep"
                obj, stats = self._import_brep_official(doc, geo, label)
                n_ok, n_fail, kind = stats
                if obj is None:
                    FreeCAD.Console.PrintMessage(
                        f"  {label}: Brep reconstruction failed "
                        f"({n_ok} ok / {n_fail} fail) — importing raw geometry\n")
                    fb = self.import_geometry(doc, geo)
                    if fb:
                        fb.Label = label
                        cont.addObject(fb)
                    continue
                FreeCAD.Console.PrintMessage(
                    f"  {label}: {kind} from {n_ok}/{n_ok + n_fail} trimmed faces"
                    + (f" ({n_fail} face fallback)" if n_fail else "") + "\n")
                cont.addObject(obj)
                n_brep += 1
            else:
                obj = self.import_geometry(doc, geo)
                if not obj:
                    continue
                if name:
                    obj.Label = name
                cont.addObject(obj)
                n_other += 1
        doc.recompute()
        try:
            FreeCADGui.SendMsgToActiveView("ViewFit")
        except Exception:
            pass
        FreeCAD.Console.PrintMessage(
            f"  Imported {n_brep} Brep(s) + {n_other} other object(s) "
            f"via official trim topology\n")

    def parse_objects_legacy(self, doc=None):
        if not doc:
            doc = FreeCAD.newDocument("3dm import")

        # Preferences
        prefs = FreeCAD.ParamGet("User parameter:BaseApp/Preferences/Mod/ImportExport_3DM")
        create_groups = prefs.GetBool("ImportCreateGroups", True)
        # When True: after collecting all NurbsSurface faces for a group (or
        # all ungrouped surfaces), attempt Part.makeShell() to stitch them into
        # a single shell, and Part.makeSolid() if the shell closes.  Falls back
        # to individual face objects if stitching fails.
        make_shell = prefs.GetBool("ImportMakeShell", False)

        # Build a map from rhino group index → group name
        grp_names = {}
        for gi in range(len(self.f3dm.Groups)):
            g = self.f3dm.Groups[gi]
            grp_names[gi] = g.Name if g.Name else f"Group_{gi}"

        # Build a map from rhino group index → FC DocumentObjectGroup (created on demand)
        fc_groups = {}

        # --- Diagnostic: survey group contents BEFORE creating FC objects ---
        # Counts NurbsSurface, NurbsCurve, and other geometry per group so we
        # can verify trim-reconstruction candidates (surface + boundary curves).
        curve_types = (r3.NurbsCurve, r3.PolylineCurve, r3.LineCurve,
                       r3.ArcCurve, r3.BezierCurve, r3.PolyCurve)
        grp_survey = {}   # gi → {"surf": int, "curve": int, "other": int}
        ungrouped = {"surf": 0, "curve": 0, "other": 0}
        for i in range(len(self.f3dm.Objects)):
            r3_obj = self.f3dm.Objects[i]
            geo = r3_obj.Geometry
            attrs = r3_obj.Attributes
            if isinstance(geo, r3.NurbsSurface):
                key = "surf"
            elif isinstance(geo, curve_types):
                key = "curve"
            else:
                key = "other"
            if attrs.GroupCount > 0:
                gi = attrs.GetGroupList()[0]
                if gi not in grp_survey:
                    grp_survey[gi] = {"surf": 0, "curve": 0, "other": 0}
                grp_survey[gi][key] += 1
            else:
                ungrouped[key] += 1

        # Also sub-group by attrs.Name within each rhino group to verify
        # per-face surface+curve pairing (e.g. Fillet_f0: 1 surf + 4 curve).
        grp_name_survey = {}  # gi → {obj_name → {"surf": int, "curve": int}}
        for i in range(len(self.f3dm.Objects)):
            r3_obj = self.f3dm.Objects[i]
            geo = r3_obj.Geometry
            attrs = r3_obj.Attributes
            if attrs.GroupCount == 0:
                continue
            gi = attrs.GetGroupList()[0]
            oname = attrs.Name if attrs.Name else "(unnamed)"
            if isinstance(geo, r3.NurbsSurface):
                key = "surf"
            elif isinstance(geo, curve_types):
                key = "curve"
            else:
                continue
            grp_name_survey.setdefault(gi, {}).setdefault(oname, {"surf": 0, "curve": 0})
            grp_name_survey[gi][oname][key] += 1

        FreeCAD.Console.PrintMessage("=== Group survey ===\n")
        for gi, counts in sorted(grp_survey.items()):
            gname = grp_names.get(gi, f"Group_{gi}")
            tag = "  [TRIM CANDIDATE]" if counts["surf"] >= 1 and counts["curve"] >= 1 else ""
            FreeCAD.Console.PrintMessage(
                f"  {gname}: {counts['surf']} surf, {counts['curve']} curve, "
                f"{counts['other']} other{tag}\n"
            )
            # Show per-name breakdown — up to 5 entries to avoid flooding
            name_map = grp_name_survey.get(gi, {})
            entries = sorted(name_map.items())
            for oname, nc in entries[:10]:
                clean = "OK" if nc["surf"] == 1 else f"surf={nc['surf']}"
                FreeCAD.Console.PrintMessage(
                    f"    {oname}: {nc['surf']} surf, {nc['curve']} curve  [{clean}]\n"
                )
            if len(entries) > 10:
                FreeCAD.Console.PrintMessage(f"    ... ({len(entries) - 10} more)\n")
        if any(ungrouped.values()):
            FreeCAD.Console.PrintMessage(
                f"  (ungrouped): {ungrouped['surf']} surf, {ungrouped['curve']} curve, "
                f"{ungrouped['other']} other\n"
            )
        FreeCAD.Console.PrintMessage("====================\n")

        curve_types = (r3.NurbsCurve, r3.PolylineCurve, r3.LineCurve,
                       r3.ArcCurve, r3.BezierCurve, r3.PolyCurve)

        # Collect rhino objects in file order, split into grouped vs ungrouped
        group_seqs = {}   # gi → [r3_obj, …] in insertion order
        ungrouped_list = []
        for i in range(len(self.f3dm.Objects)):
            r3_obj = self.f3dm.Objects[i]
            attrs = r3_obj.Attributes
            if attrs.GroupCount > 0:
                gi = attrs.GetGroupList()[0]
                group_seqs.setdefault(gi, []).append(r3_obj)
            else:
                ungrouped_list.append(r3_obj)

        part = doc.addObject("App::Part", "Part")

        # ── Ungrouped objects ─────────────────────────────────────────────────
        # When make_shell is on, NurbsSurface objects are collected into
        # deferred lists and stitched after the loop; all other geometry
        # (curves, meshes, etc.) is imported as usual.
        ungrouped_surf_shapes = []
        ungrouped_surf_labels = []

        for r3_obj in ungrouped_list:
            geo = r3_obj.Geometry
            obj_name = r3_obj.Attributes.Name

            if make_shell and isinstance(geo, r3.NurbsSurface):
                try:
                    shape = self.create_nurbs_surface(geo).toShape()
                    if not shape.isNull():
                        ungrouped_surf_shapes.append(shape)
                        ungrouped_surf_labels.append(obj_name or 'NurbsSurface')
                except Exception as e:
                    FreeCAD.Console.PrintMessage(
                        f'  Shell: could not build {obj_name or "surface"}: {e}\n')
                continue  # do not add to doc individually

            obj = self.import_geometry(doc, geo)
            if not obj:
                continue
            if obj_name:
                obj.Label = obj_name
            part.addObject(obj)

        # Stitch ungrouped surfaces into a shell/solid (or fall back individually)
        if ungrouped_surf_shapes:
            _add_as_shell(doc, part.addObject, ungrouped_surf_shapes,
                          ungrouped_surf_labels, label='Ungrouped')

        # ── Grouped objects — segment each group into surface+curve runs ──────
        for gi, r3_objs in group_seqs.items():
            gname = grp_names.get(gi, f"Group_{gi}")

            # Segment the group's object sequence into (surf_r3obj, [curve_r3objs])
            # runs.  Any non-surface/non-curve object ends the current run and is
            # imported as a standalone entry.
            runs = []     # [(r3_obj_or_None, [curve_r3objs])]  None → standalone
            cur_surf = None
            cur_curves = []
            standalones = []

            for r3_obj in r3_objs:
                geo = r3_obj.Geometry
                if isinstance(geo, r3.NurbsSurface):
                    if cur_surf is not None:
                        runs.append((cur_surf, cur_curves))
                    cur_surf = r3_obj
                    cur_curves = []
                elif isinstance(geo, curve_types) and cur_surf is not None:
                    cur_curves.append(r3_obj)
                else:
                    if cur_surf is not None:
                        runs.append((cur_surf, cur_curves))
                        cur_surf = None
                        cur_curves = []
                    standalones.append(r3_obj)
            if cur_surf is not None:
                runs.append((cur_surf, cur_curves))

            # Create FC group container
            fc_grp = None
            if create_groups:
                fc_grp = doc.addObject("App::DocumentObjectGroup", gname)
                fc_grp.Label = gname
                part.addObject(fc_grp)

            def _add(obj):
                if fc_grp:
                    fc_grp.addObject(obj)
                else:
                    part.addObject(obj)

            # Process surface+curve runs.
            # When make_shell is on: collect raw surface shapes and stitch after
            # the loop — no trim reconstruction, no individual doc.addObject calls.
            # When make_shell is off: existing trim-reconstruction / individual path.
            trim_ok = trim_fail = 0
            fail_reasons = {}   # reason → count
            self._trim_gap_closed = 0
            group_surf_shapes = []
            group_surf_labels = []

            for surf_r3obj, curve_r3objs in runs:
                surf_attrs = surf_r3obj.Attributes
                surf_label = surf_attrs.Name if surf_attrs.Name else gname

                if make_shell:
                    # Collect surface shape; skip trim curves and doc.addObject
                    try:
                        shape = self.create_nurbs_surface(
                            surf_r3obj.Geometry).toShape()
                        if not shape.isNull():
                            group_surf_shapes.append(shape)
                            group_surf_labels.append(surf_label)
                    except Exception as e:
                        FreeCAD.Console.PrintMessage(
                            f'  Shell: could not build {surf_label}: {e}\n')
                    continue

                # ── existing path ─────────────────────────────────────────────
                obj = None
                if curve_r3objs and _PYTHONOCC:
                    self._trim_fail = ""
                    obj = self._try_trim_reconstruction(
                        doc,
                        surf_r3obj.Geometry,
                        [cr.Geometry for cr in curve_r3objs],
                        surf_label,
                    )
                    if obj:
                        trim_ok += 1
                    else:
                        trim_fail += 1
                        reason = self._trim_fail or "unknown"
                        fail_reasons[reason] = fail_reasons.get(reason, 0) + 1

                if obj is None:
                    # Fall back: import surface + boundary curves as separate objects
                    obj = self.import_geometry(doc, surf_r3obj.Geometry)
                    if obj:
                        obj.Label = surf_label
                        _add(obj)
                    for cr in curve_r3objs:
                        c_obj = self.import_geometry(doc, cr.Geometry)
                        if c_obj:
                            c_obj.Label = "NurbsCurve"
                            _add(c_obj)
                else:
                    obj.Label = surf_label
                    _add(obj)

            if not make_shell and (trim_ok or trim_fail):
                gap_total = getattr(self, '_trim_gap_closed', 0)
                gap_note  = f" ({gap_total} gap-closed)" if gap_total else ""
                FreeCAD.Console.PrintMessage(
                    f"  {gname}: {trim_ok} trimmed{gap_note},"
                    f" {trim_fail} untrimmed + curves\n"
                )
                for reason, count in sorted(fail_reasons.items(),
                                            key=lambda x: -x[1]):
                    FreeCAD.Console.PrintMessage(
                        f"    x{count}: {reason}\n"
                    )

            # Stitch collected surfaces (make_shell path)
            if group_surf_shapes:
                _add_as_shell(doc, _add, group_surf_shapes,
                              group_surf_labels, label=gname)

            # Process standalone objects in this group (non-NurbsSurface)
            for r3_obj in standalones:
                obj = self.import_geometry(doc, r3_obj.Geometry)
                if not obj:
                    continue
                obj_name = r3_obj.Attributes.Name
                if obj_name:
                    obj.Label = obj_name
                _add(obj)

        doc.recompute()

    def import_geometry(self, doc, geo):
        if isinstance(geo, r3.Brep):
            if geo.IsSurface:
                # Untrimmed single-face Brep — use the surface directly.
                obj = doc.addObject("Part::Feature", "Brep Surface")
                obj.Shape = self.create_surface(geo.Surfaces[0]).toShape()
            elif len(geo.Surfaces) == 1:
                # Single-face trimmed Brep (e.g. created by
                # rhino3dm Brep.CreateFromSurface).  Import the underlying
                # surface rather than falling through to edge extraction,
                # which would produce a wireframe rectangle instead of a face.
                obj = doc.addObject("Part::Feature", "NurbsSurface")
                obj.Shape = self.create_surface(geo.Surfaces[0]).toShape()
            else:
                shapes = []
                for i in range(len(geo.Edges)):
                    s = self.create_curve(geo.Edges[i])
                    shapes.append(s.toShape())
                obj = doc.addObject("Part::Feature", "Edges")
                obj.Shape = Part.Compound(shapes)
            return obj

        if isinstance(geo, r3.LineCurve):  # Must be before Curve
            obj = doc.addObject("Part::Line", "LineCurve")
            obj.X1 = geo.PointAtStart.X
            obj.Y1 = geo.PointAtStart.Y
            obj.Z1 = geo.PointAtStart.Z
            obj.X2 = geo.PointAtEnd.X
            obj.Y2 = geo.PointAtEnd.Y
            obj.Z2 = geo.PointAtEnd.Z
            return obj

        if isinstance(geo, r3.NurbsCurve):  # Must be before Curve
            obj = doc.addObject("Part::Feature", "NurbsCurve")
            obj.Shape = self.create_curve(geo).toShape()
            return obj

        if isinstance(geo, r3.ArcCurve):
            obj = doc.addObject("Part::Circle", "Arc")
            obj.Placement.Base = toFCvec(geo.Arc.Center)
            obj.Radius = geo.Radius
            if int(FreeCAD.Version()[3].split()[0]) > 29603:
                obj.Angle1 = startAngle = toFCangle(geo.Arc.Center, geo.PointAtStart)
                obj.Angle2 = startAngle + geo.Arc.AngleDegree
            else:
                obj.Angle0 = startAngle = toFCangle(geo.Arc.Center, geo.PointAtStart)
                obj.Angle1 = startAngle + geo.Arc.AngleDegrees
            return obj

        if isinstance(geo, r3.BezierCurve):
            obj = doc.addObject("Part::Feature", "BezierCurve")
            obj.Shape = self.create_curve(geo).toShape()
            return obj

        if isinstance(geo, r3.PolylineCurve):
            obj = doc.addObject("Part::Polygon", "PolylineCurve")
            pList = []
            for i in range(geo.PointCount):
                p = geo.Point(i)
                pList.append(FreeCAD.Vector(p.X, p.Y, p.Z))
            obj.Nodes = pList
            return obj

        if isinstance(geo, r3.PolyCurve):
            obj = doc.addObject("Part::Feature", "PolyCurve")
            obj.Shape = self.create_curve(geo).toShape()
            return obj

        if isinstance(geo, r3.Ellipse):
            FreeCAD.Console.PrintMessage("  Ellipse \u2014 not yet handled\n")
            return

        if isinstance(geo, r3.Bitmap):
            return  # silently skip bitmaps

        if isinstance(geo, r3.Box):
            FreeCAD.Console.PrintMessage("  Box \u2014 not yet handled\n")
            return

        if isinstance(geo, r3.Circle):
            FreeCAD.Console.PrintMessage("  Circle \u2014 not yet handled\n")
            return

        if isinstance(geo, r3.Cone):
            FreeCAD.Console.PrintMessage("  Cone \u2014 not yet handled\n")
            return

        if isinstance(geo, r3.Curve):
            FreeCAD.Console.PrintMessage("  Generic Curve \u2014 not yet handled\n")
            return

        if isinstance(geo, r3.Cylinder):
            FreeCAD.Console.PrintMessage("  Cylinder \u2014 not yet handled\n")
            return

        if isinstance(geo, r3.Extrusion):
            height = geo.PathStart.Z - geo.PathEnd.Z
            if geo.IsCylinder():
                c = geo.Profile3d(0, 0.0)
                obj = doc.addObject("Part::Cylinder", "Extrusion")
                obj.Height = height
                obj.Radius = c.Radius
                obj.recompute()
                return obj
            for i in range(geo.ProfileCount):
                c = geo.Profile3d(i, 0.0)
                if c.IsPolyline():
                    l = c.ToPolyline()
                    points = [(l.PointAt(j).X, l.PointAt(j).Y, l.PointAt(j).Z)
                              for j in range(l.SegmentCount)]
                    points.append(points[0])
                    obj = doc.addObject("Part::FeaturePython", "Extrusion")
                    obj.Shape = Part.makePolygon(points)
                    return obj
            FreeCAD.Console.PrintMessage(f"  Extrusion h={height:.3f} \u2014 profile not handled\n")
            return

        if isinstance(geo, r3.Mesh):
            FreeCAD.Console.PrintMessage(
                f"  Mesh: quads={geo.Faces.QuadCount} "
                f"triangles={geo.Faces.TriangleCount} \u2014 NURBS not preserved\n"
            )
            return self.create_mesh(doc, geo)

        if isinstance(geo, r3.NurbsSurface):
            obj = doc.addObject("Part::Feature", "NurbsSurface")
            obj.Shape = self.create_nurbs_surface(geo).toShape()
            return obj

        if isinstance(geo, r3.PointCloud):
            FreeCAD.Console.PrintMessage("  PointCloud \u2014 not yet handled\n")
            return

        if isinstance(geo, r3.Surface):
            FreeCAD.Console.PrintMessage("  Surface \u2014 not yet handled\n")
            return

        if isinstance(geo, r3.SubD):
            try:
                import os, sys
                _d = os.path.dirname(os.path.abspath(__file__))
                if _d not in sys.path:
                    sys.path.append(_d)
                import importSubD
                return importSubD.makeSubD(doc, geo, "SubD")
            except Exception as e:
                import traceback
                FreeCAD.Console.PrintError(
                    "  SubD import failed (%s) \u2014 skipped\n" % e)
                FreeCAD.Console.PrintMessage(traceback.format_exc() + "\n")
                return

        FreeCAD.Console.PrintMessage(f"  {type(geo).__name__} \u2014 not yet handled\n")

    def printCurveInfo(self, geo):
        pass  # debug helper — retained but silenced

    def printSubDInfo(self, geo):
        pass  # debug helper — retained but silenced

    ##########################################
    #
    # Create functions return a Part Shape
    #
    ###########################################
    def create_curve(self, edge):
        nc = edge.ToNurbsCurve()
        pts = []
        weights = []
        for u in range(len(nc.Points)):
            p = nc.Points[u]
            pts.append(FreeCAD.Vector(p.X / p.W, p.Y / p.W, p.Z / p.W))
            weights.append(p.W)
        ku, mu = self.getFCKnots(nc.Knots)
        periodic = False
        bs = Part.BSplineCurve()
        bs.buildFromPolesMultsKnots(pts, mu, ku, periodic, nc.Degree, weights)
        if mu[0] < (nc.Degree + 1):
            bs.setPeriodic()
        return bs

    def create_surface(self, surf):
        nu = surf.ToNurbsSurface()
        pts = []
        weights = []
        for u in range(nu.Points.CountU):
            row = []
            wrow = []
            for v in range(nu.Points.CountV):
                p = nu.Points[u, v]
                row.append(FreeCAD.Vector(p.X / p.W, p.Y / p.W, p.Z / p.W))
                wrow.append(p.W)
            pts.append(row)
            weights.append(wrow)
        ku, mu = self.getFCKnots(nu.KnotsU)
        kv, mv = self.getFCKnots(nu.KnotsV)
        bs = Part.BSplineSurface()
        bs.buildFromPolesMultsKnots(pts, mu, mv, ku, kv, False, False,
                                    nu.Degree(0), nu.Degree(1), weights)
        return bs

    def create_nurbs_surface(self, nurbSurf):
        nu = nurbSurf
        pts = []
        weights = []
        for u in range(nu.Points.CountU):
            row = []
            wrow = []
            for v in range(nu.Points.CountV):
                p = nu.Points[u, v]
                row.append(FreeCAD.Vector(p.X / p.W, p.Y / p.W, p.Z / p.W))
                wrow.append(p.W)
            pts.append(row)
            weights.append(wrow)
        ku, mu = self.getFCKnots(nu.KnotsU)
        kv, mv = self.getFCKnots(nu.KnotsV)
        bs = Part.BSplineSurface()
        bs.buildFromPolesMultsKnots(pts, mu, mv, ku, kv, False, False,
                                    nu.Degree(0), nu.Degree(1), weights)
        return bs

    def getFCKnots(self, fknots):
        k = list(fknots)
        mults = []
        knots = list(set(k))
        knots.sort()
        for kn in knots:
            mults.append(k.count(kn))
        mults[0] += 1
        mults[-1] += 1
        return knots, mults

    def create_mesh(self, doc, r3mesh):
        # Return Object Mesh
        import Mesh

        fcMesh = Mesh.Mesh()
        obj = doc.addObject("Mesh::Feature")
        obj.Mesh = Mesh.Mesh()
        r3mesh.Faces.ConvertQuadsToTriangles()
        for m in range(r3mesh.Faces.TriangleCount):
            # print('Face')
            mf = r3mesh.Faces[m]
            # print(type(mf))
            # print(dir(mf))
            fval = ()
            # 3dm files always have 4 vertex values even for triangles
            for r in range(0, 3):
                f = mf[r]
                # print('X : '+str(r3mesh.Vertices[f].X)+ \
                #     ' Y : '+str(r3mesh.Vertices[f].Y)+ \
                #     ' Z : '+str(r3mesh.Vertices[f].Z))
                fval = fval + (
                    float(r3mesh.Vertices[f].X),
                    float(r3mesh.Vertices[f].Y),
                    float(r3mesh.Vertices[f].Z),
                )
            fcMesh.addFacet(*fval)
        obj.Mesh = fcMesh


def process3DM(doc, filename):
    FreeCAD.Console.PrintMessage("Import 3DM file : " + filename + "\n")
    FreeCAD.Console.PrintMessage(f"Import3DM Version {__version__}\n")

    att = [
        "ApplicationName",
        "ApplicationUrl",
        "ApplicationDetails",
        "CreatedBy",
        "LastEditedBy",
        "Revision",
    ]

    fi = File3dm(filename)
    fi.parse_objects(doc)
    FreeCADGui.SendMsgToActiveView("ViewFit")

    # pathName = os.path.dirname(os.path.normpath(filename))

    FreeCAD.Console.PrintMessage("3DM File Imported\n")
