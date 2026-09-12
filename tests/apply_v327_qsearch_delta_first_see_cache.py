#!/usr/bin/env python3
"""Combine qsearch delta-before-SEE with SEE reuse, preserving decisions exactly."""
from __future__ import annotations

import argparse
from pathlib import Path

SOURCE = Path("engine/c/zchezz_v326/search.c")

OLD = '''    for (int i = 0; i < n; i++) {
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

NEW = '''    for (int i = 0; i < n; i++) {
        /* Cheap delta bound first. Alpha is unchanged during this scoring pass. */
        uint8_t cap = b->b[moves[i].to];
        int gain = moves[i].epc ? MV_TAB[1] : cap ? MV_TAB[PC_TYPE(cap)] : 0;
        if (stand + gain + 50 < alpha && !moves[i].prom) { moves[i].score = -99999; continue; }

        int qs_sv = 0, qs_have_sv = 0;
        if (!moves[i].prom && !moves[i].epc) {
            qs_sv = see_board(b, moves[i].from, moves[i].to, 0);
            qs_have_sv = 1;
            if (qs_sv < 0) { moves[i].score = -99999; continue; }
        }

        /* Reproduce score_move() exactly for normal captures, reusing SEE. */
        if (qs_have_sv) {
            int mfr = moves[i].from, mto = moves[i].to;
            if (qs_pv && mfr == qs_pv->from && mto == qs_pv->to) {
                moves[i].score = 2000000;
            } else {
                int victim = PC_TYPE(cap);
                int attacker = PC_TYPE(b->b[mfr]);
                if (MV_TAB[attacker] <= MV_TAB[victim])
                    moves[i].score = 1600000 + 1000 + MVV_LVA[victim*7 + attacker];
                else
                    moves[i].score = 1600000 + qs_sv*10 + MVV_LVA[victim*7 + attacker];
            }
        } else {
            /* Promotions and en-passant retain the generic scorer. */
            moves[i].score = score_move(ss, &moves[i], b, ply, qs_pv, ok_sq, -1, -1, -1);
        }
    }
'''


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--source", type=Path, default=SOURCE)
    args = ap.parse_args()
    text = args.source.read_text(encoding="utf-8")
    count = text.count(OLD)
    if count != 1:
        raise RuntimeError(f"expected one qsearch scoring loop, found {count}")
    args.source.write_text(text.replace(OLD, NEW, 1), encoding="utf-8")
    print(f"Applied qsearch delta-first + SEE reuse to {args.source}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
