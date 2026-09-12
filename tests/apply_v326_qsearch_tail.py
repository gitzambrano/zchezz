#!/usr/bin/env python3
"""Apply conservative qsearch tail move-count pruning to v3.25 search.c.

This keeps the existing SEE>=0 and per-move delta filters intact. It only
prunes late surviving captures after legality is known, while preserving
promotions, recaptures, and checking moves. Defaults work without CLI flags.
"""
from __future__ import annotations

import argparse
from pathlib import Path

SOURCE = Path("engine/c/zchezz_v325/search.c")
MOVE_LIMIT = 6


def exact(text: str, old: str, new: str, label: str) -> str:
    n = text.count(old)
    if n != 1:
        raise RuntimeError(f"{label}: expected exactly one match, found {n}")
    return text.replace(old, new, 1)


def apply_tail(text: str, move_limit: int) -> str:
    old_header = """    for (int i = 0; i < n; i++) {
        /* Pick-best */
"""
    new_header = """    int qs_searched = 0;
    int qs_prev_sq = ply > 0 ? ss->prev_to_sq[ply-1] : -1;
    for (int i = 0; i < n; i++) {
        /* Pick-best */
"""
    text = exact(text, old_header, new_header, "qsearch ordered-loop header")

    old_search = """        board_make(b, &moves[i]);
        int mover_col = b->turn ^ 24;
        int king_sq   = mover_col == COL_W ? b->wk : b->bk;
        if (board_is_attacked(b, king_sq, b->turn)) { board_unmake(b); continue; }
        int sc = -qsearch(ss, b, -beta, -alpha, ply+1);
        board_unmake(b);
"""
    new_search = f"""        board_make(b, &moves[i]);
        int mover_col = b->turn ^ 24;
        int king_sq   = mover_col == COL_W ? b->wk : b->bk;
        if (board_is_attacked(b, king_sq, b->turn)) {{ board_unmake(b); continue; }}

        /* v3.26 candidate: only trim the tail that already survived the
         * existing SEE and delta filters. Promotions and recaptures are
         * always searched. For late ordinary captures, preserve checks by
         * verifying the opponent king after make before pruning. */
        if (qs_searched >= {move_limit} && !moves[i].prom && moves[i].to != qs_prev_sq) {{
            int opp_king_sq = b->turn == COL_W ? b->wk : b->bk;
            if (!board_is_attacked(b, opp_king_sq, mover_col)) {{
                board_unmake(b);
                continue;
            }}
        }}

        ss->prev_ft[ply] = moves[i].from * 64 + moves[i].to;
        ss->prev_to_sq[ply] = moves[i].to;
        qs_searched++;
        int sc = -qsearch(ss, b, -beta, -alpha, ply+1);
        board_unmake(b);
"""
    return exact(text, old_search, new_search, "qsearch recursive-search block")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--source", type=Path, default=SOURCE)
    ap.add_argument("--move-limit", type=int, default=MOVE_LIMIT)
    args = ap.parse_args()
    if args.move_limit < 1:
        raise SystemExit("--move-limit must be >= 1")
    before = args.source.read_text(encoding="utf-8")
    after = apply_tail(before, args.move_limit)
    args.source.write_text(after, encoding="utf-8")
    print(f"applied qsearch tail pruning to {args.source}: move_limit={args.move_limit}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
