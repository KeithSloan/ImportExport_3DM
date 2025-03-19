
# ImportExport 3DM

  Add Import/Export of 3DM files to FreeCAD

##########################################################
# Some coded added lots more to do.                      #
# Please report any problems as Issues - Thanks          #
##########################################################
  
# Requirements 

* rhino3dm - Open Python Rhino 3dm library 

You need to use the same version and level of Python that FreeCAD is using to
install rhino3dm. 

You can find out the version FreeCAD is using by using
 
    FreeCAD | About freecad | Libraries 
or
    Looking at the heading in FreeCAD python console   
  
# Installation - Add on Manager

 * The workbench is available via the FreeCAD AddonManager
 * However users may have to install rhino3dm depending on OS.
 * One suggestion
     - Start FreeCAD
     - In python console
        - import sys
        - print(sys.path)
         
     - Select one the the directories listed

       If FreeCAD 1.0.0 is using Python 3.11
     
       python3.11 -m pip install rhino3dm --no-cache -t [directory path]
     
     - restart FreeCAD


# Installing for FreeCAD 1.0.0 on MacOS

* FreeCAD 1.0.0 on Mac uses Python 3.11
  
  Make sure Mac is also 3.11 using homebrew
  
  brew instal python@3.11

* install rhino3dm in FreeCAD path

- Start FreeCAD
     - In python console
        - import sys
        - print(sys.path)
          
 - python3.11 -m pip install rhino3dm  --no-cache -t '/Applications/FreeCAD 1.0.0.app/Contents/Resources/lib/python3.11/site-packages'

  

# Alternate Installation ( Linux )

 * sudo apt install python3-pip
 * pip3 install --user rhino3dm
 * Change directory to .FreeCAD/Mod   
   i.e. with a dot
 * git clone  https://github.com/KeithSloan/ImportNURBS.git
 * start or restart FreeCAD
 
# Rhino - API h

  ttps://developer.rhino3d.com/api/rhinocommon/

# Sample Rhino files

  Can be downloaded from https://www.rhino3d.com/download/opennurbs/6/opennurbs6samples 

# Acknowledgements

  * Icon design by Freepik
  * 3dm testCases kindly supplied by
      * Jonne Neva (cheezebreeze)
      * EdWilliams
      * Sven


# Developers 
  
 * Chris Grellier
 * Keith Sloan
  
