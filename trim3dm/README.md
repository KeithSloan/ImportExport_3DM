# trim3dm

A small pybind11 + OpenNURBS extension that does the one thing rhino3dm can't:
**build and read trimmed Breps** in `.3dm` files. Used by ImportExport_3DM to
write/read trimmed surfaces for the FreeCAD ↔ 3dm ↔ Rhino pipeline.

It is decoupled from rhino3dm — they cooperate at the **file level** (both speak
OpenNURBS), so no C++ objects cross between them:

```
exporter:  rhino3dm writes curves/untrimmed surfaces -> out.3dm
           trim3dm.add_trimmed_breps(out.3dm, ...)    -> adds trimmed Breps
importer:  trim3dm.read_trimmed_breps(in.3dm)         -> trim data (surface +
           loops of 3D edges + 2D pcurves) -> rebuilt as trimmed faces via OCP
```

## API

```python
trim3dm.write_trimmed_breps(out_path, faces)            # fresh file
trim3dm.add_trimmed_breps(in_path, out_path, faces)     # append to existing
faces = trim3dm.read_trimmed_breps(path)                # read back
```

`faces` is plain data (no rhino3dm types). Control points are **homogeneous**
`(x*w, y*w, z*w, w)`; knots are in OpenNURBS form (count = nPoles + degree - 1):

```python
face = {
  "name": "Plane_0",
  "surface": {"degree_u": 1, "degree_v": 1,
              "cv": [[[x,y,z,w], ...], ...],          # cv[i][j]
              "knots_u": [...], "knots_v": [...]},
  "loops": [                                           # [0] outer, rest inner
    [ {"c3": {"degree":1, "cv":[[x,y,z,w],...], "knots":[...]},   # 3D edge
       "c2": {"degree":1, "cv":[[u,v,w],...],   "knots":[...]},   # 2D pcurve
       "rev3d": False}, ... ],
  ],
}
```

## Build

trim3dm is a C++17 pybind11 extension linking OpenNURBS. OpenNURBS and pybind11
are fetched as git submodules into `extern/`. The output is one
`trim3dm.cpython-3XY-<platform>.so` (or `.pyd` on Windows).

**Key rule:** build against a Python that has **dev headers** and whose **minor
version matches** the host that will import it (FreeCAD 1.1 = 3.11). FreeCAD's
bundled Python ships no build headers, so use a same-minor Python that does
(e.g. a conda env). The resulting `.so` imports fine into FreeCAD because
extension modules resolve Python symbols at load time.

First time (any platform): get the submodules.
```bash
git -C extern clone --depth 1 https://github.com/mcneel/opennurbs  opennurbs   2>/dev/null || true
git -C extern clone --depth 1 https://github.com/pybind/pybind11   pybind11    2>/dev/null || true
```
(`build.sh` does this for you on macOS/Linux.)

### macOS (arm64 / x86_64)

Needs Xcode command-line tools + CMake.
```bash
xcode-select --install        # once
brew install cmake            # once
conda create -y -n trim311 python=3.11   # a Python WITH headers, matching FreeCAD
conda activate trim311
PYTHON=$(which python) ./build.sh
python tests/test_trim3dm.py
conda deactivate
```

### Linux

Needs gcc/g++ (C++17) + CMake + a python3-dev (or conda python).
```bash
sudo apt install build-essential cmake git    # Debian/Ubuntu
conda create -y -n trim311 python=3.11 && conda activate trim311   # or use python3-dev
PYTHON=$(which python) ./build.sh             # build.sh works on Linux (nproc)
python tests/test_trim3dm.py
```

### Windows

Needs Visual Studio 2019/2022 (MSVC, "Desktop development with C++") + CMake.
`build.sh` is bash-only, so configure/build with CMake directly from a
**Developer Command Prompt** (or PowerShell):
```bat
:: get submodules first (see "First time" above, using git)
conda create -y -n trim311 python=3.11
conda activate trim311
cmake -S . -B build -A x64 ^
  -DCMAKE_BUILD_TYPE=Release ^
  -DPython_EXECUTABLE="%CONDA_PREFIX%\python.exe" ^
  -DPYBIND11_FINDPYTHON=ON
cmake --build build --config Release
:: result: build\Release\trim3dm.cp311-win_amd64.pyd  -> copy next to tests, or onto FreeCAD's path
python tests\test_trim3dm.py
```
If CMake can't find the Python dev module, pass the include/lib explicitly:
`-DPython_INCLUDE_DIR="%CONDA_PREFIX%\include"` and
`-DPython_LIBRARY="%CONDA_PREFIX%\libs\python311.lib"`.

### Installing into FreeCAD

Drop the built `trim3dm.*.so` / `.pyd` somewhere on FreeCAD's `sys.path` — e.g.
next to `import_trim_3DM.py` in the module folder, or
`…/FreeCAD/Contents/Resources/lib/python3.11/site-packages/`. `import_trim_3DM`
also searches a `trim3dm/` build folder next to itself.

### Notes

- Builds against **one** Python minor at a time. For multiple hosts (FreeCAD
  3.11 + Blender 3.13), build once per env.
- The `.so`/`.pyd` is platform-specific; ship per-platform builds (or a CI
  matrix) if distributing.

## Notes

- Trimmed-curved-Brep construction isn't exposed in rhino3dm (issue #712); it
  *does* exist in OpenNURBS C++, which is what this wraps.
- See `THIRD_PARTY_NOTICES.md` for OpenNURBS / zlib / FreeType / pybind11 terms.
- Status: working (write + read proven end-to-end through FreeCAD ↔ 3dm).
