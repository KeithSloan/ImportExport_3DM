# -*- coding: utf-8 -*-
# **************************************************************************
# *   Copyright (c) 2026 Keith Sloan <keith@sloan-home.co.uk>              *
# *   LGPL v2+ (see LICENSE)                                               *
# **************************************************************************
"""
Generate ImportExport_3DM test cases from AstoCAD's Forms workbench.

Must run inside AstoCAD (build 2026.09.01 or later) with ImportExport_3DM
installed.  For every case it:

  * builds the model with the public Forms API,
  * checks the Forms conversion status and B-rep validity,
  * saves <case>.FCStd               (source model, re-editable in AstoCAD),
  * exports untrimmed/<case>.3dm     (ExportTrimmedBreps = False),
  * exports trimmed/<case>.3dm       (ExportTrimmedBreps = True, needs the
                                      trim3dm extension to be built),
  * re-imports each .3dm and records a coarse comparison,
  * writes manifest.json with the stats for all cases and both sets.

The user's ExportTrimmedBreps preference is restored afterwards.

Run from the AstoCAD Python console:

    import runpy, os
    runpy.run_path(os.path.join(App.getUserAppDataDir(),
        "Mod/ImportExport_3DM/testCases/Forms/make_forms_testcases.py"),
        run_name="__main__")

or, to rebuild a subset and/or one export set:

    ns = runpy.run_path(<path>, run_name="forms")
    ns["generate"](["torus", "pipe"])
    ns["generate"](modes=("trimmed",))
"""

__version__ = "0.2.0"

import os
import json
import time
import traceback

import FreeCAD as App
import Part
import Forms
import rhino3dm as r3

from freecad.importExport3DM import export3DM, import3DM

V = App.Vector
HERE = os.path.dirname(os.path.abspath(__file__))
PREF_PATH = "User parameter:BaseApp/Preferences/Mod/ImportExport_3DM"
MODES = {"untrimmed": False, "trimmed": True}


# ===========================================================================
# Helpers
# ===========================================================================
def _cage_edges(obj):
    """Set of control-cage edges as sorted (i, j) index pairs."""
    edges = set()
    for face in obj.ControlFaces:
        ids = [int(x) for x in face.split()]
        for a, b in zip(ids, ids[1:] + ids[:1]):
            edges.add(tuple(sorted((a, b))))
    return edges


def _top_centre_index(obj, cx=0.0, cy=0.0):
    pts = obj.ControlPoints
    zmax = max(p.z for p in pts)
    return min((k for k, p in enumerate(pts) if abs(p.z - zmax) < 1e-6),
               key=lambda k: (pts[k].x - cx) ** 2 + (pts[k].y - cy) ** 2)


def _pull(obj, index, offset):
    pts = list(obj.ControlPoints)
    pts[index] = pts[index] + offset
    obj.ControlPoints = pts


def _base_body(doc, box):
    body = doc.addObject("PartDesign::Body", "Body")
    src = body.newObject("PartDesign::Feature", "Source")
    src.Shape = box
    doc.recompute()
    return body, src


# ===========================================================================
# Case builders: each takes a document, returns the objects to export
# ===========================================================================
def case_box_default(doc):
    """Default Form box: 2x2x2 cage, 24 bicubic patches."""
    return [Forms.create_box(doc)]


def case_box_segments_4(doc):
    """Denser parametric cage: 4 segments per side, 96 patches."""
    o = Forms.create_box(doc)
    o.XSegments = o.YSegments = o.ZSegments = 4
    return [o]


def case_box_edited_pull(doc):
    """Editable cage with the top-centre control point pulled up."""
    o = Forms.create_box(doc)
    doc.recompute()
    Forms.make_editable(o)
    _pull(o, _top_centre_index(o), V(0, 0, 12))
    return [o]


def _box_creased(doc, sharpness):
    o = Forms.create_box(doc)
    doc.recompute()
    Forms.make_editable(o)
    pts = o.ControlPoints
    zmax = max(p.z for p in pts)
    m = max(abs(p.x) for p in pts)

    def on_top_rim(k):
        p = pts[k]
        return abs(p.z - zmax) < 1e-6 and (abs(abs(p.x) - m) < 1e-6
                                           or abs(abs(p.y) - m) < 1e-6)
    edges = [e for e in _cage_edges(o) if all(on_top_rim(k) for k in e)]
    Forms.set_edge_crease(o, edges, sharpness)
    return [o]


def case_box_crease_sharp(doc):
    """Fully sharp crease (10) around the top rim: G0 patch boundaries."""
    return _box_creased(doc, 10)


def case_box_crease_semi(doc):
    """Semi-sharp crease (3) around the top rim."""
    return _box_creased(doc, 3)


def case_box_symmetric_edit(doc):
    """YZ-symmetric box with a mirrored off-centre pull."""
    o = Forms.create_box(doc)
    o.Symmetric = True
    doc.recompute()
    Forms.make_editable(o)
    pts = o.ControlPoints
    i = max(range(len(pts)), key=lambda k: (pts[k].x, pts[k].z, pts[k].y))
    _pull(o, i, V(6, 0, 5))
    return [o]


def case_box_open_top(doc):
    """Top cage faces deleted: open B-spline shell, no solid."""
    o = Forms.create_box(doc)
    doc.recompute()
    Forms.make_editable(o)
    pts = o.ControlPoints
    zmax = max(p.z for p in pts)
    top = [k for k, f in enumerate(o.ControlFaces)
           if all(abs(pts[int(i)].z - zmax) < 1e-6 for i in f.split())]
    Forms.delete_faces(o, top)
    return [o]


def case_box_subdivided_face(doc):
    """Local 2x2 subdivision of one face: T-mesh with T-junctions."""
    o = Forms.create_box(doc)
    doc.recompute()
    Forms.make_editable(o)
    Forms.subdivide_faces(o, [0], 2, 2)
    return [o]


def case_cylinder(doc):
    return [Forms.create_cylinder(doc)]


def case_sphere(doc):
    return [Forms.create_sphere(doc)]


def case_quadball(doc):
    return [Forms.create_quadball(doc)]


def case_torus(doc):
    """Genus-1 closed solid."""
    return [Forms.create_torus(doc)]


def case_tube(doc):
    """Hollow tube: solid with inner and outer skins."""
    return [Forms.create_tube(doc)]


def case_face_open(doc):
    """Default open Form face: single-sided surface, no solid."""
    return [Forms.create_face(doc)]


def case_face_thickened(doc):
    """Open face thickened (3 mm, sharp) into a closed solid."""
    o = Forms.create_face(doc)
    doc.recompute()
    Forms.thicken_surface(o, 3.0, True)
    return [o]


def case_face_from_profile(doc):
    """Form face initialised from a closed polygon: trimmed planar face."""
    pts = [V(0, 0, 0), V(40, 0, 0), V(50, 25, 0), V(20, 40, 0),
           V(-10, 20, 0), V(0, 0, 0)]
    return [Forms.create_face(doc, profile=Part.Face(Part.makePolygon(pts)))]


def case_pipe(doc):
    """Form pipe along a 3D B-spline path."""
    c = Part.BSplineCurve()
    c.interpolate([V(0, 0, 0), V(30, 20, 10), V(60, 0, 30), V(90, 15, 20)])
    path = doc.addObject("Part::Feature", "Path")
    path.Shape = Part.Wire(c.toShape())
    doc.recompute()
    return [Forms.create_pipe(doc, path)]


def case_body_form_surface(doc):
    """PartDesign Form Surface on a box top face, 3x3, centre pulled.
    Mixed planar + B-spline solid."""
    body, src = _base_body(doc, Part.makeBox(30, 20, 10))
    f = Forms.create_surface(body, src, "Face6")
    doc.recompute()
    f.USegments = 3
    f.VSegments = 3
    doc.recompute()
    Forms.make_editable(f)
    _pull(f, _top_centre_index(f, 15, 10), V(0, 0, 6))
    return [body]


def case_body_additive_quadball(doc):
    """Additive Form quadball fused onto a PartDesign base plate."""
    body, src = _base_body(doc, Part.makeBox(40, 40, 10, V(-20, -20, -10)))
    Forms.create_additive_form(body, src, "Quadball", None, App.Placement())
    return [body]


def case_body_subtractive_sphere(doc):
    """Subtractive Form sphere cut from a PartDesign base plate."""
    body, src = _base_body(doc, Part.makeBox(40, 40, 10, V(-20, -20, -10)))
    Forms.create_subtractive_form(body, src, "Sphere", None, App.Placement())
    return [body]


def case_multi_placed(doc):
    """Three Forms in one file, translated and rotated."""
    a = Forms.create_box(doc)
    b = Forms.create_torus(doc)
    b.Placement = App.Placement(V(60, 0, 0), App.Rotation(V(1, 0, 0), 90))
    c = Forms.create_quadball(doc)
    c.Placement = App.Placement(V(0, 60, 15), App.Rotation(V(1, 1, 1), 40))
    return [a, b, c]


CASES = [
    ("box_default", case_box_default),
    ("box_segments_4", case_box_segments_4),
    ("box_edited_pull", case_box_edited_pull),
    ("box_crease_sharp", case_box_crease_sharp),
    ("box_crease_semi", case_box_crease_semi),
    ("box_symmetric_edit", case_box_symmetric_edit),
    ("box_open_top", case_box_open_top),
    ("box_subdivided_face", case_box_subdivided_face),
    ("cylinder", case_cylinder),
    ("sphere", case_sphere),
    ("quadball", case_quadball),
    ("torus", case_torus),
    ("tube", case_tube),
    ("face_open", case_face_open),
    ("face_thickened", case_face_thickened),
    ("face_from_profile", case_face_from_profile),
    ("pipe", case_pipe),
    ("body_form_surface", case_body_form_surface),
    ("body_additive_quadball", case_body_additive_quadball),
    ("body_subtractive_sphere", case_body_subtractive_sphere),
    ("multi_placed", case_multi_placed),
]


# ===========================================================================
# Stats
# ===========================================================================
def _shape_stats(shape):
    return dict(
        solids=len(shape.Solids), shells=len(shape.Shells),
        faces=len(shape.Faces), valid=shape.isValid(),
        closed=all(s.isClosed() for s in shape.Shells) if shape.Shells
        else False,
        volume=round(shape.Volume, 4) if shape.Solids else None,
        area=round(shape.Area, 4),
        surfaces=sorted({type(f.Surface).__name__ for f in shape.Faces}))


def _forms_stats(obj):
    st = dict(label=obj.Label, type_id=obj.TypeId)
    for p in ("FormType", "ConversionStatus", "CageMode"):
        if hasattr(obj, p):
            st[p] = getattr(obj, p)
    if hasattr(obj, "MaximumDeviation"):
        st["MaximumDeviation"] = float(obj.MaximumDeviation)
    if hasattr(obj, "ControlPoints"):
        st["control_points"] = len(obj.ControlPoints)
        st["control_faces"] = len(obj.ControlFaces)
    return st


def _3dm_stats(path):
    f = r3.File3dm.Read(path)
    types = {}
    for o in f.Objects:
        t = type(o.Geometry).__name__
        types[t] = types.get(t, 0) + 1
    return dict(bytes=os.path.getsize(path), objects=len(f.Objects),
                types=types, groups=[g.Name for g in f.Groups])


def _reimport_stats(path):
    doc = App.newDocument("Forms_Reimport")
    try:
        import3DM.insert(path, doc.Name)
        doc.recompute()
        faces = []
        for o in doc.Objects:
            if o.TypeId.startswith("Part::") and not getattr(o, "Group", None):
                sh = getattr(o, "Shape", None)
                if sh is not None and not sh.isNull():
                    faces += sh.Faces
        return dict(faces=len(faces),
                    area=round(sum(f.Area for f in faces), 4),
                    all_valid=all(f.isValid() for f in faces))
    finally:
        App.closeDocument(doc.Name)


# ===========================================================================
# Generator
# ===========================================================================
def _export_set(objs, name, mode, out_dir):
    """Export *objs* to <out_dir>/<mode>/<name>.3dm and collect stats."""
    params = App.ParamGet(PREF_PATH)
    params.SetBool("ExportTrimmedBreps", MODES[mode])
    sub = os.path.join(out_dir, mode)
    os.makedirs(sub, exist_ok=True)
    dm = os.path.join(sub, name + ".3dm")
    if os.path.exists(dm):
        os.remove(dm)
    export3DM.export(objs, dm)
    if not os.path.exists(dm):
        return dict(status="error", error="export wrote no file")
    entry = dict(status="ok", file=os.path.relpath(dm, out_dir),
                 **{"3dm": _3dm_stats(dm)})
    entry["reimport"] = _reimport_stats(dm)
    src_area = sum(o.Shape.Area for o in objs)
    entry["reimport"]["area_rel_err"] = round(
        abs(entry["reimport"]["area"] - src_area) / max(src_area, 1e-12), 6)
    return entry


def generate(names=None, out_dir=HERE, modes=("untrimmed", "trimmed")):
    """Build, save and export the cases (all, or those in *names*) for each
    export set in *modes*."""
    for mode in modes:
        if mode not in MODES:
            raise ValueError("Unknown mode %r (use %s)" % (mode, list(MODES)))
    if "trimmed" in modes and export3DM._import_trim3dm() is None:
        raise RuntimeError("trimmed set requested but the trim3dm extension "
                           "is not importable - build it first "
                           "(ImportExport_3DM/trim3dm/build.sh)")
    os.makedirs(out_dir, exist_ok=True)
    manifest_path = os.path.join(out_dir, "manifest.json")
    manifest = {}
    if os.path.exists(manifest_path):
        with open(manifest_path) as fh:
            manifest = json.load(fh).get("cases", {})

    params = App.ParamGet(PREF_PATH)
    had_pref = "ExportTrimmedBreps" in params.GetBools()
    old_pref = params.GetBool("ExportTrimmedBreps", True)
    try:
        for name, builder in CASES:
            if names and name not in names:
                continue
            entry = manifest.get(name, {})
            if not isinstance(entry.get("exports"), dict):
                entry = {}               # older manifest layout: start afresh
            entry["description"] = (builder.__doc__ or "").strip()
            entry.setdefault("exports", {})
            doc = App.newDocument("Forms_" + name)
            try:
                objs = builder(doc)
                doc.recompute()
                entry["objects"] = []
                for o in objs:
                    st = _forms_stats(o)
                    st["shape"] = _shape_stats(o.Shape)
                    # Forms feature inside a Body: report the Form itself too
                    if o.TypeId == "PartDesign::Body":
                        st["forms"] = [_forms_stats(x) for x in o.Group
                                       if hasattr(x, "FormType")]
                    entry["objects"].append(st)
                doc.saveAs(os.path.join(out_dir, name + ".FCStd"))
                entry["source"] = name + ".FCStd"
                for mode in modes:
                    try:
                        entry["exports"][mode] = _export_set(objs, name,
                                                             mode, out_dir)
                    except Exception as e:
                        entry["exports"][mode] = dict(
                            status="error", error=repr(e),
                            trace=traceback.format_exc())
                bad = [m for m in modes
                       if entry["exports"][m]["status"] != "ok"]
                entry["status"] = "error" if bad else "ok"
                entry.pop("error", None)
                entry.pop("trace", None)
            except Exception as e:
                entry["status"] = "error"
                entry["error"] = repr(e)
                entry["trace"] = traceback.format_exc()
            finally:
                App.closeDocument(doc.Name)
            manifest[name] = entry
            App.Console.PrintMessage("Forms test case %-26s %s\n"
                                     % (name, entry["status"]))
    finally:
        if had_pref:
            params.SetBool("ExportTrimmedBreps", old_pref)
        else:
            params.RemBool("ExportTrimmedBreps")

    meta = dict(generated=time.strftime("%Y-%m-%d %H:%M:%S"),
                astocad=App.Version()[:4], generator=__version__,
                export3DM=export3DM.__version__,
                import3DM=import3DM.__version__,
                rhino3dm=r3.__version__,
                layout={"source": "<case>.FCStd",
                        "untrimmed": "untrimmed/<case>.3dm",
                        "trimmed": "trimmed/<case>.3dm"})
    with open(manifest_path, "w") as fh:
        json.dump(dict(meta=meta, cases=manifest), fh, indent=1)
    return manifest


if __name__ == "__main__":
    generate()
