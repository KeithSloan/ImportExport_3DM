#!/usr/bin/env python3
"""Capture each remaining file in its OWN Serpentine3D instance.

A hang/crash in one file's import only costs that file (instance is killed
after the attempt), which is how we get round Serpentine's .3dm importer hangs
(e.g. v5_ring, v5_teacup).  Run from the repo root; the Serpentine GUI must not
already be running (we launch our own instances and kill them)."""
import json, socket, glob, os, time, subprocess, sys

SERP = os.path.expanduser('~/github/Serpentine3D/.venv/bin/serp3d')
PORTFILE = os.path.expanduser('~/.serpentine3d/rpc.port')
WIKI = '/Users/ksloan/Workbenches/ImportExport_3DM.wiki/images'
S = '/Users/ksloan/Workbenches/ImportExport_3DM/sample_scan'
OUT = '/tmp/ie3dm/serp_shot'
BADPATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'serp_bad.txt')
HERE = os.path.dirname(os.path.abspath(__file__))
os.makedirs(OUT, exist_ok=True)

src = {}
for f in glob.glob(S + '/**/*.3dm', recursive=True):
    stem = os.path.splitext(os.path.basename(f))[0]
    src[stem] = f; src[stem.replace(' ', '_')] = f
jobs = []
for p in sorted(glob.glob(WIKI + '/*.png')):
    stem = os.path.splitext(os.path.basename(p))[0]
    jobs.append((stem + '.png', src[stem]))
jobs.append(('v5_ring.png', src['v5_ring']))

bad = [l.strip() for l in open(BADPATH) if l.strip()]

def rpc_call(port, method, params=None, timeout=90):
    s = socket.create_connection(('127.0.0.1', port), timeout=timeout)
    s.settimeout(timeout)
    s.sendall((json.dumps({'method': method, 'params': params or {}, 'id': 1}) + '\n').encode())
    buf = b''
    while True:
        c = s.recv(65536)
        if not c: break
        buf += c
        if buf.endswith(b'\n') and (b'"result"' in buf or b'"error"' in buf): break
    s.close()
    try:
        return json.loads(buf)
    except Exception:
        return {'error': 'bad response'}

def launch(portfile):
    if os.path.exists(portfile):
        try: os.unlink(portfile)
        except Exception: pass
    env = dict(os.environ)
    env['SERP3D_NO_UPDATE_CHECK'] = '1'
    env['PYOPENGL_PLATFORM'] = 'cgl'
    proc = subprocess.Popen([SERP], env=env,
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    for _ in range(60):
        time.sleep(1)
        if not os.path.exists(portfile):
            continue
        try:
            port = int(open(portfile).read().strip())
            r = rpc_call(port, 'scene_info', timeout=6)
            if not r.get('error'):
                return proc, port
        except Exception:
            continue
    try: proc.kill()
    except Exception: pass
    return None, None

def mark_bad(nm):
    if nm not in bad:
        bad.append(nm)
        open(BADPATH, 'w').write('\n'.join(bad) + '\n')

log = open('/tmp/ie3dm/cap_isolated.log', 'a')
todo = [j for j in jobs
        if not os.path.exists(os.path.join(OUT, j[0])) and j[0] not in bad]
log.write('ISOLATED start, todo=%d %s\n' % (len(todo), [j[0] for j in todo]))
log.flush()
for nm, path in todo:
    ok = False
    proc, port = launch(PORTFILE)
    if proc is None:
        log.write('launch-fail %s\n' % nm); log.flush()
        mark_bad(nm)
        continue
    try:
        r = rpc_call(port, 'command', {'command': 'new', 'inputs': ['Yes']}, timeout=60)
        if not r.get('error'):
            r = rpc_call(port, 'import_file', {'path': path}, timeout=90)
            if not r.get('error'):
                rpc_call(port, 'set_viewport', {'view': 'isometric',
                                                'display_mode': 'shaded',
                                                'zoom_extents': True,
                                                'grid': False}, timeout=30)
                r = rpc_call(port, 'screenshot',
                             {'path': os.path.join(OUT, nm), 'width': 480,
                              'height': 360}, timeout=60)
                ok = (not r.get('error')
                      and os.path.exists(os.path.join(OUT, nm)))
    except Exception as e:
        log.write('exc %s %r\n' % (nm, e)); log.flush()
    finally:
        try: proc.kill()
        except Exception: pass
        time.sleep(2)
    if ok:
        log.write('ok %s\n' % nm); log.flush()
    else:
        log.write('fail %s\n' % nm); log.flush()
        mark_bad(nm)
log.write('ISOLATED done\n'); log.flush(); log.close()
print('DONE')
