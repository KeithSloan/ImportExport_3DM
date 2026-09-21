
import os, sys, glob, signal, multiprocessing
os.environ["QT_QPA_PLATFORM"]="offscreen"

def sum_area(doc, geo):
    a=0.0
    for o in doc.objects():
        try: a+=geo.surface_area(o.shape)
        except Exception: pass
    return a

def main():
    from serpentine3d.scripting import Document
    from serpentine3d.core import geometry as geo
    class TO(Exception): pass
    def _to(s,f): raise TO()
    signal.signal(signal.SIGALRM,_to)
    root="/Users/ksloan/github/CAD_Files_Git/3DM/example_3dm_files_20181010"
    tsv="/Users/ksloan/github/CAD_Files_Git/3DM/serp_sweep.tsv"
    files=sorted(glob.glob(root+"/*/*.3dm"))
    with open(tsv,"w") as out:
        out.write("# file\tnobj\tarea\n"); out.flush()
        for f in files:
            rel=f.split("example_3dm_files_20181010/")[1]
            signal.alarm(120)
            try:
                doc=Document(); n=doc.import_(f)
                out.write(f"{rel}\t{n}\t{sum_area(doc,geo):.4f}\n"); out.flush()
            except TO:
                out.write(f"{rel}\tTIMEOUT\t\n"); out.flush()
            except Exception as e:
                out.write(f"{rel}\tERR\t{str(e)[:60]}\n"); out.flush()
            finally:
                signal.alarm(0)
        out.write("# DONE\n")

if __name__=="__main__":
    multiprocessing.freeze_support()
    main()
