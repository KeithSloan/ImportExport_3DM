# **************************************************************************
# *   Copyright (c) 2026 Keith Sloan <keith@sloan-home.co.uk>               *
# *                                                                         *
# *   Trimmed-Brep importer for .3dm.                                        *
# *   Reads trimmed Breps via the `trim3dm` extension (OpenNURBS) and        *
# *   rebuilds them as trimmed Part::Face objects with pythonOCC.            *
# *   Registered as a second "3DM trimmed" import type alongside import3DM;  *
# *   choose it from the format dropdown in File > Open / Import.            *
# **************************************************************************
__version__ = "0.1.0"

import os
import sys
import tempfile
import FreeCAD
import Part

FreeCAD.Console.PrintMessage(f"import_trim_3DM {__version__}\n")


# --- locate the trim3dm extension -----------------------------------------
def _import_trim3dm():
    try:
        import trim3dm
        return trim3dm
    except ImportError:
        pass
    here = os.path.dirname(os.path.abspath(__file__))
    # repo_root/trim3dm (build.sh drops the .so there), and the module dir
    for cand in (os.path.join(here, "..", "..", "trim3dm"), here):
        cand = os.path.abspath(cand)
        if cand not in sys.path and os.path.isdir(cand):
            sys.path.insert(0, cand)
    import trim3dm
    return trim3dm


# --- pythonOCC builders ----------------------------------------------------
def _occ_knots_mults(knots):
    """OpenNURBS knot list (n+deg-1) -> OCC (unique knots, mults)."""
    from OCC.Core.TColStd import TColStd_Array1OfReal, TColStd_Array1OfInteger
    full = [knots[0]] + list(knots) + [knots[-1]]
    uk, mu = [], []
    eps = 1e-10
    for k in full:
        if uk and abs(k - uk[-1]) < eps:
            mu[-1] += 1
        else:
            uk.append(k)
            mu.append(1)
    ak = TColStd_Array1OfReal(1, len(uk))
    am = TColStd_Array1OfInteger(1, len(uk))
    for i, (k, m) in enumerate(zip(uk, mu)):
        ak.SetValue(i + 1, k)
        am.SetValue(i + 1, m)
    return ak, am


def _surface(sd):
    from OCC.Core.Geom import Geom_BSplineSurface
    from OCC.Core.TColgp import TColgp_Array2OfPnt
    from OCC.Core.TColStd import TColStd_Array2OfReal
    from OCC.Core.gp import gp_Pnt
    cv = sd["cv"]
    nu, nv = len(cv), len(cv[0])
    poles = TColgp_Array2OfPnt(1, nu, 1, nv)
    wts = TColStd_Array2OfReal(1, nu, 1, nv)
    for i in range(nu):
        for j in range(nv):
            x, y, z, w = cv[i][j]
            poles.SetValue(i + 1, j + 1, gp_Pnt(x / w, y / w, z / w))
            wts.SetValue(i + 1, j + 1, w)
    uk, um = _occ_knots_mults(sd["knots_u"])
    vk, vm = _occ_knots_mults(sd["knots_v"])
    return Geom_BSplineSurface(poles, wts, uk, vk, um, vm,
                               sd["degree_u"], sd["degree_v"], False, False)


def _pcurve(cd):
    from OCC.Core.Geom2d import Geom2d_BSplineCurve
    from OCC.Core.TColgp import TColgp_Array1OfPnt2d
    from OCC.Core.TColStd import TColStd_Array1OfReal
    from OCC.Core.gp import gp_Pnt2d
    cv = cd["cv"]
    n = len(cv)
    poles = TColgp_Array1OfPnt2d(1, n)
    wts = TColStd_Array1OfReal(1, n)
    for i in range(n):
        u, v, w = cv[i]
        poles.SetValue(i + 1, gp_Pnt2d(u / w, v / w))
        wts.SetValue(i + 1, w)
    k, m = _occ_knots_mults(cd["knots"])
    return Geom2d_BSplineCurve(poles, wts, k, m, cd["degree"], False)


def _trimmed_face_shape(fd):
    """Build a FreeCAD Part shape (trimmed face) from a trim3dm face dict."""
    from OCC.Core.BRepBuilderAPI import (BRepBuilderAPI_MakeEdge,
                                         BRepBuilderAPI_MakeWire,
                                         BRepBuilderAPI_MakeFace)
    from OCC.Core.BRepLib import breplib
    from OCC.Core.BRepTools import breptools

    surf = _surface(fd["surface"])
    wires = []
    for loop in fd["loops"]:
        mw = BRepBuilderAPI_MakeWire()
        for e in loop:
            me = BRepBuilderAPI_MakeEdge(_pcurve(e["c2"]), surf)
            if me.IsDone():
                mw.Add(me.Edge())
        if mw.IsDone():
            wires.append(mw.Wire())
    if not wires:
        return None
    mf = BRepBuilderAPI_MakeFace(surf, wires[0], True)
    if not mf.IsDone():
        return None
    face = mf.Face()
    for w in wires[1:]:
        mf2 = BRepBuilderAPI_MakeFace(face)
        mf2.Add(w)
        if mf2.IsDone():
            face = mf2.Face()
    breplib.BuildCurves3d(face)

    # OCCT can flag a freshly-built trimmed face as UnorientableShape even when
    # its wires/edges are all clean (the surface normal vs wire winding leaves
    # the "inside" ambiguous). ShapeFix_Face resolves the orientation.
    try:
        from OCC.Core.ShapeFix import ShapeFix_Face
        sff = ShapeFix_Face(face)
        sff.Perform()
        face = sff.Face()
    except Exception:
        pass

    tf = tempfile.NamedTemporaryFile(suffix=".brep", delete=False)
    tf.close()
    breptools.Write(face, tf.name)
    shp = Part.Shape()
    shp.importBrep(tf.name)
    os.unlink(tf.name)

    # repair if needed (some faces come back invalid until fixed)
    if not shp.isNull() and not shp.isValid():
        try:
            fixed = shp.copy()
            fixed.fix(1e-6, 1e-6, 1e-6)
            if fixed.isValid():
                shp = fixed
        except Exception:
            pass
    return shp


def _read_into(doc, filename):
    trim3dm = _import_trim3dm()
    faces = trim3dm.read_trimmed_breps(filename)
    FreeCAD.Console.PrintMessage(
        f"import_trim_3DM: {len(faces)} trimmed Brep(s) in {filename}\n")
    ok = invalid = fail = 0
    for fd in faces:
        name = fd.get("name") or "TrimFace"
        try:
            shp = _trimmed_face_shape(fd)
            if shp is None or shp.isNull():
                fail += 1
                FreeCAD.Console.PrintMessage(f"  {name}: no shape\n")
                continue
            obj = doc.addObject("Part::Feature", name)
            obj.Shape = shp
            obj.Label = name
            if not shp.isValid():
                invalid += 1
        except Exception as e:
            fail += 1
            FreeCAD.Console.PrintMessage(f"  {name}: {e}\n")
    doc.recompute()
    FreeCAD.Console.PrintMessage(
        f"import_trim_3DM: imported {len(faces) - fail} face(s)"
        f" ({invalid} invalid, {fail} failed)\n")


# --- FreeCAD import handler entry points -----------------------------------
def open(filename):
    "called when FreeCAD opens a .3dm with this import type"
    docname = os.path.splitext(os.path.basename(filename))[0]
    doc = FreeCAD.newDocument(docname)
    _read_into(doc, filename)
    return doc


def insert(filename, docname):
    "called when FreeCAD imports a .3dm with this import type"
    try:
        doc = FreeCAD.getDocument(docname)
    except NameError:
        doc = FreeCAD.newDocument(docname)
    _read_into(doc, filename)
