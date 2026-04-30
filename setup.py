from setuptools import setup
__version__ = '0.1.0'

import os

def mysetup(requires):
    setup(name='ImportExport_3DM',
          version=str(__version__),
          packages=['freecad', 'rhino3dm'],
          maintainer="Keith Sloan",
          maintainer_email="keith@sloan-home.co.uk",
          url="https://github.com/KeithSloan/ImportExport_3DM",
          description="FreeCAD module to import and export Rhino 3DM files",
          install_requires=[requires],
          include_package_data=True)

# Still not clear if under linux one can just install lxml with pip
# or sudo apt-get install python3-lxml

mysetup('rhino3dm')
#import os
#if 'posix' in os.name:
#    mysetup('lxml')
#
#else:
#    mysetup('python3-lxml')
