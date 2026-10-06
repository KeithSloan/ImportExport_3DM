# -*- coding: utf-8 -*-
# **************************************************************************
# *   Copyright (c) 2026 Keith Sloan <keith@sloan-home.co.uk>              *
# *   LGPL v2+ (see LICENSE)                                               *
# **************************************************************************
"""
Model-unit scaling shared by the ImportExport_3DM importers.

FreeCAD works in millimetres; a .3dm file records its own model unit system
(``File3dm.Settings.ModelUnitSystem``).  With the preference
``ImportScaleToMillimetres`` on (the default), importers scale geometry from
the file's units to millimetres:

* ``import3DM``      - imports in file units, then ``scale_objects`` scales
                       every object the import created (one place covers all
                       geometry paths, including trim3dm, which reads the
                       file directly).
* ``importForms3DM`` - scales the control cage while extracting it.

A unit system of "None" (unitless, common in V1 files) is treated as
millimetres, i.e. no scaling.
"""

__version__ = "0.1.0"

import FreeCAD as App

PREFS_NS = "User parameter:BaseApp/Preferences/Mod/ImportExport_3DM"
PREF_SCALE = "ImportScaleToMillimetres"

# rhino3dm UnitSystem name -> millimetres
UNIT_TO_MM = {
    "None": 1.0, "Millimeters": 1.0, "Centimeters": 10.0,
    "Decimeters": 100.0, "Meters": 1000.0, "Kilometers": 1.0e6,
    "Microns": 1.0e-3, "Nanometers": 1.0e-6, "Angstroms": 1.0e-7,
    "Microinches": 25.4e-6, "Mils": 25.4e-3, "Inches": 25.4,
    "Feet": 304.8, "Yards": 914.4, "Miles": 1609344.0,
    "Dekameters": 1.0e4, "Hectometers": 1.0e5, "Megameters": 1.0e9,
    "Gigameters": 1.0e12, "AstronomicalUnits": 1.495978707e14,
    "LightYears": 9.4607304725808e18, "Parsecs": 3.0856775814913673e19,
    "NauticalMiles": 1852000.0, "PrinterPoints": 25.4 / 72.0,
    "PrinterPicas": 25.4 / 6.0,
}

_PARAMETRIC_LENGTHS = {
    "Part::Line": ("X1", "Y1", "Z1", "X2", "Y2", "Z2"),
    "Part::Circle": ("Radius",),
}


def scaling_enabled():
    """User preference: scale imported geometry to millimetres."""
    try:
        return App.ParamGet(PREFS_NS).GetBool(PREF_SCALE, True)
    except Exception:
        return True


def unit_name(model):
    """Model unit system name of a rhino3dm File3dm ("Inches", ...)."""
    try:
        return str(model.Settings.ModelUnitSystem).split(".")[-1]
    except Exception:
        return "None"


def unit_scale(model):
    """Factor from the model's unit system to millimetres (1.0 if unknown)."""
    name = unit_name(model)
    scale = UNIT_TO_MM.get(name)
    if scale is None:
        App.Console.PrintWarning(
            "ImportExport_3DM: unknown unit system %r - not scaled\n" % name)
        return 1.0
    return scale


def import_scale(model):
    """Scale to apply on import: unit_scale() if enabled, else 1.0."""
    return unit_scale(model) if scaling_enabled() else 1.0


def report(model, scale):
    """Report-view line describing the unit handling for this import."""
    name = unit_name(model)
    if scale != 1.0:
        App.Console.PrintMessage(
            "  Model units: %s - scaled to mm (x %.10g)\n" % (name, scale))
    elif not scaling_enabled() and UNIT_TO_MM.get(name, 1.0) != 1.0:
        App.Console.PrintMessage(
            "  Model units: %s - NOT scaled (%s is off)\n"
            % (name, PREF_SCALE))


def _scale_placement(obj, s):
    pl = obj.Placement
    pl.Base = pl.Base * s
    obj.Placement = pl


def _scale_object(obj, s):
    """Scale one document object about the origin.  Returns True if handled.

    Shapes and meshes are scaled including their own Placement; for
    property-driven objects the Placement base is scaled separately.  Only the
    object's local data is touched, so nested objects (in App::Part) stay
    consistent when their container's Placement is scaled too.
    """
    tid = obj.TypeId
    if tid == "Part::Feature":
        sh = obj.Shape
        if not sh.isNull():
            sh = sh.copy()
            sh.scale(s, App.Vector(0, 0, 0))   # in place, geometry types kept
            obj.Shape = sh                     # also carries the Placement
        else:
            _scale_placement(obj, s)
        return True
    if tid in _PARAMETRIC_LENGTHS:
        for prop in _PARAMETRIC_LENGTHS[tid]:
            setattr(obj, prop, getattr(obj, prop).Value * s)
        _scale_placement(obj, s)
        return True
    if tid == "Part::Polygon":
        obj.Nodes = [App.Vector(p) * s for p in obj.Nodes]
        _scale_placement(obj, s)
        return True
    if tid.startswith("Mesh::"):
        m = obj.Mesh.copy()
        mat = App.Matrix()
        mat.scale(s, s, s)
        m.transform(mat)
        obj.Mesh = m
        _scale_placement(obj, s)
        return True
    if tid.startswith("Points::"):
        import Points
        obj.Points = Points.Points([App.Vector(p) * s
                                    for p in obj.Points.Points])
        _scale_placement(obj, s)
        return True
    if (tid == "App::FeaturePython" and "Points" in obj.PropertiesList
            and obj.getTypeIdOfProperty("Points")
            == "App::PropertyVectorList"):            # importSubD cage
        obj.Points = [App.Vector(p) * s for p in obj.Points]
        _scale_placement(obj, s)
        return True
    if "Placement" in obj.PropertiesList and "Shape" not in obj.PropertiesList:
        _scale_placement(obj, s)                      # App::Part, groups ...
        return True
    if "Placement" in obj.PropertiesList and tid.startswith("App::"):
        _scale_placement(obj, s)                      # App::Part has a Shape
        return True
    return False


def scale_objects(objs, s):
    """Scale *objs* (objects created by one import) by *s* about the origin."""
    if s == 1.0:
        return
    skipped = []
    for obj in objs:
        try:
            if not _scale_object(obj, s):
                skipped.append(obj)
        except Exception as e:
            skipped.append(obj)
            App.Console.PrintWarning(
                "  Unit scaling failed for %s: %s\n" % (obj.Label, e))
    for obj in skipped:
        App.Console.PrintWarning(
            "  Unit scaling: %s (%s) not scaled\n" % (obj.Label, obj.TypeId))
