#!/usr/bin/env python3
"""Join the import3DM and Serpentine3D area sweeps.

Usage:
    python3 join_sweeps.py [import3dm_sweep.tsv] [serp_sweep.tsv] [out_prefix]

Defaults read both sweeps from /Users/ksloan/github/CAD_Files_Git/3DM and
write <out_prefix>.tsv (the joined table) and <out_prefix>.md (a Markdown
summary for the wiki: counts plus every file outside +/-5%), with
out_prefix = serp_vs_import3dm in the current directory.

Flags (ser/imp area ratio):
  ok          within 5 %
  SER_LOW     Serpentine area < 95 % of import3DM
  SER_HIGH    Serpentine area > 105 % of import3DM
  no-surface  both areas are zero (curves, points, meshes, empty files)
  imp-zero    import3DM has no surface but Serpentine does
  ERR         either sweep reported an error / timeout
"""
import sys

DEF_DIR = "/Users/ksloan/github/CAD_Files_Git/3DM/"


def read_tsv(path, ncols):
    rows = {}
    with open(path) as fh:
        for line in fh:
            if not line.strip() or line.startswith("#"):
                continue
            parts = line.rstrip("\n").split("\t")
            parts += [""] * (ncols - len(parts))
            rows[parts[0]] = parts[1:ncols]
    return rows


def as_float(s):
    try:
        return float(s)
    except (TypeError, ValueError):
        return None


def main(argv):
    imp_path = argv[1] if len(argv) > 1 else DEF_DIR + "import3dm_sweep.tsv"
    ser_path = argv[2] if len(argv) > 2 else DEF_DIR + "serp_sweep.tsv"
    prefix = argv[3] if len(argv) > 3 else "serp_vs_import3dm"
    imp = read_tsv(imp_path, 4)     # file -> [nobj, faces, area]
    ser = read_tsv(ser_path, 3)     # file -> [nobj, area]
    out = []
    counts = {}
    for f in sorted(set(imp) | set(ser)):
        i_n, i_f, i_a = imp.get(f, ["", "", ""])
        s_n, s_a = ser.get(f, ["", ""])
        ia, sa = as_float(i_a), as_float(s_a)
        if ia is None or sa is None:
            ratio, flag = "", "ERR"
        elif ia == 0 and sa == 0:
            ratio, flag = "", "no-surface"
        elif ia == 0:
            ratio, flag = "", "imp-zero"
        else:
            r = sa / ia
            ratio = f"{r:.3f}"
            flag = "ok" if 0.95 <= r <= 1.05 else ("SER_LOW" if r < 0.95 else "SER_HIGH")
        counts[flag] = counts.get(flag, 0) + 1
        out.append((f, i_n, i_f, i_a, s_n, s_a, ratio, flag))

    with open(prefix + ".tsv", "w") as fh:
        fh.write("file\timp_nobj\timp_faces\timp_area\tser_nobj\tser_area\t"
                 "ser_over_imp\tflag\n")
        for row in out:
            fh.write("\t".join(row) + "\n")

    md = ["| result | files |", "|---|---|"]
    for k in ("ok", "SER_LOW", "SER_HIGH", "no-surface", "imp-zero", "ERR"):
        if counts.get(k):
            md.append(f"| {k} | {counts[k]} |")
    odd = [r for r in out if r[7] not in ("ok", "no-surface")]
    if odd:
        md += ["", "| file | import3DM area | Serpentine area | ser/imp | flag |",
               "|---|---|---|---|---|"]
        for f, _, _, ia, _, sa, ratio, flag in odd:
            md.append(f"| {f} | {ia} | {sa} | {ratio} | {flag} |")
    with open(prefix + ".md", "w") as fh:
        fh.write("\n".join(md) + "\n")

    print("wrote", prefix + ".tsv", "and", prefix + ".md")
    for k, v in sorted(counts.items()):
        print(f"  {k:11s} {v}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
