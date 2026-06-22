"""Read trimmed Breps back out of a .3dm and print a summary.
    python tests/read_test.py [path-to.3dm]
"""
import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import trim3dm

PATH = sys.argv[1] if len(sys.argv) > 1 else "trim_test.3dm"

faces = trim3dm.read_trimmed_breps(PATH)
print("read", len(faces), "faces from", PATH)
for d in faces:
    s = d["surface"]
    e0 = d["loops"][0][0] if d["loops"] and d["loops"][0] else None
    print("  %-20s deg=%dx%d cv=%dx%d loops=%s%s" % (
        d["name"], s["degree_u"], s["degree_v"],
        len(s["cv"]), len(s["cv"][0]),
        [len(l) for l in d["loops"]],
        ("  edge0 c2/c3 pts=%d/%d rev3d=%s" % (
            len(e0["c2"]["cv"]), len(e0["c3"]["cv"]), e0["rev3d"]) if e0 else "")))
