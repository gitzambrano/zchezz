#!/usr/bin/env python3
"""Apply a contextual qsearch pruning candidate to v3.25 search.c.

The transform deliberately avoids the failed fixed-delta approach. It moves
capture pruning after legality/check detection, preserves promotions, checks and
recaptures, uses a Stockfish-like futility base plus SEE relative to alpha, and
optionally limits late ordinary captures.

Defaults are useful without CLI arguments; flags only override them.
"""
from __future__ import annotations

import argparse
from pathlib import Path

SOURCE = Path("engine/c/zchezz_v325/search.c")
MOVE_LIMIT = 4
FUTILITY_MARGIN = 300
SEE_FLOOR = -75


def exact(text: str, old: str, new: str, label: str) -> str:
    n = text.count(old)
    if n != 1:
        raise RuntimeError(f"{label}: expected exactly one match, found {n}")
    return text.replace(old, new, 1)


def apply_contextual(text: str, move_limit: int, futility_margin: int, see_floor: int) -> str:
    old_scoring = """    for (int i = 0; i < n; i++) {
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

"""
    new_scoring = """    /* v3.26 contextual qsearch candidate: order every tactical move first.
     * Pruning is deferred until after legality/check detection so checking
     * captures are never discarded by a static pre-move heuristic. */
    for (int i = 0; i < n; i++)
        moves[i].score = score_move(ss, &moves[i], b, ply, qs_pv, ok_sq, -1, -1, -1);

"""
    text = exact(text, old_scoring, new_scoring, "qsearch pre-move pruning block")

    old_loop_header = """    for (int i = 0; i < n; i++) {
        /* Pick-best */
"""
    new_loop_header = f"""    int qs_searched = 0;
    int qs_prev_sq = ply > 0 ? ss->prev_to_sq[ply-1] : -1;
    for (int i = 0; i < n; i++) {{
        /* Pick-best */
"""
    text = exact(text, old_loop_header, new_loop_header, "qsearch ordered-loop header")

    old_search = """        board_make(b, &moves[i]);
        int mover_col = b->turn ^ 24;
        int king_sq   = mover_col == COL_W ? b->wk : b->bk;
        if (board_is_attacked(b, king_sq, b->turn)) { board_unmake(b); continue; }
        int sc = -qsearch(ss, b, -beta, -alpha, ply+1);
        board_unmake(b);
"""
    new_search = f"""        /* Compute static tactical context before make. En-passant keeps the
         * conservative exemption because its captured pawn is not on move.to. */
        int qs_sv = moves[i].epc ? 0 : see_board(b, moves[i].from, moves[i].to, 0);
        uint8_t qs_cap = b->b[moves[i].to];
        int qs_gain = moves[i].epc ? MV_TAB[1] : qs_cap ? MV_TAB[PC_TYPE(qs_cap)] : 0;

        board_make(b, &moves[i]);
        int mover_col = b->turn ^ 24;
        int king_sq   = mover_col == COL_W ? b->wk : b->bk;
        if (board_is_attacked(b, king_sq, b->turn)) {{ board_unmake(b); continue; }}

        int opp_king_sq = b->turn == COL_W ? b->wk : b->bk;
        int gives_check = board_is_attacked(b, opp_king_sq, mover_col);
        int is_recap = (qs_prev_sq >= 0 && moves[i].to == qs_prev_sq);

        if (!moves[i].prom && !gives_check && !is_recap) {{
            int futility_base = stand + {futility_margin};
            /* Stockfish-style contextual futility: captured material is useful
             * only when it can plausibly bridge the current alpha deficit. */
            if (futility_base + qs_gain <= alpha) {{ board_unmake(b); continue; }}

            if (!moves[i].epc) {{
                /* SEE threshold follows the alpha deficit rather than a fixed
                 * zero threshold, plus a modest absolute floor for obviously
                 * losing captures. */
                int needed_see = alpha - futility_base;
                if (qs_sv < needed_see || qs_sv < {see_floor}) {{ board_unmake(b); continue; }}
            }}

            /* Move-count pruning is applied only to ordinary non-checking,
             * non-promotion, non-recapture captures and only after several
             * better tactical moves have actually been searched. */
            if (qs_searched >= {move_limit}) {{ board_unmake(b); continue; }}
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
    ap.add_argument("--futility-margin", type=int, default=FUTILITY_MARGIN)
    ap.add_argument("--see-floor", type=int, default=SEE_FLOOR)
    args = ap.parse_args()
    if args.move_limit < 1:
        raise SystemExit("--move-limit must be >= 1")
    before = args.source.read_text(encoding="utf-8")
    after = apply_contextual(before, args.move_limit, args.futility_margin, args.see_floor)
    args.source.write_text(after, encoding="utf-8")
    print(
        f"applied contextual qsearch to {args.source}: "
        f"move_limit={args.move_limit} futility_margin={args.futility_margin} see_floor={args.see_floor}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
