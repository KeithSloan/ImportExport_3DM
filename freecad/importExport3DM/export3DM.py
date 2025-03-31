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



class rhinoModel():
    #import rhino3dm as r3
    #import rhino3dm
    def __init__(self):
        import rhino3dm
        print("Init Model")
        self.model = r3.File3dm()
        self.model.ApplicationName = "ImportExport_3DM"
        self.model.ApplicationUrl = "https://github.com/KeithSloan/ImportExport_3DM"
        # Variables
        self.ControlPoints = []
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

    def addControlPoint(self, x, y, z):
        import rhino3dm
        cp = r3.Point3d(x,y,z)
        #cp = rhino3dm.Point3d(x,y,z)
        self.ControlPoints.append(cp)

    def createNurbsCurve(self, degree, poles):
        polesList = []
        print(f"Poles {poles}")
        for p in poles:
            polesList.append(r3.Point3d(p[0], p[1], p[2]))
        print(f"PolesList {polesList}")
        NurbsCurve = r3.NurbsCurve(degree, len(poles))
        nc = NurbsCurve.Create(False, degree, polesList)
        return nc

    def addNurbsCurve(self, degree, knots, mults,  poles):
        #
        # Number of Knots = Number of Control Points + Degree + 1
        #
        #knotList = r3.NurbsCurveKnotList
        #print(len(knots))
        #for i in range(len(knots)):
        #    if knotList.InsertKnot(float(knots[i]), int(mults[i])) == False:
        #        print(f"Insert Knot {i} Failed")
            
        #NurbsCurve = r3.NurbsCurve(degree, len(self.ControlPoints))
        polesList = []
        print(f"Poles {poles}")
        for p in poles:
            polesList.append(r3.Point3d(p[0], p[1], p[2]))
        print(f"PolesList {polesList}")
        NurbsCurve = r3.NurbsCurve(degree, len(poles))
        nc = NurbsCurve.Create(False, degree, polesList)
        print(f"NurbsCurve {nc}")
        self.model.Objects.AddCurve(nc)
        #self.model.Objects.AddCurve(NurbsCurve)
        #self.ControlPoints = []         # reset control points

    def processNurbEdges(self, nurbs):
        # B-Spline 
        # Control Points P0-Pn = n + 1
        # Knots u0 - um = m+1
        # Degree = p = m - n - 1
        # Degree = (nKn - 1)-(nCP - 1) - 1
        # Degree = nKn - nCP - 1
        print(f">>>>>>>>>>  Process Nurb Edges Len {len(nurbs.Edges)}")
        valid = False
        self.curves = []
        for e in nurbs.Edges:
            print(f"TypeId {e.TypeId} Number of Vertex {len(e.Vertexes)}")
            #print(dir(e))
            if len(e.Vertexes) > 1:         # Avoid error degenerate edge
                if hasattr(e, 'Curve'):
                    #print(dir(e.Curve))
                    print(f"=====  B-Spline {len(e.Vertexes)}")
                    print(f"FirstParameter {e.Curve.FirstParameter}")
                    #print(dir(e))
                    print(f"Max Degrees {e.Curve.MaxDegree}")
                    degree = e.Curve.Degree
                    print(f"Degree {degree}")
                    print(f"Number Knots {e.Curve.NbKnots}")
                    print(f"Knot Sequence {e.Curve.KnotSequence}")
                    knots = e.Curve.getKnots()
                    print(f"Knots {knots}")
                    mults = e.Curve.getMultiplicities()
                    print(f"Mults {mults}")
                    print(f"Number Poles {e.Curve.NbPoles}")
                    poles = e.Curve.getPoles()
                    print(f"Poles {poles}")
                    print(f"Poles and Weight {e.Curve.getPolesAndWeights()}")
                    self.curves.append(self.addNurbsCurve(degree, knots, mults, poles))


                print(f"Vertexes Knots?")
                for v in e.Vertexes:
                    print(f" x {v.X} y {v.Y} z {v.Z}")
                    #self.addControlPoint(v.X, v.Y, v.Z)
                valid = True

            else:
                print(f"Line")

        #if valid: self.addNurbsCurve(3)        # degree 3
        #degree =  e.Curve.NbKnots - e.Curve.NbPoles - 1
        #print(f"Degree = {degree}")
        #if valid: self.addNurbsCurve(degree)


    def processNurbSurfaces(self, nurbs):
        print(f"    Process Nurb Surfaces ToDo")


    def processNurbs(self, nurbs):
        print(f"Process Nurbs {nurbs}")
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
        print(f"Check Shape for Curves ToDp !!!!")
        # return True for Now
        return False

    def checkShapeForSurface(self, obj):
        # Just check and return True or False
        print(f"Check Shape for Surface")
        if hasattr(obj, "Surface"):
            print(f"Has Surface")
            return True
        return False

    def processSurfaceUV(self, surface):
        print(f"=========== Process Surface UV")
        print(dir(surface))
        UDegree = surface.UDegree
        UOrder = UDegree + 1
        VDegree = surface.VDegree
        VOrder =VDegree + 1
        UPoles = surface.NbUPoles
        VPoles = surface.NbVPoles
        poles = surface.getPoles()
        print(f"UPoles {UPoles} VPoles {VPoles}")
        print(f"Poles {len(poles[0])} x {len(poles[1])}")
        #print(f"Poles {poles}")
        print(f"Surface UDegree {UDegree} VDegree {VDegree}")
        VKnots = surface.getVKnots()
        UKnots = surface.getUKnots()
        VMults = surface.getVMultiplicities()
        UMults = surface.getUMultiplicities()
        #Ucurve = self.createNurbsCurve(UDegree, UKnots)
        Ucurve = self.createNurbsCurve(UDegree, poles[0])
        #Vcurve = self.createNurbsCurve(VDegree, VKnots)
        Vcurve = self.createNurbsCurve(VDegree, poles[1])
        nurbSurf = r3.NurbsSurface.Create(3, False, UOrder, VOrder, UPoles, VPoles) 
        #for c in range(0, len(self.curves)-1, 2):
        #    nurbSurf.CreateRuledSurface(self.curves[c], self.curves[c+1])
        #    self.model.Objects.AddSurface(nurbSurf)
        #ns =  nurbSurf.CreateRuledSurface(self.curves[0], self.curves[2])
        attr = r3.ObjectAttributes()
        ns =  nurbSurf.CreateRuledSurface(Ucurve, Vcurve)
        if ns is not None:
            self.model.Objects.AddSurface(ns, attr)
        else:
            print(f"Invalid Ruled Surface")    


    def processSurfaceUV3(self, surface):
        print(f"=========== Process Surface UV")
        plane = r3.Plane.WorldXY
        planeSurf = r3.PlaneSurface(plane, 10, 5)
        print(dir(planeSurf))
        ns = planeSurface.ToNurbsSurface()
        u_interval = r3.Interval(0.0, 15.0)
        v_interval = r3.Interval(0.0, 7.5)
        u_degree = 2
        v_degree = 2
        u_points = 10
        v_points = 10
        print(dir(r3.NurbsSurface))
        srf = r3.NurbsSurface.CreateFromPlane(plane, u_interval, v_interval, u_degree, v_degree, u_points, v_points)
        if srf and srf.IsValid:
            return srf
        return None


    def processSurfaceUV2(self, surface):
        print(f"=========== Process Surface UV")
        plane = r3.Plane.WorldXY
        u_interval = r3.Interval(0.0, 15.0)
        v_interval = r3.Interval(0.0, 7.5)
        u_degree = 2
        v_degree = 2
        u_points = 10
        v_points = 10
        print(dir(r3.NurbsSurface))
        srf = r3.NurbsSurface.CreateFromPlane(plane, u_interval, v_interval, u_degree, v_degree, u_points, v_points)
        if srf and srf.IsValid:
            return srf
        return None


    def createSpline(self, knots):
        print(f"createSpline knots {knots}")
        print(dir(knots))
        spline = r3.Curve
        #spline.CreateControlPointCurve(


    def checkForSurfaceUV(self, face):
        if hasattr(face, "Surface"):
            print(dir(face.Surface))
            print(f"UDegree {face.Surface.UDegree} VDegree {face.Surface.VDegree}")
            print(f"UKnots {face.Surface.NbUKnots} VKnots {face.Surface.NbVKnots}")
            if hasattr(face.Surface, "UDegree") and \
               hasattr(face.Surface, "VDegree"):
               #USpline = self.createSpline(face.Surface.NbUKnots)
               #USpline = self.createSpline(face.Surface.getUKnots())
               #VSpline = self.createSpline(face.Surface.NbVKnots)
               #VSpline = self.createSpline(face.Surface.getVKnots())
               return True

    
    def processBSplineSurface(self, obj):
        #print(f"======== Process BSplineSurface ToDo")
        if self.checkForSurfaceUV(obj):
            self.processSurfaceUV(obj.Surface)


    def processSurfacePlane(self, obj):
        print(f"======== Process Surface Plane ToDo")
        print(dir(obj))
       
    def processSurface(self, obj):
        print(f"Surface {obj.Surface}  TypeId {obj.TypeId} Typ e{type(obj.Surface)}")
        surfType = str(obj.Surface)
        #if surfType == "Part.BSplineSurface object":
        #    self.processBSplineSurface(obj)
        #    return
        #elif surfType == "Part.Plane object":
        #    self.processSurfacePlane(obj)
        #    return
        if isinstance(obj.Surface, Part.BSplineSurface):
            self.processBSplineSurface(obj)
            return
        elif isinstance(obj.Surface, Part.Plane):
            self.processSurfacePlane(obj)
            return
        print("===== >>>>> NOT YET HANDLED in processSurface")
        raise TypeError("Not Yet Handled")
    
        #if hasattr(obj, "UPeriod") and hasattr(obj, "VPeriod"):
        #    print(f"UPeriod {obj.UPeriod} VPeriod {obj.VPeriod}")
        #    self.checkForSurfaceUV(f)
        #else:
        #    print(f"Face TypeId {obj.TypeId} ShapeType {obj.ShapeType}")
        #    print(dir(obj))

    def processFaces(self, obj):
        print(obj.Shape.Faces)
        print(f"processFaces {len(obj.Shape.Faces)}")
        for f in obj.Shape.Faces:
            if self.checkShapeForSurface(f):
                self.processSurface(f) 
               

    def checkShape(self, obj):
        print(f"    CheckShape {obj.TypeId} {obj.Name}")
        if hasattr(obj, "Shape") == None:
            return
        ##### ?????? or in processFacees
        if self.checkShapeForSurface(obj):
            self.processSurface(obj)
            return
        if self.checkShapeForCurves(obj):
            self.curvesToNurbs(obj)
            return
        #print(dir(obj))    
        #print(dir(obj.Shape))
        print("======= >>>>> Not yet handled - process Faces")     
        self.processFaces(obj)

    def addObjToModel(self, obj):
        #print(f"{obj.TypeId}")
        while switch(obj.TypeId):
            if case("App::Part"):
                print(f"App Part : {obj.Label}")
                break

            if case("Part::FeaturePython"):
                print(f"Part::FeaturePython")
                self.checkShape(obj)
                break

            if case("Part::Feature"):
                print(f"Part::Feature")
                self.checkShape(obj)
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
                self.model.Objects.AddBrep(brp)
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
    rModel.addObjToModel(first)
    if hasattr(first, "OutList"):
        for obj in first.OutList:
            rModel.addObjToModel(obj)
    ret = rModel.write(filepath)
    print(f"File {filepath} exported rc {ret}")


def length(lenQuantity):
    print(f"Len Value {Units.Quantity(lenQuantity).Value}")
    return Units.Quantity(lenQuantity).Value
    #return r3.Interval(0, Units.Quantity(lenQuantity).Value)


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

