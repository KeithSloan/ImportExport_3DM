// trim3dm — build trimmed Breps in OpenNURBS and add them to a .3dm file.
//
// Decoupled from rhino3dm: input is plain Python data (no rhino3dm types),
// output is a .3dm file. See README for the data schema.
//
// Build: pybind11 + OpenNURBS (see CMakeLists.txt).
//
// NOTE: This is a scaffold. A few OpenNURBS calls are version-sensitive and
// are flagged with  // VERIFY  — check them against your opennurbs headers.

#include <pybind11/pybind11.h>
#include <pybind11/stl.h>
#include <cstdio>
#include "opennurbs_public.h"   // VERIFY: header name for your opennurbs build

namespace py = pybind11;

#define DBG(msg) do { std::fprintf(stderr, "[trim3dm] %s\n", (msg)); std::fflush(stderr); } while (0)

// ---------- helpers: build ON geometry from plain python dicts -------------

// Build an ON_NurbsCurve from {"degree", "cv":[[..]], "knots":[..]}.
// dim = 2 for pcurves (cv = [u,v,w]), 3 for edge curves (cv = [x,y,z,w]).
// Control points arrive HOMOGENEOUS: a dim-D point is D+1 doubles
//   dim 3 -> [x*w, y*w, z*w, w]   dim 2 -> [u*w, v*w, w]
// We always create the curve/surface RATIONAL so the CV slot is D+1 wide and
// matches the homogeneous array exactly (weight 1 is exact, no distortion).
static ON_NurbsCurve* make_curve(const py::dict& d, int dim)
{
  int degree = d["degree"].cast<int>();
  auto cv = d["cv"].cast<std::vector<std::vector<double>>>();
  auto knots = d["knots"].cast<std::vector<double>>();
  int order = degree + 1;
  int n = (int)cv.size();

  ON_NurbsCurve* c = ON_NurbsCurve::New();
  c->Create(dim, true /*rational*/, order, n);
  for (int i = 0; i < n; ++i)
    c->SetCV(i, ON::homogeneous_rational, cv[i].data());   // D+1 doubles
  int kc = n + order - 2;                                   // ON knot count
  for (int i = 0; i < kc && i < (int)knots.size(); ++i)
    c->SetKnot(i, knots[i]);
  return c;
}

static ON_NurbsSurface* make_surface(const py::dict& d)
{
  int du = d["degree_u"].cast<int>();
  int dv = d["degree_v"].cast<int>();
  auto cv = d["cv"].cast<std::vector<std::vector<std::vector<double>>>>(); // [i][j][4]
  auto ku = d["knots_u"].cast<std::vector<double>>();
  auto kv = d["knots_v"].cast<std::vector<double>>();
  int ou = du + 1, ov = dv + 1;
  int nu = (int)cv.size();
  int nv = nu ? (int)cv[0].size() : 0;

  ON_NurbsSurface* s = ON_NurbsSurface::New();
  s->Create(3, true /*rational*/, ou, ov, nu, nv);
  for (int i = 0; i < nu; ++i)
    for (int j = 0; j < nv; ++j)
      s->SetCV(i, j, ON::homogeneous_rational, cv[i][j].data());  // 4 doubles
  int kcu = nu + ou - 2, kcv = nv + ov - 2;
  for (int i = 0; i < kcu && i < (int)ku.size(); ++i) s->SetKnot(0, i, ku[i]);
  for (int j = 0; j < kcv && j < (int)kv.size(); ++j) s->SetKnot(1, j, kv[j]);
  return s;
}

// ---------- the core: assemble a trimmed ON_Brep ---------------------------

static ON_Brep* build_trimmed_brep(const py::dict& face)
{
  DBG("build: start");
  ON_Brep* brep = ON_Brep::New();

  DBG("build: make_surface");
  ON_NurbsSurface* srf = make_surface(face["surface"].cast<py::dict>());
  DBG("build: AddSurface");
  const int si = brep->AddSurface(srf);            // brep owns srf
  DBG("build: NewFace");
  ON_BrepFace& bface = brep->NewFace(si);

  auto loops = face["loops"].cast<py::list>();
  for (size_t li = 0; li < loops.size(); ++li)
  {
    auto edges = loops[li].cast<py::list>();
    ON_BrepLoop::TYPE lt = (li == 0) ? ON_BrepLoop::outer : ON_BrepLoop::inner;
    ON_BrepLoop& loop = brep->NewLoop(lt, bface);

    DBG("build: NewLoop");
    int n = (int)edges.size();
    std::vector<int> vidx(n);
    // one vertex per loop corner (start of each 3D edge)
    DBG("build: vertex loop");
    for (int i = 0; i < n; ++i)
    {
      py::dict e = edges[i].cast<py::dict>();
      ON_NurbsCurve* c3 = make_curve(e["c3"].cast<py::dict>(), 3);
      ON_3dPoint p0 = c3->PointAtStart();
      ON_BrepVertex& v = brep->NewVertex(p0, 0.0);
      vidx[i] = v.m_vertex_index;
      delete c3;   // re-made below; cheap and keeps ownership clear
    }
    DBG("build: edge/trim loop");
    for (int i = 0; i < n; ++i)
    {
      py::dict e = edges[i].cast<py::dict>();
      ON_NurbsCurve* c3 = make_curve(e["c3"].cast<py::dict>(), 3);
      ON_NurbsCurve* c2 = make_curve(e["c2"].cast<py::dict>(), 2);
      bool rev3d = e.contains("rev3d") ? e["rev3d"].cast<bool>() : false;

      int c3i = brep->AddEdgeCurve(c3);            // -> m_C3, brep owns
      int c2i = brep->AddTrimCurve(c2);            // -> m_C2, brep owns

      ON_BrepVertex& v0 = brep->m_V[vidx[i]];
      ON_BrepVertex& v1 = brep->m_V[vidx[(i + 1) % n]];
      ON_BrepEdge& edge = brep->NewEdge(v0, v1, c3i, nullptr, 0.0);

      ON_BrepTrim& trim = brep->NewTrim(edge, rev3d, loop, c2i);
      trim.m_type = ON_BrepTrim::boundary;
      // Leave tolerances UNSET so the Set*Tolerances calls below compute the
      // real deviation. Pinning them to 0 rejects any sampled pcurve (which is
      // never an exact match to the 3d edge).
      trim.m_tolerance[0] = ON_UNSET_VALUE;
      trim.m_tolerance[1] = ON_UNSET_VALUE;
    }
  }

  DBG("build: finalize (SetTolerancesBoxesAndFlags)");
  // Canonical finalize: sets pcurve/trim bounding boxes + iso/type/loop flags
  // and tries to compute tolerances.
  brep->SetTolerancesBoxesAndFlags();  // defaults: bLazy=false, all true

  // Auto-compute can leave tolerances UNSET (e.g. when a sampled pcurve deviates
  // slightly from the 3d edge). A tolerance only has to be >= the real
  // deviation, so fill anything still unset with a small positive fallback.
  const double fb = 0.1;  // mm
  for (int i = 0; i < brep->m_V.Count(); ++i)
    if (!(brep->m_V[i].m_tolerance >= 0.0)) brep->m_V[i].m_tolerance = fb;
  for (int i = 0; i < brep->m_E.Count(); ++i)
    if (!(brep->m_E[i].m_tolerance >= 0.0)) brep->m_E[i].m_tolerance = fb;
  for (int i = 0; i < brep->m_T.Count(); ++i)
  {
    ON_BrepTrim& t = brep->m_T[i];
    if (!(t.m_tolerance[0] >= 0.0)) t.m_tolerance[0] = fb;
    if (!(t.m_tolerance[1] >= 0.0)) t.m_tolerance[1] = fb;
  }
  DBG("build: done");
  return brep;
}

// ---------- file-level entry points ----------------------------------------

static bool add_to_model(ONX_Model& model, const py::list& faces, std::string& err)
{
  for (auto item : faces)
  {
    py::dict face = item.cast<py::dict>();
    ON_Brep* brep = build_trimmed_brep(face);
    DBG("model: IsValid check");
    ON_wString wlog;
    ON_TextLog log(wlog);
    if (!brep->IsValid(&log))
    {
      // capture the reason IsValid reported
      ON_String slog(wlog);
      std::string nm = face.contains("name")
              ? face["name"].cast<std::string>() : std::string("?");
      err += "invalid brep [" + nm + "]: "
           + std::string(slog.Array() ? slog.Array() : "(no detail)") + "\n";
    }
    DBG("model: AddManagedModelGeometryComponent");
    // BOTH pointers are "managed" — OpenNURBS takes ownership and deletes them.
    // They must be heap-allocated (a stack attr would dangle and crash Write).
    ON_3dmObjectAttributes* attr = new ON_3dmObjectAttributes();
    if (face.contains("name"))
    {
      std::string nm = face["name"].cast<std::string>();
      attr->m_name = nm.c_str();
    }
    model.AddManagedModelGeometryComponent(brep, attr);
    DBG("model: added");
  }
  return true;
}

static bool write_trimmed_breps(const std::string& out_path, py::list faces)
{
  ONX_Model model;
  std::string err;
  add_to_model(model, faces, err);
  if (!err.empty()) py::print(err);
  DBG("write: ONX_Model.Write");
  bool ok = model.Write(out_path.c_str(), 0);              // VERIFY: version arg
  DBG("write: done");
  return ok;
}

static bool add_trimmed_breps(const std::string& in_path,
                              const std::string& out_path, py::list faces)
{
  ONX_Model model;
  if (!model.Read(in_path.c_str()))
    return false;
  std::string err;
  add_to_model(model, faces, err);
  if (!err.empty()) py::print(err);
  return model.Write(out_path.c_str(), 0);
}

// ---------- read side: 3dm trimmed Breps -> plain python data --------------
// Mirror of the write schema, so import3DM can rebuild trimmed faces with OCP.

static py::dict curve_to_dict(const ON_NurbsCurve& c)
{
  py::dict d;
  d["degree"] = c.Degree();
  int dim = c.Dimension();
  py::list cv;
  for (int i = 0; i < c.CVCount(); ++i)
  {
    double b[4] = {0, 0, 0, 1};
    c.GetCV(i, ON::homogeneous_rational, b);   // dim+1 homogeneous values
    py::list pt;
    for (int k = 0; k <= dim; ++k) pt.append(b[k]);
    cv.append(pt);
  }
  d["cv"] = cv;
  py::list knots;
  for (int i = 0; i < c.KnotCount(); ++i) knots.append(c.Knot(i));
  d["knots"] = knots;
  return d;
}

static py::dict surface_to_dict(const ON_NurbsSurface& s)
{
  py::dict d;
  d["degree_u"] = s.Degree(0);
  d["degree_v"] = s.Degree(1);
  py::list cv;
  for (int i = 0; i < s.CVCount(0); ++i)
  {
    py::list row;
    for (int j = 0; j < s.CVCount(1); ++j)
    {
      double b[4] = {0, 0, 0, 1};
      s.GetCV(i, j, ON::homogeneous_rational, b);
      py::list pt;
      for (int k = 0; k < 4; ++k) pt.append(b[k]);
      row.append(pt);
    }
    cv.append(row);
  }
  d["cv"] = cv;
  py::list ku, kv;
  for (int i = 0; i < s.KnotCount(0); ++i) ku.append(s.Knot(0, i));
  for (int j = 0; j < s.KnotCount(1); ++j) kv.append(s.Knot(1, j));
  d["knots_u"] = ku;
  d["knots_v"] = kv;
  return d;
}

static py::list read_trimmed_breps(const std::string& path)
{
  py::list out;
  ONX_Model model;
  if (!model.Read(path.c_str()))
    return out;

  ONX_ModelComponentIterator it(model, ON_ModelComponent::Type::ModelGeometry);
  for (const ON_ModelComponent* mc = it.FirstComponent();
       mc != nullptr; mc = it.NextComponent())
  {
    const ON_ModelGeometryComponent* mg = ON_ModelGeometryComponent::Cast(mc);
    if (!mg) continue;
    const ON_Geometry* geo = mg->Geometry(nullptr);
    const ON_Brep* brep = ON_Brep::Cast(geo);
    if (!brep) continue;

    std::string name;
    const ON_3dmObjectAttributes* attr = mg->Attributes(nullptr);
    if (attr)
    {
      ON_String s(attr->m_name);
      if (s.Array()) name = s.Array();
    }

    for (int fi = 0; fi < brep->m_F.Count(); ++fi)
    {
      const ON_BrepFace& face = brep->m_F[fi];
      const ON_Surface* srf = face.SurfaceOf();
      if (!srf) continue;
      ON_NurbsSurface ns;
      if (srf->GetNurbForm(ns) < 1) continue;

      py::dict fd;
      fd["name"] = name;
      fd["surface"] = surface_to_dict(ns);

      py::list loops;
      for (int li = 0; li < face.LoopCount(); ++li)
      {
        const ON_BrepLoop* loop = face.Loop(li);
        if (!loop) continue;
        py::list ploop;
        for (int ti = 0; ti < loop->TrimCount(); ++ti)
        {
          const ON_BrepTrim* trim = loop->Trim(ti);
          if (!trim) continue;
          const ON_Curve* c2 = trim->TrimCurveOf();
          const ON_Curve* c3 = trim->EdgeCurveOf();
          if (!c2 || !c3) continue;
          ON_NurbsCurve nc2, nc3;
          if (c2->GetNurbForm(nc2) < 1 || c3->GetNurbForm(nc3) < 1) continue;
          py::dict ed;
          ed["c3"] = curve_to_dict(nc3);
          ed["c2"] = curve_to_dict(nc2);
          ed["rev3d"] = (bool)trim->m_bRev3d;
          ploop.append(ed);
        }
        loops.append(ploop);
      }
      fd["loops"] = loops;
      out.append(fd);
    }
  }
  return out;
}

PYBIND11_MODULE(trim3dm, m)
{
  m.doc() = "Build/read trimmed Breps in OpenNURBS .3dm files";
  ON::Begin();    // VERIFY: needed by some opennurbs builds
  m.def("write_trimmed_breps", &write_trimmed_breps,
        py::arg("out_path"), py::arg("faces"));
  m.def("add_trimmed_breps", &add_trimmed_breps,
        py::arg("in_path"), py::arg("out_path"), py::arg("faces"));
  m.def("read_trimmed_breps", &read_trimmed_breps, py::arg("path"));
}
