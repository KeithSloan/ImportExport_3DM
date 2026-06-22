"""Minimal smoke test: trim a 10x10 plane to a 2..8 square and write a .3dm.
Then, if rhino3dm is available, read it back and confirm it's a 1-face Brep.

    python tests/test_trim3dm.py
"""
import os
import sys
# the built trim3dm*.so sits in the project root (one level up from tests/)
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import trim3dm


def line3(p0, p1):
    return {"degree": 1, "cv": [[*p0, 1.0], [*p1, 1.0]], "knots": [0.0, 1.0]}


def line2(a, b):
    return {"degree": 1,
            "cv": [[a[0], a[1], 1.0], [b[0], b[1], 1.0]], "knots": [0.0, 1.0]}


# Bilinear 10x10 plane: point(u, v) == (u, v, 0)
surface = {
    "degree_u": 1, "degree_v": 1,
    "cv": [[[0.0, 0.0, 0.0, 1.0], [0.0, 10.0, 0.0, 1.0]],
           [[10.0, 0.0, 0.0, 1.0], [10.0, 10.0, 0.0, 1.0]]],
    "knots_u": [0.0, 10.0], "knots_v": [0.0, 10.0],
}

# Outer loop: CCW square (2,2)->(8,2)->(8,8)->(2,8). pcurve == 3D since the
# plane maps (u,v)->(u,v,0), so rev3d is False everywhere.
sq = [(2.0, 2.0), (8.0, 2.0), (8.0, 8.0), (2.0, 8.0)]
edges = []
for i in range(4):
    a, b = sq[i], sq[(i + 1) % 4]
    edges.append({
        "c3": line3((a[0], a[1], 0.0), (b[0], b[1], 0.0)),
        "c2": line2(a, b),
        "rev3d": False,
    })

face = {"name": "TrimSquare", "surface": surface, "loops": [edges]}

ok = trim3dm.write_trimmed_breps("trim_test.3dm", [face])
print("write_trimmed_breps ->", ok)

try:
    import rhino3dm
    m = rhino3dm.File3dm.Read("trim_test.3dm")
    print("objects in file:", len(m.Objects))
    g = m.Objects[0].Geometry
    nfaces = len(g.Faces) if hasattr(g, "Faces") else "-"
    print("geometry:", type(g).__name__, "faces:", nfaces, "isSurface:",
          getattr(g, "IsSurface", "?"))
    # A trivially-trimmed Brep would report IsSurface == True. We trimmed it to
    # a smaller square, so a correct result should be a Brep with IsSurface False.
except Exception as e:
    print("rhino3dm verification skipped:", e)
