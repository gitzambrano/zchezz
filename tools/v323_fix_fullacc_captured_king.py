#!/usr/bin/env python3
"""Keep v3.23 compact king state exact even on illegal king-capture test trees.

Legal chess never captures a king, but robustness/parity tests may feed illegal
FENs. v3.22's recompute path treats a missing king as distance 0, so fullacc
must also mark a captured king square as 255 and refresh king distance.
"""
from __future__ import annotations
import argparse
from pathlib import Path

OLD = r'''                if (cpt == 0) {
                    if (PC_COLOR(cap) == COL_W) dst->pawns_w &= ~tm;
                    else                        dst->pawns_b &= ~tm;
                    pawn_changed = 1;
                }
                changed = 1;
'''
NEW = r'''                if (cpt == 0) {
                    if (PC_COLOR(cap) == COL_W) dst->pawns_w &= ~tm;
                    else                        dst->pawns_b &= ~tm;
                    pawn_changed = 1;
                } else if (cpt == 5) {
                    if (PC_COLOR(cap) == COL_W) dst->king_w = 255;
                    else                        dst->king_b = 255;
                    king_changed = 1;
                }
                changed = 1;
'''

def main():
    ap=argparse.ArgumentParser(); ap.add_argument('--root',type=Path,required=True); a=ap.parse_args()
    p=a.root/'nnue.c'; t=p.read_text(encoding='utf-8')
    if t.count(OLD)!=1: raise SystemExit(f'captured-king anchor count={t.count(OLD)}')
    p.write_text(t.replace(OLD,NEW,1),encoding='utf-8')
    print('patched captured-king compact state')
if __name__=='__main__': main()
