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

def exportDoc3DM(filepath, fileExt):
    for obj in FreeCAD.ActiveDocument.Objects:
        exportObj(obj, filepath)


def export3DM(first, filepath, fileExt):

    print("====> Start Export 3DM 0.1")
    print("File extension : " + fileExt)
    addObjToModel(first)
    if hasattr(first, "OutList"):
        for obj in first.OutList:
            addObjToModel(obj)

def addObjToModel(obj):
    import rhino3dm

    #print(f"{obj.TypeId}")
    while switch(obj.TypeId):
        if case("App::Part"):
            print(f"App Part : {obj.Label}")
            break

        if case("Part::FeaturePython"):
            print(f"Part::FeaturePython")
            break

        if case("Part::Sphere"):
            print(f"sphere : Radius {obj.Radius}")
            break

        if case("Part::Box"):
            print(f"box : ({obj.Length},{obj.Width},{obj.Height}")
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

