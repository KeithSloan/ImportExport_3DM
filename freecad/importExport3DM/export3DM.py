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
__title__ = "FreeCAD - Import / Export 3DM Version"
__author__ = "Keith Sloan <keith@sloan-home.co.uk>"
__url__ = ["https://github.com/KeithSloan/ImportExport_3DM"]

import FreeCAD, os, Part
from FreeCAD import Units
import rhino3dm as r3


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

class rhinoNurbsCurve():
    def __init__(self, model):
        self.model = model
        self.ControlPoints = []

    def addControlPoint(self, x, y, z):
        cp = Point3d(x,y,z)
        self.ControlPoints.append(cp)

    def addNurbsCurve(self, degree):
        NurbsCurve(degree, self.ControlPoints)
        self.model.AddCurve(NurbsCurve)
        self.ControlPoints = []

    def processNurbEdges(self, FCnurbs):
        print(f"Process Nurb Edges")
        for e in FCnurbs.Edges:
            print(f"TypeId {e.TypeId}")
            if hasattr(e, "Curve"):
                print(f"Bezier Curve")
                print(f"FirstParameter {e.Curve.FirstParameter}")
                print(dir(e))
                print(dir(e.Curve))
                print(f"Max Degrees {e.Curve.MaxDegree}")
                print(f"Number Knots {e.Curve.NbKnots}")
                print(f"Number Poles {e.Curve.NbPoles}")

            else:
                print(f"Line")

            for v in e.Vertexes:
                print(f" x {v.X} y {v.Y} z {v.Z}")
                self.addControlPoint(x, y, z)

        self.addNurbsCurve(3)        # degree 3


class rhinoModel():
    #import rhino3dm as r3
    def __init__(self):
        import rhino3dm
        print("Init Model")
        self.model = r3.File3dm()
        self.model.ApplicationName = "ImportExport_3DM"
        self.model.ApplicationUrl = "https://github.com/KeithSloan/ImportExport_3DM"
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
        self.model.Objects.AddBrep(brp)

    def write(self, filepath):
        self.model.Write(filepath, 0)


def exportDoc3DM(filepath, fileExt):
    rModel = rhinoModel()
    for obj in FreeCAD.ActiveDocument.Objects:
        addObjToModel(obj)
    rModel.Write(filepath, 0)

def export3DM(first, filepath, fileExt):

    print("====> Start Export 3DM 0.1")
    print("File extension : " + fileExt)
    rModel = rhinoModel()
    addObjToModel(first, rModel)
    if hasattr(first, "OutList"):
        for obj in first.OutList:
            addObjToModel(obj, rModel)
    ret = rModel.write(filepath)
    print(f"File {filepath} exported rc {ret}")

def length(lenQuantity):
    print(f"Len Value {Units.Quantity(lenQuantity).Value}")
    return Units.Quantity(lenQuantity).Value
    #return r3.Interval(0, Units.Quantity(lenQuantity).Value)


def processNurbEdges(model, nurbs):
    print(f"Process Nurb Edges")
    for e in nurbs.Edges:
        print(f"TypeId {e.TypeId}")
        if hasattr(e, "Curve"):
            print(f"Bezier Curve")
            print(f"FirstParameter {e.Curve.FirstParameter}")
            print(dir(e))
            print(dir(e.Curve))
            print(f"Max Degrees {e.Curve.MaxDegree}")
            print(f"Number Knots {e.Curve.NbKnots}")
            print(f"Number Poles {e.Curve.NbPoles}")

        else:
            print(f"Line")
            for v in e.Vertexes:
                print(f" x {v.X} y {v.Y} z {v.Z}")


def processNurbSurfaces(model, nurbs):
    print(f"Process Nurb Surfaces")


def processNurbs(model, nurbs):
    print(f"Process Nurbs {nurbs}")
    if hasattr(nurbs, "Edges"):
        if len(nurbs.Edges) > 0:
            processNurbEdges(model, nurbs)
    if hasattr(nurbs, "Faces"):
        if len(nurbs.Faces) > 0:
            processNurbSurfaces(model, nurbs)


def curvesToNurbs(obj, model):
    if hasattr(obj, "Shape"):
        if hasattr(obj.Shape, "toNurbs"):
            nurbs = obj.Shape.toNurbs()
            processNurbs(model, nurbs)


def checkShapeForCurves(obj, model):
    print(f"Check Shape for Curves")
    # return True for Now
    return True


def checkShape(obj, model):
    if hasattr(obj, "Shape") == None:
        return
    if checkShapeForCurves(obj, model):
        curvesToNurbs(obj, model)    


def addObjToModel(obj, model):

    #print(f"{obj.TypeId}")
    while switch(obj.TypeId):
        if case("App::Part"):
            print(f"App Part : {obj.Label}")
            break

        if case("Part::FeaturePython"):
            print(f"Part::FeaturePython")
            checkShape(obj, model)
            break

        if case("Part::Sphere"):
            print(f"sphere : Radius {obj.Radius}")
            break

        if case("Part::Box"):
            print(f"box : ({obj.Length},{obj.Width},{obj.Height})")
            #pln = r3.Plane.WorldXY
            #box = r3.Box(pln,
            box = r3.Box(r3.BoundingBox
                 (
                 0,
                  length(obj.Length),
                 0,
                  length(obj.Width),
                 0,
                  length(obj.Height)
                  ))
            brp = r3.Brep.CreateFromBox(box)
            model.Objects.AddBrep(brp)
            break

        if case("Part::Cylinder"):
           print(f"cylinder : Height {obj.Height} Radius {obj.Radius}")
           break

        if case("Part::Cone"):
           print(f"cone : Height {obj.Height} Radius1 {obj.Radius1} Radius2 {obj.Radius2}")
           break

        if case("Part::Torus"):
           print(f"torus {obj.Radius1} {obj.Radius2}")
           break

        if case("Part::Prism"):
           print("Prism")
           break

        if case("Part::RegularPolygon"):
           print("RegularPolygon")
           break

        if case("Part::Extrusion"):
           print("Extrusion")
           break
            
        if case("Mesh::Feature"):
           print("Mesh")
           # print dir(obj.Mesh)
           break

        #print("Other")
        #print(obj.TypeId)
        break


def export(exportList, filepath):
    "called when FreeCAD exports a file"
    import os

    first = exportList[0]
    print(f"Export Object: {first.Label}")

    path, fileExt = os.path.splitext(filepath)
    print("filepath : " + path)
    print("file extension : " + fileExt)
    if fileExt.lower() == ".3dm":
        export3DM(first, filepath, fileExt)

