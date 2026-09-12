#!/usr/bin/env python3
"""Improve TT use for in-check qsearch without changing its tactical move set."""
from __future__ import annotations
import argparse
from pathlib import Path

SOURCE=Path('engine/c/zchezz_v326/search.c')
ORDER_OLD='''        sort_moves(ss, moves, n, b, ply, NULL, ok_sq, -1, -1, -1);
'''
ORDER_NEW='''        const Move *qs_check_pv = (qs_tt_move.from || qs_tt_move.to) ? &qs_tt_move : NULL;
        sort_moves(ss, moves, n, b, ply, qs_check_pv, ok_sq, -1, -1, -1);
'''
CUTOFF_OLD='''            if (alpha >= beta) {
                return beta;
            }
'''
CUTOFF_NEW='''            if (alpha >= beta) {
                if (!ss->time_up)
                    tt_store(b->hash, beta, 0, TT_LOWER, &moves[i], ply, TT_EVAL_NONE);
                return beta;
            }
'''

def exact(text,old,new,label):
    n=text.count(old)
    if n!=1: raise RuntimeError(f'{label}: expected one match, found {n}')
    return text.replace(old,new,1)

def main()->int:
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--candidate',choices=('order','order-cutoff'),required=True);ap.add_argument('--source',type=Path,default=SOURCE);a=ap.parse_args()
    text=a.source.read_text(encoding='utf-8')
    text=exact(text,ORDER_OLD,ORDER_NEW,'in-check qsearch TT ordering')
    if a.candidate=='order-cutoff': text=exact(text,CUTOFF_OLD,CUTOFF_NEW,'in-check qsearch TT cutoff store')
    a.source.write_text(text,encoding='utf-8');print(f'Applied {a.candidate} to {a.source}');return 0

if __name__=='__main__':raise SystemExit(main())
