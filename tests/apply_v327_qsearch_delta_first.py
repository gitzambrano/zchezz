#!/usr/bin/env python3
"""Move qsearch per-move delta pruning before SEE, preserving decisions.

The original loop computes SEE first, then applies a cheap material-gain delta
bound. Both tests only reject a move and neither has side effects, while alpha
is unchanged during the scoring pass. Therefore evaluating delta first preserves
the exact searched move set/order but avoids SEE for captures already rejected
by the delta bound.
"""
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
        /* Cheap delta bound first. Alpha is constant during this scoring pass,
         * so this only avoids SEE work for moves that were already going to be
         * rejected later by the original loop. */
        uint8_t cap = b->b[moves[i].to];
        int gain = moves[i].epc ? MV_TAB[1] : cap ? MV_TAB[PC_TYPE(cap)] : 0;
        if (stand + gain + 50 < alpha && !moves[i].prom) { moves[i].score = -99999; continue; }

        /* SEE pruning: mark bad captures */
        if (!moves[i].prom && !moves[i].epc) {
            int sv = see_board(b, moves[i].from, moves[i].to, 0);
            if (sv < 0) { moves[i].score = -99999; continue; }
        }
        moves[i].score = score_move(ss, &moves[i], b, ply, qs_pv, ok_sq, -1, -1, -1);
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
    print(f"Applied qsearch delta-before-SEE to {args.source}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
