#!/usr/bin/env bash
# Build trim3dm on macOS (or Linux). Fetches OpenNURBS + pybind11 into extern/,
# then compiles the extension with CMake.
#
# Usage:
#   ./build.sh                      # builds against `python3` on PATH
#   PYTHON=/Applications/FreeCAD_1.1.app/Contents/Resources/bin/python ./build.sh
#
# Requirements: git, cmake, a C++17 compiler (Xcode CLT on macOS:
#   xcode-select --install   /   brew install cmake)
set -euo pipefail
cd "$(dirname "$0")"

PYTHON="${PYTHON:-$(command -v python3)}"
echo "Building trim3dm for: $PYTHON"
"$PYTHON" --version

mkdir -p extern
[ -d extern/pybind11 ]  || git clone --depth 1 https://github.com/pybind/pybind11  extern/pybind11
[ -d extern/opennurbs ] || git clone --depth 1 https://github.com/mcneel/opennurbs extern/opennurbs

# Hand CMake the exact include dir + libpython so FindPython doesn't fail to
# locate a conda Python's "Development.Module".
PYINC="$("$PYTHON" -c 'import sysconfig; print(sysconfig.get_path("include"))')"
PYLIB="$("$PYTHON" - <<'EOF'
import os, sysconfig
libdir = sysconfig.get_config_var("LIBDIR") or ""
ldlib  = sysconfig.get_config_var("LDLIBRARY") or ""
print(os.path.join(libdir, ldlib))
EOF
)"
echo "Python include: $PYINC"
echo "Python library: $PYLIB"

cmake -S . -B build \
  -DCMAKE_BUILD_TYPE=Release \
  -DPython_EXECUTABLE="$PYTHON" \
  -DPython_INCLUDE_DIR="$PYINC" \
  -DPython_LIBRARY="$PYLIB" \
  -DPYBIND11_FINDPYTHON=ON

cmake --build build -j"$(sysctl -n hw.ncpu 2>/dev/null || nproc)"

SO="$(ls build/trim3dm*.so 2>/dev/null | head -1 || true)"
if [ -n "$SO" ]; then
  cp "$SO" "$(dirname "$0")/"
  echo "Built: $SO  (copied next to README for the test)"
  echo "Run:   $PYTHON tests/test_trim3dm.py"
else
  echo "Build finished but no trim3dm*.so found — check CMake output above."
fi
