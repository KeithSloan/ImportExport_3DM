<!-- Draft comment for https://github.com/mcneel/rhino3dm/issues/712
     Posting account: KeithSloan. Edit names/links as needed before posting. -->

As a workaround for this (the loop/trim/Curves2D tables not being exposed, so
trimmed Breps can't be *constructed* from the rhino3dm Python API), I built a
small standalone pybind11 + OpenNURBS extension, **trim3dm**, that builds and
reads trimmed Breps directly in `.3dm` files.

It's deliberately **independent of rhino3dm** — the two don't share any C++
objects; they just cooperate at the file level, since both speak OpenNURBS. In
my pipeline rhino3dm still does all the untrimmed geometry, and trim3dm only adds
the trimmed Breps to the same file afterwards.

What it does:

- `write_trimmed_breps` / `add_trimmed_breps` — build `ON_Brep`s by hand
  (`NewFace`/`NewLoop`/`NewVertex`/`NewEdge`/`NewTrim` + `SetTolerancesBoxesAndFlags`)
  and add them to a model / append them to an existing `.3dm`.
- `read_trimmed_breps` — read the trims back out (surface, 2D pcurves, loops).

Proven end-to-end: FreeCAD trimmed face → trim3dm write → `.3dm` → trim3dm read →
rebuild in OpenCASCADE → valid trimmed face. Source and build instructions
(macOS/Linux/Windows) are here: <ADD-REPO-LINK> (branch `trim3dm`).

A few notes in case they're useful to others hitting this, or to anyone scoping a
proper binding:

- CVs must be set with `ON::homogeneous_rational` on rational geometry, and the
  curve/surface created rational, or a 4-wide `Point4d` overruns a 3-wide CV.
- `AddManagedModelGeometryComponent` takes ownership of **both** the geometry and
  the attributes, so the `ON_3dmObjectAttributes` must be heap-allocated (a stack
  attr dangles and crashes on write).
- Freshly hand-built trims often leave `m_tolerance` UNSET; a small positive
  fallback after `SetTolerancesBoxesAndFlags()` avoids downstream validity issues.

This isn't a substitute for binding the loop/trim tables in rhino3dm itself —
which is what I think a lot of people in this thread actually want — but it's a
usable stopgap today for getting trimmed Breps in and out of `.3dm` from Python.
Happy to share more detail if it helps anyone working on the real binding.
