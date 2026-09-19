#!/usr/bin/env python3
"""Materialize v3.30 candidates promoted from short search screens."""
from __future__ import annotations
import argparse, shutil
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]
SRC=ROOT/"engine"/"c"/"zchezz_v330"
VARIANTS=("lmp80","hist96","qsee50","fut165","histgravity")

def repl(s,old,new,expected=1):
    n=s.count(old)
    if n!=expected: raise RuntimeError(f"expected {expected}, found {n}: {old!r}")
    return s.replace(old,new)

def add_gravity(s):
    marker='static inline uint32_t pawn_corr_key(const Board *b) {'
    helper='''static inline int32_t hist_gravity(int32_t cur, int bonus) {
    if (bonus > 16384) bonus = 16384;
    if (bonus < -16384) bonus = -16384;
    int mag = bonus < 0 ? -bonus : bonus;
    int next = cur + bonus - (cur * mag) / 16384;
    if (next > 16384) next = 16384;
    if (next < -16384) next = -16384;
    return next;
}

'''
    s=repl(s,marker,helper+marker)
    old='''            /* Reward the cutoff move in all history tables */
            int ft = mfr*64+mto;
            {   int h = ss->mv_history[ft] + bonus;
                ss->mv_history[ft] = h < 16384 ? h : 16384; }
            if (cmh0 >= 0) {
                int c = ss->cont_hist[0][cmh0][ft] + bonus;
                ss->cont_hist[0][cmh0][ft] = (int16_t)(c < 16384 ? c : 16384);
            }
            if (cmh1 >= 0) {
                int c = ss->cont_hist[1][cmh1][ft] + bonus;
                ss->cont_hist[1][cmh1][ft] = (int16_t)(c < 16384 ? c : 16384);
            }

            /* Penalise all quiet moves that were searched before the cutoff
             * move but failed to produce a cutoff themselves.  This teaches
             * the engine that these moves are relatively weaker in this context. */
            for (int j = 0; j < n_searched_quiets; j++) {
                Move *pm = &searched_quiets[j];
                if (pm->from == mfr && pm->to == mto) continue;
                int pft = pm->from*64 + pm->to;
                {   int h = ss->mv_history[pft] - bonus;
                    ss->mv_history[pft] = h > -16384 ? h : -16384; }
                if (cmh0 >= 0) {
                    int c = ss->cont_hist[0][cmh0][pft] - bonus;
                    ss->cont_hist[0][cmh0][pft] = (int16_t)(c > -16384 ? c : -16384);
                }
                if (cmh1 >= 0) {
                    int c = ss->cont_hist[1][cmh1][pft] - bonus;
                    ss->cont_hist[1][cmh1][pft] = (int16_t)(c > -16384 ? c : -16384);
                }
            }'''
    new='''            /* Gravity updates keep history responsive instead of pinning at saturation. */
            int ft = mfr*64+mto;
            ss->mv_history[ft] = hist_gravity(ss->mv_history[ft], bonus);
            if (cmh0 >= 0)
                ss->cont_hist[0][cmh0][ft] = (int16_t)hist_gravity(ss->cont_hist[0][cmh0][ft], bonus);
            if (cmh1 >= 0)
                ss->cont_hist[1][cmh1][ft] = (int16_t)hist_gravity(ss->cont_hist[1][cmh1][ft], bonus);

            for (int j = 0; j < n_searched_quiets; j++) {
                Move *pm = &searched_quiets[j];
                if (pm->from == mfr && pm->to == mto) continue;
                int pft = pm->from*64 + pm->to;
                ss->mv_history[pft] = hist_gravity(ss->mv_history[pft], -bonus);
                if (cmh0 >= 0)
                    ss->cont_hist[0][cmh0][pft] = (int16_t)hist_gravity(ss->cont_hist[0][cmh0][pft], -bonus);
                if (cmh1 >= 0)
                    ss->cont_hist[1][cmh1][pft] = (int16_t)hist_gravity(ss->cont_hist[1][cmh1][pft], -bonus);
            }'''
    return repl(s,old,new)

def patch(s,v):
    if v=="lmp80":
        return repl(s,"static const int lmp_limit[8] = {0,12,22,32,44,58,74,94};",
                      "static const int lmp_limit[8] = {0,10,18,26,36,46,60,76};")
    if v=="hist96":
        return repl(s,"int hp_thresh = -64 * depth;","int hp_thresh = -96 * depth;")
    if v=="qsee50":
        return repl(s,"see_board(b, mfr, mto, 0) < -(depth * 60)",
                      "see_board(b, mfr, mto, 0) < -(depth * 50)")
    if v=="fut165":
        return repl(s,"static const int fut_base[9] = {0,150,300,450,600,750,900,1050,1200};",
                      "static const int fut_base[9] = {0,165,330,495,660,825,990,1155,1320};")
    if v=="histgravity":
        return add_gravity(s)
    raise ValueError(v)

def main():
    ap=argparse.ArgumentParser(); ap.add_argument("--variant",choices=VARIANTS,required=True); ap.add_argument("--out",required=True)
    a=ap.parse_args(); out=Path(a.out).resolve()
    if out.exists(): shutil.rmtree(out)
    shutil.copytree(SRC,out)
    p=out/"search.c"; p.write_text(patch(p.read_text(encoding="utf-8"),a.variant),encoding="utf-8")
    print(f"materialized v3.30 + {a.variant}: {out}")
    return 0
if __name__=="__main__": raise SystemExit(main())
