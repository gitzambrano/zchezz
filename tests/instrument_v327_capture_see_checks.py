#!/usr/bin/env python3
"""Observe legal checking captures discarded by the promoted capture-SEE gate.

The instrumentation preserves every pruning decision.  Immediately before the
existing distance-based `continue`, it temporarily makes the move, verifies
legality and whether the resulting position checks the opponent king, then
unmakes it and executes the same continue.
"""
from __future__ import annotations

import argparse
import re
from pathlib import Path

SOURCE = Path("engine/c/zchezz_v326/search.c")

DECL = r'''

/* CAPTURE_SEE_CHECK_DIAGNOSTICS: observe only; preserve pruning decisions. */
static unsigned long long g_capsee_pruned;
static unsigned long long g_capsee_pruned_legal;
static unsigned long long g_capsee_pruned_check;
static void capsee_check_diag_report(void) {
    fprintf(stderr,
        "[CAPSEE_CHECK_DIAG] pruned=%llu legal=%llu actual_check=%llu\n",
        g_capsee_pruned, g_capsee_pruned_legal, g_capsee_pruned_check);
}
#if defined(__GNUC__) || defined(__clang__)
__attribute__((constructor))
#endif
static void capsee_check_diag_register(void) { atexit(capsee_check_diag_report); }
'''

PAT = re.compile(r'''(?P<indent>\s*)if \(\(dr>dc\?dr:dc\) > 1\) continue;''')


def repl(m: re.Match[str]) -> str:
    i = m.group('indent')
    return f'''{i}if ((dr>dc?dr:dc) > 1) {{
{i}    g_capsee_pruned++;
{i}    board_make(b, m);
{i}    int mover_col_cs = b->turn ^ 24;
{i}    int king_sq_cs = mover_col_cs == COL_W ? b->wk : b->bk;
{i}    int legal_cs = !board_is_attacked(b, king_sq_cs, b->turn);
{i}    int actual_check_cs = legal_cs ? board_in_check(b) : 0;
{i}    board_unmake(b);
{i}    if (legal_cs) g_capsee_pruned_legal++;
{i}    if (actual_check_cs) g_capsee_pruned_check++;
{i}    continue;
{i}}}'''


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--source", type=Path, default=SOURCE)
    args = ap.parse_args()
    s = args.source.read_text(encoding="utf-8")
    inc = '#include <time.h>\n'
    if s.count(inc) != 1:
        raise RuntimeError('expected one time.h include')
    s = s.replace(inc, inc + DECL, 1)
    s, n = PAT.subn(repl, s)
    if n < 1:
        raise RuntimeError('capture SEE distance guard not found')
    args.source.write_text(s, encoding='utf-8')
    print(f'Instrumented {n} capture SEE distance guard(s)')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
