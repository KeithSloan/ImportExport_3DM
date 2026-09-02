# -*- coding: utf-8 -*-
# "3DM SubD" import type: same as import3DM but reconstructs SubD objects as exact
# NURBS limit patches + control-net cage (import3DM._SUBD_AS = "subd"), instead of the
# default subdivided limit mesh.
from . import import3DM


def open(filename):
    import3DM._SUBD_AS = "subd"
    try:
        return import3DM.open(filename)
    finally:
        import3DM._SUBD_AS = "surfaces"


def insert(filename, docname):
    import3DM._SUBD_AS = "subd"
    try:
        return import3DM.insert(filename, docname)
    finally:
        import3DM._SUBD_AS = "surfaces"
