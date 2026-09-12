#!/usr/bin/env python3
"""Reuse qsearch SEE results when scoring captures, preserving search decisions."""
from __future__ import annotations

import argparse
from pathlib import Path

SOURCE=Path('engine/c/zchezz_v326/search.c')
OLD='''    for (int i = 0; i < n; i++) {
        /* SEE pruning: mark bad captures */
        if (!moves[i].prom && !moves[i].epc) {
            int sv = see_board(b, moves[i].from, moves[i].to, 0);
            if (sv < 0) { moves[i].score = -99999; continue; }
        }
        /* Delta pruning per move */
        uint8_t cap = b->b[moves[i].to];
        int gain = moves[i].epc ? MV_TAB[1] : cap ? MV_TAB[PC_TYPE(cap)] : 0;
        if (stand + gain + 50 < alpha && !moves[i].prom) { moves[i].score = -99999; continue; }
        moves[i].score = score_move(ss, &moves[i], b, ply, qs_pv, ok_sq, -1, -1, -1);
    }
'''
NEW='''    for (int i = 0; i < n; i++) {
        int qs_sv = 0, qs_have_sv = 0;
        /* SEE pruning: mark bad captures. Keep the result for scoring below. */
        if (!moves[i].prom && !moves[i].epc) {
            qs_sv = see_board(b, moves[i].from, moves[i].to, 0);
            qs_have_sv = 1;
            if (qs_sv < 0) { moves[i].score = -99999; continue; }
        }
        /* Delta pruning per move */
        uint8_t cap = b->b[moves[i].to];
        int gain = moves[i].epc ? MV_TAB[1] : cap ? MV_TAB[PC_TYPE(cap)] : 0;
        if (stand + gain + 50 < alpha && !moves[i].prom) { moves[i].score = -99999; continue; }

        /* Normal qsearch captures have already paid for SEE above. Reproduce
         * score_move() exactly here so attacker>victim captures do not call
         * see_board() a second time. Promotions/EP keep the generic scorer. */
        if (qs_have_sv) {
            int mfr=moves[i].from, mto=moves[i].to;
            if (qs_pv && mfr==qs_pv->from && mto==qs_pv->to) {
                moves[i].score = 2000000;
            } else {
                int victim=PC_TYPE(cap);
                int attacker=PC_TYPE(b->b[mfr]);
                if (MV_TAB[attacker] <= MV_TAB[victim])
                    moves[i].score = 1600000 + 1000 + MVV_LVA[victim*7+attacker];
                else
                    moves[i].score = 1600000 + qs_sv*10 + MVV_LVA[victim*7+attacker];
            }
        } else {
            moves[i].score = score_move(ss, &moves[i], b, ply, qs_pv, ok_sq, -1, -1, -1);
        }
    }
'''

def main()->int:
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--source',type=Path,default=SOURCE);a=ap.parse_args()
    text=a.source.read_text(encoding='utf-8')
    if text.count(OLD)!=1: raise RuntimeError(f'expected one qsearch scoring loop, found {text.count(OLD)}')
    a.source.write_text(text.replace(OLD,NEW,1),encoding='utf-8');print(f'Applied qsearch SEE reuse to {a.source}');return 0

if __name__=='__main__':raise SystemExit(main())
