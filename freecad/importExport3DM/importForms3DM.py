# -*- coding: utf-8 -*-
# **************************************************************************
# *   Copyright (c) 2026 Keith Sloan <keith@sloan-home.co.uk>              *
# *   LGPL v2+ (see LICENSE)                                               *
# **************************************************************************
"""
PROTOTYPE - import Rhino SubD objects from a .3dm as editable AstoCAD Forms.

Instead of a Part shape (exact limit patches + display cage, as importSubD
does), each Rhino SubD becomes a native AstoCAD ``Forms::Form``: its control
net becomes the Form's control cage, so the result is editable with the
Forms tools (pull, crease, subdivide, symmetry, thicken ...).

Mapping  Rhino SubD (rhino3dm)          ->  Forms::Form
         -------------------------------    ---------------------------------
         SubDVertex.ControlNetPoint      ->  ControlPoints (file units -> mm)
         SubDFace vertex loop (n-gon)    ->  ControlFaces "i j k ..."
         SubDEdge.IsHardCrease           ->  EdgeSharpness "i j 10"
         SubDEdge.EndSharpness (semi)    ->  EdgeSharpness "i j s"
         SubDVertex Tag == Corner        ->  VertexSharpness 10
         SubDVertex.VertexSharpness      ->  VertexSharpness
         cage symmetric about origin     ->  Symmetric / SymmetryPlane

Both Rhino SubD and Forms are Catmull-Clark with OpenSubdiv-style creases,
so the Form's limit surface reproduces the Rhino surface.  Each imported
Form records ``ImportDeviation``: the max distance from Rhino's own limit
points (SubDVertex.SurfacePoint) to the Form's B-rep.

Forms converts the limit surface by patch sampling; dense or irregular cages
can exceed its sampling limit.  The importer then retries with a lower
``MaxRefinement`` (3 -> 2 -> 1).

Coordinates are scaled from the file's unit system to millimetres when the
``ImportScaleToMillimetres`` preference is on (default), shared with
import3DM via units3DM.  Forms' conversion tolerance (BRepTolerance) is in mm,
so leaving a non-mm file unscaled changes the effective tolerance.

Requires AstoCAD 2026.09.01 or later (the ``Forms`` module).  Before
importing, the Forms API this importer relies on is verified once per session
(``check_forms_api``) so an incompatible AstoCAD gives a clear message rather
than a generic error.  Non-SubD objects are skipped and reported; use
import3DM for those.

Usage (AstoCAD Python console):

    from freecad.importExport3DM import importForms3DM
    created, skipped = importForms3DM.import_file("/path/model.3dm")

    # or the FreeCAD import-hook style entry points:
    importForms3DM.insert("/path/model.3dm", App.ActiveDocument.Name)
    importForms3DM.open("/path/model.3dm")

Not yet registered with FreeCAD.addImportType - prototype only.
"""

__version__ = "0.3.0"

import os
import time

import FreeCAD as App
import Part
import rhino3dm as r3

try:
    from freecad.importExport3DM import units3DM
except ImportError:
    import units3DM

try:
    import Forms
    HAVE_FORMS = True
except ImportError:
    Forms = None
    HAVE_FORMS = False

CREASE = 10.0              # OpenSubdiv / Forms "infinitely sharp"
REFINEMENT_FALLBACK = (3, 2, 1)
SAMPLING_LIMIT_MSG = "sampling limit"
VALIDATION_SAMPLE_MAX = 2000   # limit points checked per object


class FormsImportError(RuntimeError):
    """A SubD could not be converted to an editable Form."""


def _msg(text):
    App.Console.PrintMessage("importForms3DM: %s\n" % text)


def _warn(text):
    App.Console.PrintWarning("importForms3DM: %s\n" % text)


# Forms API this importer relies on (AstoCAD 2026.09.01)
REQUIRED_FORM_PROPERTIES = (
    "ControlPoints", "ControlFaces", "VertexSharpness", "EdgeSharpness",
    "MaxRefinement", "BRepTolerance", "ConversionStatus", "Symmetric",
    "SymmetryPlane",
)
_api_status = None      # cached: (ok, message)


def check_forms_api():
    """Verify the Forms API once per session.  Returns (ok, message).

    Checks that ``Forms.create_form`` exists and that a throwaway Form, made
    in a hidden temporary document, has every property the importer uses.
    """
    global _api_status
    if _api_status is not None:
        return _api_status
    if not HAVE_FORMS:
        _api_status = (False, "the Forms module is not available "
                              "(AstoCAD 2026.09.01 or later required)")
        return _api_status
    if not callable(getattr(Forms, "create_form", None)):
        _api_status = (False, "Forms API changed: Forms.create_form() not "
                              "found - importForms3DM needs updating for "
                              "this AstoCAD version")
        return _api_status
    doc = None
    try:
        try:
            doc = App.newDocument("importForms3DM_APIcheck", hidden=True,
                                  temp=True)
        except TypeError:
            doc = App.newDocument("importForms3DM_APIcheck")
        obj = Forms.create_form(doc, "APIcheck")
        missing = [p for p in REQUIRED_FORM_PROPERTIES
                   if p not in obj.PropertiesList]
        if missing:
            _api_status = (False, "Forms API changed: Form object lacks %s - "
                                  "importForms3DM needs updating for this "
                                  "AstoCAD version" % ", ".join(missing))
        else:
            _api_status = (True, "Forms API OK")
    except Exception as e:
        _api_status = (False, "Forms API check failed (%s) - importForms3DM "
                              "may need updating for this AstoCAD version"
                       % e)
    finally:
        if doc is not None:
            try:
                App.closeDocument(doc.Name)
            except Exception:
                pass
    return _api_status


def available():
    """True when running in AstoCAD with a compatible Forms module."""
    return check_forms_api()[0]


def _require_forms():
    ok, message = check_forms_api()
    if not ok:
        raise FormsImportError(message)


# ===========================================================================
# Extraction
# ===========================================================================
def extract_cage(sd, scale=1.0):
    """Control cage + crease data from a rhino3dm SubD.

    Iterates the collections (indexing sd.Vertices[i] returns a dangling
    temporary - see importSubD.extract_subd).

    Returns dict(points, limit, faces, vertex_sharpness, edge_sharpness,
    notes) with points/limit as App.Vector in mm, faces as index tuples and
    edge_sharpness as {(i, j): s} with i < j.
    """
    remap = {}
    points, limit, vsharp = [], [], []
    notes = []
    for v in sd.Vertices:
        remap[v.Index] = len(points)
        p = v.ControlNetPoint
        points.append(App.Vector(p.X, p.Y, p.Z) * scale)
        s = v.SurfacePoint
        limit.append(App.Vector(s.X, s.Y, s.Z) * scale)
        if str(v.Tag).endswith("Corner"):
            vsharp.append(CREASE)
        else:
            try:
                vsharp.append(max(0.0, float(v.VertexSharpness)))
            except Exception:
                vsharp.append(0.0)

    faces = []
    for fc in sd.Faces:
        faces.append(tuple(remap[fc.Vertex(k).Index]
                           for k in range(fc.VertexCount)))

    esharp = {}
    varying = 0
    for e in sd.Edges:
        a = remap[e.Vertex(0).Index]
        b = remap[e.Vertex(1).Index]
        key = (a, b) if a < b else (b, a)
        if e.IsHardCrease:
            s = CREASE
        else:
            try:
                s0, s1 = float(e.EndSharpness(0)), float(e.EndSharpness(1))
            except Exception:
                s0 = s1 = 0.0
            if abs(s0 - s1) > 1e-9:
                varying += 1
            # Forms / OpenSubdiv: constant sharpness per edge
            s = max(s0, s1)
        if s > 0.0:
            esharp[key] = min(s, CREASE)
    if varying:
        notes.append("%d edge(s) with varying sharpness approximated by "
                     "their maximum end sharpness" % varying)
    ngons = sum(1 for f in faces if len(f) != 4)
    if ngons:
        notes.append("%d non-quad face(s) - irregular patches convert "
                     "more slowly" % ngons)
    return dict(points=points, limit=limit, faces=faces,
                vertex_sharpness=vsharp, edge_sharpness=esharp, notes=notes)


def validate_cage(points, faces):
    """Return a list of problems that would stop Forms building the cage."""
    problems = []
    if not points or not faces:
        return ["empty control cage"]
    edge_count = {}
    used = set()
    for f in faces:
        if len(f) < 3 or len(set(f)) != len(f):
            problems.append("degenerate face %s" % (f,))
            continue
        if min(f) < 0 or max(f) >= len(points):
            problems.append("face index out of range %s" % (f,))
            continue
        used.update(f)
        for k, a in enumerate(f):
            b = f[(k + 1) % len(f)]
            key = (a, b) if a < b else (b, a)
            edge_count[key] = edge_count.get(key, 0) + 1
    if len(used) != len(points):
        problems.append("%d loose vertex(es)" % (len(points) - len(used)))
    nonmanifold = sum(1 for c in edge_count.values() if c > 2)
    if nonmanifold:
        problems.append("%d non-manifold edge(s)" % nonmanifold)
    boundary = {}
    for (a, b), c in edge_count.items():
        if c == 1:
            boundary.setdefault(a, set()).add(b)
            boundary.setdefault(b, set()).add(a)
    branched = sum(1 for n in boundary.values() if len(n) != 2)
    if branched:
        problems.append("%d branched boundary vertex(es)" % branched)
    return problems


def _symmetry_plane(points, faces):
    """Origin symmetry plane name, using Forms' own Blender-import test."""
    try:
        from Forms.blend_import import _origin_symmetry
    except Exception:
        return None
    verts = [(p.x, p.y, p.z) for p in points]
    for axis, plane in ((0, "YZ"), (1, "XZ"), (2, "XY")):
        try:
            if _origin_symmetry(verts, faces, axis):
                return plane
        except Exception:
            return None
    return None


# ===========================================================================
# Form creation
# ===========================================================================
def _add_import_property(obj, name, kind, doc, value):
    if name not in obj.PropertiesList:
        obj.addProperty(kind, name, "Import", doc)
        obj.setEditorMode(name, 1)
    setattr(obj, name, value)


def _limit_deviation(limit, shape):
    """Max distance of Rhino limit points to the Form shape."""
    if not limit or shape.isNull():
        return None
    step = max(1, len(limit) // VALIDATION_SAMPLE_MAX)
    worst = 0.0
    for p in limit[::step]:
        worst = max(worst, Part.Vertex(p).distToShape(shape)[0])
    return worst


def create_form(doc, name, cage, max_refinement=None, tolerance=None,
                detect_symmetry=True, validate=True, source=None):
    """Create a Forms::Form from an extracted cage.  Raises FormsImportError.

    max_refinement: start value (default: Forms' own, then fall back).
    tolerance:      BRepTolerance in mm (default: Forms' own).
    source:         dict(file=, object=, layer=) recorded on the object.
    """
    _require_forms()
    problems = validate_cage(cage["points"], cage["faces"])
    if problems:
        raise FormsImportError("; ".join(problems))

    obj = Forms.create_form(doc, name)
    try:
        obj.Label = name
        obj.ControlPoints = cage["points"]
        obj.ControlFaces = [" ".join(str(i) for i in f)
                            for f in cage["faces"]]
        obj.VertexSharpness = cage["vertex_sharpness"]
        obj.EdgeSharpness = ["%d %d %.12g" % (a, b, s) for (a, b), s
                             in sorted(cage["edge_sharpness"].items())]
        if tolerance is not None:
            obj.BRepTolerance = tolerance
        if detect_symmetry:
            plane = _symmetry_plane(cage["points"], cage["faces"])
            if plane:
                obj.SymmetryPlane = plane
                obj.Symmetric = True

        levels = list(REFINEMENT_FALLBACK)
        if max_refinement is not None:
            levels = [max_refinement] + [r for r in levels
                                         if r < max_refinement]
        status = ""
        for level in levels:
            obj.MaxRefinement = level
            t0 = time.time()
            doc.recompute()
            status = str(getattr(obj, "ConversionStatus", ""))
            if not obj.Shape.isNull():
                break
            if SAMPLING_LIMIT_MSG not in status:
                break
            _msg("%s: %s at MaxRefinement %d (%.1fs) - retrying lower"
                 % (name, status, level, time.time() - t0))
        if obj.Shape.isNull():
            raise FormsImportError("Forms could not convert the cage"
                                   + (": " + status if status else ""))

        if source:
            _add_import_property(obj, "SourceFile", "App::PropertyFile",
                                 "Source .3dm file", source.get("file", ""))
            _add_import_property(obj, "SourceObject", "App::PropertyString",
                                 "Rhino object id / name",
                                 source.get("object", ""))
            _add_import_property(obj, "SourceLayer", "App::PropertyString",
                                 "Rhino layer", source.get("layer", ""))
        if validate:
            dev = _limit_deviation(cage["limit"], obj.Shape)
            if dev is not None:
                _add_import_property(
                    obj, "ImportDeviation", "App::PropertyLength",
                    "Max distance from Rhino SubD limit points to the "
                    "Form surface", dev)
        if App.GuiUp:
            try:
                obj.ViewObject.ShowControlCage = True
            except Exception:
                pass
        return obj
    except Exception:
        if obj.Document is doc:
            doc.removeObject(obj.Name)
        raise


# ===========================================================================
# File import
# ===========================================================================
def _layer_name(model, index):
    try:
        return model.Layers[index].FullPath
    except Exception:
        try:
            return model.Layers[index].Name
        except Exception:
            return ""


def import_file(filename, doc=None, group=True, max_refinement=None,
                tolerance=None, validate=True, detect_symmetry=True):
    """Import every SubD in *filename* into *doc* as editable Forms.

    Returns (created, skipped): created is a list of Form objects, skipped
    a list of (object description, reason).
    """
    _require_forms()
    model = r3.File3dm.Read(filename)
    if model is None:
        raise FormsImportError("rhino3dm could not read %s" % filename)
    if doc is None:
        doc = App.ActiveDocument or App.newDocument()
    scale = units3DM.import_scale(model)
    units3DM.report(model, scale)
    if (scale == 1.0
            and units3DM.UNIT_TO_MM.get(units3DM.unit_name(model), 1.0) != 1.0):
        _warn("file is in %s and not scaled - Forms BRepTolerance is in mm"
              % units3DM.unit_name(model))
    stem = os.path.splitext(os.path.basename(filename))[0]

    created, skipped = [], []
    others = {}
    container = None
    count = 0
    for robj in model.Objects:
        geo = robj.Geometry
        kind = type(geo).__name__
        if kind != "SubD":
            others[kind] = others.get(kind, 0) + 1
            continue
        count += 1
        attrs = robj.Attributes
        name = attrs.Name or "%s_SubD%03d" % (stem, count)
        desc = "%s (%s)" % (name, attrs.Id)
        t0 = time.time()
        try:
            cage = extract_cage(geo, scale)
            for note in cage["notes"]:
                _msg("%s: %s" % (name, note))
            obj = create_form(
                doc, name, cage, max_refinement=max_refinement,
                tolerance=tolerance, detect_symmetry=detect_symmetry,
                validate=validate,
                source=dict(file=os.path.abspath(filename),
                            object=str(attrs.Id),
                            layer=_layer_name(model, attrs.LayerIndex)))
        except Exception as e:
            skipped.append((desc, str(e)))
            _warn("%s skipped: %s" % (desc, e))
            continue
        if group:
            if container is None:
                container = doc.addObject("App::DocumentObjectGroup", stem)
            container.addObject(obj)
        created.append(obj)
        dev = getattr(obj, "ImportDeviation", None)
        _msg("%s -> %s, %s, %d faces, MaxRefinement %d, deviation %s, "
             "%.1fs" % (desc, obj.Name, obj.ConversionStatus,
                        len(obj.Shape.Faces), obj.MaxRefinement,
                        dev if dev is not None else "n/a",
                        time.time() - t0))
    for kind, n in sorted(others.items()):
        skipped.append(("%d %s object(s)" % (n, kind),
                        "not a SubD - use import3DM"))
    if count == 0:
        _warn("%s contains no SubD objects" % filename)
    doc.recompute()
    return created, skipped


# ---------------------------------------------------------------------------
# FreeCAD import-hook style entry points
# ---------------------------------------------------------------------------
def open(filename):
    """Create a new document and import the SubDs of *filename* as Forms."""
    doc = App.newDocument(os.path.splitext(os.path.basename(filename))[0])
    import_file(filename, doc)
    return doc


def insert(filename, docname):
    """Import the SubDs of *filename* as Forms into document *docname*."""
    try:
        doc = App.getDocument(docname)
    except NameError:
        doc = App.newDocument(docname)
    import_file(filename, doc)
