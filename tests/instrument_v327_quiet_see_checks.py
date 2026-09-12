#!/usr/bin/env python3
"""Count quiet SEE-pruned moves that actually give check, without changing decisions."""
from __future__ import annotations

import argparse
from pathlib import Path

SOURCE = Path("engine/c/zchezz_v326/search.c")

DECL = r'''

/* QUIET_SEE_CHECK_DIAGNOSTICS: observe only; preserve pruning decisions. */
static unsigned long long g_qsee_pruned;
static unsigned long long g_qsee_pruned_check;
static unsigned long long g_qsee_pruned_discovered_check;
static void qsee_check_diag_report(void) {
    fprintf(stderr,
        "[QSEE_CHECK_DIAG] pruned=%llu actual_check=%llu discovered_check=%llu\n",
        g_qsee_pruned, g_qsee_pruned_check, g_qsee_pruned_discovered_check);
}
#if defined(__GNUC__) || defined(__clang__)
__attribute__((constructor))
#endif
static void qsee_check_diag_register(void) { atexit(qsee_check_diag_report); }
'''

OLD = '''                if (!in_check && !is_pv && legal_count > 0 && depth <= 4 &&
                    !is_killer &&
                    !(cur_prev_ft >= 0 && ss->counter_move[cur_prev_ft] == (mfr*64+mto)) &&
                    !quiet_direct_check(b, mfr, mto)) {
                    if (see_board(b, mfr, mto, 0) < -(depth * 60)) continue;
                }
'''

NEW = '''                if (!in_check && !is_pv && legal_count > 0 && depth <= 4 &&
                    !is_killer &&
                    !(cur_prev_ft >= 0 && ss->counter_move[cur_prev_ft] == (mfr*64+mto)) &&
                    !quiet_direct_check(b, mfr, mto)) {
                    if (see_board(b, mfr, mto, 0) < -(depth * 60)) {
                        /* Diagnostic only: inspect the move we are about to prune,
                         * then restore the board and make the exact same continue. */
                        g_qsee_pruned++;
                        board_make(b, m);
                        int mover_col_qs = b->turn ^ 24;
                        int king_sq_qs = mover_col_qs == COL_W ? b->wk : b->bk;
                        int legal_qs = !board_is_attacked(b, king_sq_qs, b->turn);
                        int actual_check_qs = legal_qs ? board_in_check(b) : 0;
                        board_unmake(b);
                        if (actual_check_qs) {
                            g_qsee_pruned_check++;
                            /* The direct-check helper was false by construction,
                             * therefore every actual check here is discovered. */
                            g_qsee_pruned_discovered_check++;
                        }
                        continue;
                    }
                }
'''


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--source", type=Path, default=SOURCE)
    args = ap.parse_args()
    text = args.source.read_text(encoding="utf-8")
    inc = '#include <time.h>\n'
    if text.count(inc) != 1:
        raise RuntimeError("expected one time.h include")
    text = text.replace(inc, inc + DECL, 1)
    count = text.count(OLD)
    if count != 1:
        raise RuntimeError(f"expected one quiet SEE block, found {count}")
    args.source.write_text(text.replace(OLD, NEW, 1), encoding="utf-8")
    print(f"Instrumented quiet SEE discovered-check pruning in {args.source}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
