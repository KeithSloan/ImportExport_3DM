class common3DM:
    def __init__(self, obj):
        """Init"""

    def __getstate__(self):
        """When saving the document this object gets stored using Python's
        json module.
        Since we have some un-serializable parts here -- the Coin stuff --
        we must define this method
        to return a tuple of all serializable objects or None."""
        if hasattr(self, "Type"):  # If not saved just return
            return {"type": self.Type}
        else:
            pass

    def __setstate__(self, arg):
        """When restoring the serialized object from document we have the
        chance to set some internals here.
        Since no data were serialized nothing needs to be done here."""
        # Handle bug in FreeCAD 0.21.2 handling of json
        #print(f"setstate : arg {arg} type {type(arg)}")
        if arg is not None and arg != {}:
            if 'type' in arg:
                self.Type = arg["type"]
            else: #elif 'Type' in arg:
                self.Type = arg["Type"]
            #print(self.Type)

class Surface3DM(common3DM):
    def __init__(self, obj):
        super().__init__(obj)
        """Add some custom properties to Surface3DM Objecte"""
        obj.addProperty("App::PropertyFloat", "x", "Surface3DM", "Length x").x = x
        #obj.addProperty("App::PropertyFloat", "y", "GDMLBox", "Length y").y = y
        #obj.addProperty("App::PropertyFloat", "z", "GDMLBox", "Length z").z = z
        #obj.addProperty(
        #    "App::PropertyEnumeration", "lunit", "GDMLBox", "lunit"
        #)
        #setLengthQuantity(obj, lunit)
        #obj.lunit = LengthQuantityList.index(lunit)
        #obj.addProperty(
        # "App::PropertyEnumeration", "material", "GDMLBox", "Material"
        #)
        #setMaterial(obj, material)
        #if FreeCAD.GuiUp:
        #    updateColour(obj, colour, material)
            # Suppress Placement - position & Rotation via parent App::Part
            # this makes Placement via Phyvol easier and allows copies etc
        self.Type = "Surface3DM"
        #self.colour = colour
        obj.Proxy = self
        obj.Proxy.Type = "Surface3DM"

    def onChanged(self, fp, prop):
        """Do something when a property has changed"""
        # print(fp.Label+" State : "+str(fp.State)+" prop : "+prop)
        # Changing Shape in createGeometry will redrive onChanged
        if "Restore" in fp.State:
            return

        #if prop in ["material"]:
        #    if FreeCAD.GuiUp:
        #        if hasattr(self, "colour"):
        #            if self.colour is None:
        #                fp.ViewObject.ShapeColor = colourMaterial(fp.material)
        #        if fp.material == "G4_AIR":
        #            print("Set Transparency")
        #            fp.ViewObject.Transparency = 98

        #if prop in ["x", "y", "z", "lunit"]:
        #    self.createGeometry(fp)

def createGeometry(self, fp):
        print('createGeometry')

        #if (hasattr(fp,'x') and hasattr(fp,'y') and hasattr(fp,'z')) :

        #   currPlacement = fp.Placement
        #    mul = GDMLShared.getMult(fp)
        #    GDMLShared.trace("mul : " + str(mul))
        #    x = mul * fp.x
        #    y = mul * fp.y
        #   z = mul * fp.z
        #    box = Part.makeBox(x, y, z)
        #    base = FreeCAD.Vector(-x / 2, -y / 2, -z / 2)
        #    fp.Shape = translate(box, base)
        #   fp.Placement = currPlacement
        #if hasattr(fp, "scale"):
        #    super().scale(fp)

def OnDocumentRestored(self, obj):
        print("Doc Restored")

# use general ViewProvider if poss
class ViewProvider:
    def __init__(self, obj):
        super().__init__()
        """Set this object to the proxy object of the actual view provider"""
        obj.Proxy = self

    def updateData(self, fp, prop):
        """If a property of the handled feature has changed we have the chance to handle this here"""
        # print("updateData")
        pass

    def getDisplayModes(self, obj):
        """Return a list of display modes."""
        # print("getDisplayModes")
        modes = []
        modes.append("Shaded")
        modes.append("Wireframe")
        modes.append("Points")
        return modes

    def getDefaultDisplayMode(self):
        """Return the name of the default display mode. It must be defined in getDisplayModes."""
        return "Shaded"

    def setDisplayMode(self, mode):
        """Map the display mode defined in attach with those defined in getDisplayModes.\
               Since they have the same names nothing needs to be done. This method is optional"""
        return mode

    def onChanged(self, vp, prop):
        """Here we can do something when a single property got changed"""
        # if hasattr(vp,'Name') :
        #   print("View Provider : "+vp.Name+" State : "+str(vp.State)+" prop : "+prop)
        # else :
        #   print("View Provider : prop : "+prop)
        pass

    def getIcon(self):
        """Return the icon in XPM format which will appear in the tree view. This method is\
               optional and if not defined a default icon is shown."""
        return """
           /* XPM */
           static const char * ViewProviderBox_xpm[] = {
           "16 16 6 1",
           "   c None",
           ".  c #141010",
           "+  c #615BD2",
           "@  c #C39D55",
           "#  c #000000",
           "$  c #57C355",
           "        ........",
           "   ......++..+..",
           "   .@@@@.++..++.",
           "   .@@@@.++..++.",
           "   .@@  .++++++.",
           "  ..@@  .++..++.",
           "###@@@@ .++..++.",
           "##$.@@$#.++++++.",
           "#$#$.$$$........",
           "#$$#######      ",
           "#$$#$$$$$#      ",
           "#$$#$$$$$#      ",
           "#$$#$$$$$#      ",
           " #$#$$$$$#      ",
           "  ##$$$$$#      ",
           "   #######      "};
           """
    
    def __getstate__(self):
        """When saving the document this object gets stored using Python's json module.\
               Since we have some un-serializable parts here -- the Coin stuff -- we must define this method\
               to return a tuple of all serializable objects or None."""
        return None

    def __setstate__(self, state):
        """When restoring the serialized object from document we have the chance to set some internals here.\
               Since no data were serialized nothing needs to be done here."""
        return None