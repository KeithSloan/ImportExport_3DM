#!/usr/bin/env python3
import json, socket, glob, os
PORT=int(open('/Users/ksloan/.serpentine3d/rpc.port').read().strip())
BAD=[l.strip() for l in open('/tmp/ie3dm/serp_bad.txt') if l.strip()]
def call(method, params=None, timeout=25):
    try:
        s=socket.create_connection(('127.0.0.1',PORT),timeout=timeout); s.settimeout(timeout)
        s.sendall((json.dumps({'method':method,'params':params or {},'id':1})+'\n').encode())
        buf=b''
        while True:
            c=s.recv(65536)
            if not c: break
            buf+=c
            if buf.endswith(b'\n'): break
        s.close()
        return json.loads(buf)
    except Exception as e:
        return {'error':'IO %r'%(e,)}
WIKI='/Users/ksloan/Workbenches/ImportExport_3DM.wiki/images'
S='/Users/ksloan/Workbenches/ImportExport_3DM/sample_scan'
OUT='/tmp/ie3dm/serp_shot'
os.makedirs(OUT, exist_ok=True)
src={}
for f in glob.glob(S+'/**/*.3dm', recursive=True):
    stem=os.path.splitext(os.path.basename(f))[0]
    src[stem]=f; src[stem.replace(' ','_')]=f
jobs=[]
for p in sorted(glob.glob(WIKI+'/*.png')):
    stem=os.path.splitext(os.path.basename(p))[0]
    jobs.append((stem+'.png', src[stem]))
jobs.append(('v5_ring.png', src['v5_ring']))
def save_bad():
    open('/tmp/ie3dm/serp_bad.txt','w').write('\n'.join(BAD)+'\n')
log=open('/tmp/ie3dm/cap_pass.log','a')
ok=err=0
for nm,path in jobs:
    if os.path.exists(os.path.join(OUT,nm)) or nm in BAD: continue
    r=call('command',{'command':'new','inputs':['Yes']})
    if r.get('error'):
        log.write('IOBREAK new %s (%s)\n'%(nm,str(r['error'])[:60])); log.flush(); break
    r=call('import_file',{'path':path})
    if r.get('error'):
        msg=r['error']
        if not isinstance(msg,str):
            BAD.append(nm); save_bad()
            log.write('CRASH imp %s marked-bad (%r)\n'%(nm,msg)); log.flush(); break
        if msg.startswith('IO'):
            BAD.append(nm); save_bad()
            log.write('CRASH imp %s marked-bad (%s)\n'%(nm,msg)); log.flush(); break
        # deterministic import bug (ApiError like "Import failed: Add(): ...")
        BAD.append(nm); save_bad()
        log.write('BAD imp %s (%s)\n'%(nm,msg[:70])); log.flush(); err+=1; continue
    call('set_viewport',{'view':'isometric','display_mode':'shaded','zoom_extents':True,'grid':False})
    r=call('screenshot',{'path':os.path.join(OUT,nm),'width':480,'height':360})
    if r.get('error'):
        msg=r['error']
        if not isinstance(msg,str) or msg.startswith('IO'):
            BAD.append(nm); save_bad()
            log.write('CRASH shot %s marked-bad (%r)\n'%(nm,msg)); log.flush(); break
        log.write('ERR shot %s (%s)\n'%(nm,str(msg)[:70])); log.flush(); err+=1
    else:
        ok+=1
log.write('pass end ok=%d err=%d bad=%d\n'%(ok,err,len(BAD))); log.flush(); log.close()
print('PASSEND ok',ok,'err',err)
