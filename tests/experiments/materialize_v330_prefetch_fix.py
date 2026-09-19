#!/usr/bin/env python3
from __future__ import annotations
import argparse, shutil
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]
SRC=ROOT/"engine"/"c"/"zchezz_v330"

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--out",required=True)
    a=ap.parse_args()
    out=Path(a.out).resolve()
    if out.exists(): shutil.rmtree(out)
    shutil.copytree(SRC,out)
    p=out/"search.c"
    s=p.read_text(encoding="utf-8")
    old="tt_prefetch(b->hash ^ ZR_side);"
    n=s.count(old)
    if n != 4:
        raise RuntimeError(f"expected 4 child TT prefetches, found {n}")
    s=s.replace(old,"tt_prefetch(b->hash);")
    p.write_text(s,encoding="utf-8")
    print("materialized v3.30 child-hash prefetch fix")
    return 0

if __name__=="__main__":
    raise SystemExit(main())
