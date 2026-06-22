cmake_minimum_required(VERSION 3.18)
project(trim3dm LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

# --- pybind11 (submodule under extern/pybind11) ---
add_subdirectory(extern/pybind11)

# --- OpenNURBS (submodule under extern/opennurbs) ---
# mcneel/opennurbs ships a CMakeLists that builds a static `opennurbs` target.
# (Public OpenNURBS; no Rhino SDK needed.)
add_subdirectory(extern/opennurbs)

pybind11_add_module(trim3dm src/trim3dm.cpp)

# OpenNURBS' CMake builds a static target named `opennurbsStatic`
# (and a shared `OpenNURBS`). Link the static one.
target_link_libraries(trim3dm PRIVATE opennurbsStatic)
target_include_directories(trim3dm PRIVATE
    ${CMAKE_CURRENT_SOURCE_DIR}/extern/opennurbs)

# OpenNURBS on macOS needs these frameworks/macros (matches rhino3dm's setup):
if(APPLE)
  target_compile_definitions(trim3dm PRIVATE ON_COMPILER_CLANG ON_RUNTIME_APPLE)
  target_link_libraries(trim3dm PRIVATE
      "-framework CoreFoundation" "-framework Security")
endif()
