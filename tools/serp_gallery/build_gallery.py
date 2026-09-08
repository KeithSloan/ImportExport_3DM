#!/usr/bin/env python3
"""Rebuild the Serpentine3D vs ImportExport_3DM side-by-side gallery HTML.

Usage:
    python3 build_gallery.py <imp_dir> <serp_dir> <out_html>
  - imp_dir   folder with the FreeCAD/import3DM PNGs (e.g. wiki images/)
  - serp_dir  folder with the Serpentine3D PNGs (may be missing some files)
  - out_html  path of the HTML page to write

The page copies nothing; it references the two folders' images by relative
name, so place the HTML next to (or above) those folders, or copy the PNGs
next to it first (see Serpentine_Gallery.md).
"""
import sys
import os
import html


def main():
    if len(sys.argv) != 4:
        print(__doc__)
        return 2
    imp_dir, serp_dir, out_html = sys.argv[1:4]
    names = sorted(os.path.basename(p) for p in os.listdir(imp_dir)
                   if p.endswith(".png"))
    P = ['<!doctype html><meta charset="utf-8"><title>Serpentine3D vs ImportExport_3DM</title>',
         '<style>body{font-family:system-ui,sans-serif;background:#fff;margin:0;padding:16px}'
         'h1{font-size:20px} .note{color:#666;font-size:13px;margin-bottom:12px}'
         'table{border-collapse:collapse;width:100%} '
         'td{border:1px solid #ddd;vertical-align:top;text-align:center;padding:6px}'
         '.cap{font-size:12px;margin:4px 0} img{width:420px;max-width:46vw;background:#f8f8f8}'
         '.miss{color:#b00;font-size:12px;padding:60px 0;background:#fafafa}</style>',
         '<h1>Serpentine3D vs ImportExport_3DM (side by side)</h1>',
         '<div class="note">Left: FreeCAD import3DM 0.5.0 (white bg). '
         'Right: Serpentine3D 0.9.0 shaded (dark bg). Files marked \'not '
         'captured\' crashed/hung the Serpentine3D 3dm importer.</div>',
         '<table><tr><th>File</th><th>ImportExport_3DM (FreeCAD)</th>'
         '<th>Serpentine3D</th></tr>']
    for n in names:
        left = '<img src="%s/%s">' % (imp_dir, n)
        if os.path.exists(os.path.join(serp_dir, n)):
            right = '<img src="%s/%s">' % (serp_dir, n)
        else:
            right = ('<div class="miss">not captured<br>(Serpentine 3dm '
                     'importer crashed/hung on this file)</div>')
        P.append('<tr><td class="cap">%s</td><td>%s</td><td>%s</td></tr>'
                 % (html.escape(n), left, right))
    P.append('</table>')
    with open(out_html, "w") as fh:
        fh.write("\n".join(P))
    print("wrote", out_html, "rows:", len(names))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
