#!/usr/bin/env python3
from __future__ import annotations
import argparse, shutil
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]
SRC=ROOT/"engine"/"c"/"zchezz_v330"
VARIANTS=("iir4","badlmr_early","badlmr2","lmp80_hist96","lmp80_qsee50")

def repl(s,old,new,expected=1):
    n=s.count(old)
    if n!=expected:
        raise RuntimeError(f"expected {expected}, found {n}: {old!r}")
    return s.replace(old,new)

def patch_one(s,v):
    if v=="iir4":
        return repl(s,
            "if (!pv_move.from && !pv_move.to && depth>=3 && !in_check && depth-1>=2) depth--;",
            "if (!pv_move.from && !pv_move.to && depth>=4 && !in_check && depth-1>=2) depth--;")
    if v=="badlmr_early":
        return repl(s,"depth>=3 && legal_count>=4 && !in_check",
                      "depth>=3 && legal_count>=3 && !in_check",2)
    if v=="badlmr2":
        return repl(s,"if (m->score >= 100000 && m->score <= 200000) reduce = 1;",
                      "if (m->score >= 100000 && m->score <= 200000) reduce = depth >= 6 ? 2 : 1;",2)
    if v=="lmp80":
        return repl(s,"static const int lmp_limit[8] = {0,12,22,32,44,58,74,94};",
                      "static const int lmp_limit[8] = {0,10,18,26,36,46,60,76};")
    if v=="hist96":
        return repl(s,"int hp_thresh = -64 * depth;","int hp_thresh = -96 * depth;")
    if v=="qsee50":
        return repl(s,"see_board(b, mfr, mto, 0) < -(depth * 60)",
                      "see_board(b, mfr, mto, 0) < -(depth * 50)")
    raise ValueError(v)

def patch(s,v):
    if v=="lmp80_hist96":
        return patch_one(patch_one(s,"lmp80"),"hist96")
    if v=="lmp80_qsee50":
        return patch_one(patch_one(s,"lmp80"),"qsee50")
    return patch_one(s,v)

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--variant",choices=VARIANTS,required=True)
    ap.add_argument("--out",required=True)
    a=ap.parse_args()
    out=Path(a.out).resolve()
    if out.exists(): shutil.rmtree(out)
    shutil.copytree(SRC,out)
    p=out/"search.c"
    p.write_text(patch(p.read_text(encoding="utf-8"),a.variant),encoding="utf-8")
    print(f"materialized v3.30 + {a.variant}: {out}")
    return 0

if __name__=="__main__":
    raise SystemExit(main())
