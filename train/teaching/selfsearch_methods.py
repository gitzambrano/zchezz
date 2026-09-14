"""Self-search teaching methods for generic UCI engines.

The robust path in this module does not rely on MultiPV.  It first evaluates
all legal child positions cheaply, then searches only the best root candidates
one by one.  This works even when an engine's MultiPV implementation emits only
one usable PV through the generic backend.
"""
from __future__ import annotations

import chess

from .format import (
    FLAG_DEEP_REFINED,
    FLAG_POLICY,
    FLAG_SEARCH_REFINED,
    METHOD_DEEP_SEARCH,
    METHOD_SHALLOW_SEARCH,
    METHOD_STATIC_POLICY,
)
from .methods import TeachingContext, register


def _better_key(cp_white: int, parent_white: bool) -> int:
    return int(cp_white) if parent_white else -int(cp_white)


@register("search_policy_all")
def search_policy_all(ctx: TeachingContext) -> None:
    """Legacy direct-MultiPV self teacher; retained for diagnostics."""
    lines = ctx.backend.search(
        ctx.fen,
        bool(ctx.board.turn),
        nodes=int(ctx.cfg.SHALLOW_NODES),
        multipv=int(ctx.cfg.SEARCH_MULTIPV),
    )
    if not lines:
        return

    ctx.search_cp = int(lines[0].cp_white)
    ctx.search_nodes = int(ctx.cfg.SHALLOW_NODES)
    ctx.moves = [
        {
            "uci": line.move,
            "static_cp": None,
            "search_cp": int(line.cp_white),
            "rank_static": 65535,
            "rank_search": rank,
        }
        for rank, line in enumerate(lines)
    ]
    ctx.flags |= FLAG_POLICY | FLAG_SEARCH_REFINED | FLAG_DEEP_REFINED
    ctx.methods |= METHOD_SHALLOW_SEARCH | METHOD_DEEP_SEARCH


@register("root_probe_policy")
def root_probe_policy(ctx: TeachingContext) -> None:
    """Produce robust move targets without relying on engine MultiPV.

    1. Evaluate every legal child with the teacher's cheap static ``eval``.
    2. Keep the best ``SEARCH_MULTIPV`` root moves from the parent's POV.
    3. Search each selected child independently with MultiPV=1 and
       ``SHALLOW_NODES`` nodes.

    All stored scores are White-relative, matching the rest of the teaching
    format.  The trainer converts them to parent-STM preference when building
    policy groups.
    """
    parent_white = bool(ctx.board.turn)
    rows: list[dict] = []

    for move in list(ctx.board.legal_moves):
        uci = move.uci()
        ctx.board.push(move)
        try:
            if ctx.board.is_checkmate():
                # Side to move in the child is mated.
                static_cp = -int(ctx.cfg.MATE_CP) if ctx.board.turn == chess.WHITE else int(ctx.cfg.MATE_CP)
            else:
                static_cp = int(ctx.backend.static_eval(ctx.board.fen(), bool(ctx.board.turn)))
        finally:
            ctx.board.pop()
        rows.append({
            "uci": uci,
            "static_cp": static_cp,
            "search_cp": None,
            "rank_static": 65535,
            "rank_search": 65535,
        })

    if not rows:
        return

    rows.sort(key=lambda r: _better_key(r["static_cp"], parent_white), reverse=True)
    for rank, row in enumerate(rows):
        row["rank_static"] = rank

    top_k = max(1, min(int(ctx.cfg.SEARCH_MULTIPV), len(rows)))
    selected = rows[:top_k]
    node_budget = max(1, int(ctx.cfg.SHALLOW_NODES))

    refined: list[dict] = []
    by_uci = {r["uci"]: r for r in rows}
    for row in selected:
        move = chess.Move.from_uci(row["uci"])
        if move not in ctx.board.legal_moves:
            continue
        ctx.board.push(move)
        try:
            if ctx.board.is_checkmate():
                cp_white = -int(ctx.cfg.MATE_CP) if ctx.board.turn == chess.WHITE else int(ctx.cfg.MATE_CP)
            else:
                lines = ctx.backend.search(
                    ctx.board.fen(), bool(ctx.board.turn), nodes=node_budget, multipv=1)
                if not lines:
                    continue
                cp_white = int(lines[0].cp_white)
        finally:
            ctx.board.pop()
        target = by_uci[row["uci"]]
        target["search_cp"] = cp_white
        refined.append(target)

    if refined:
        refined.sort(
            key=lambda r: _better_key(r["search_cp"], parent_white), reverse=True)
        for rank, row in enumerate(refined):
            row["rank_search"] = rank
        ctx.search_cp = int(refined[0]["search_cp"])
        ctx.search_nodes = node_budget * len(refined)
        ctx.flags |= FLAG_SEARCH_REFINED | FLAG_DEEP_REFINED
        ctx.methods |= METHOD_SHALLOW_SEARCH | METHOD_DEEP_SEARCH
    else:
        ctx.search_cp = int(rows[0]["static_cp"])

    ctx.moves = rows
    ctx.flags |= FLAG_POLICY
    ctx.methods |= METHOD_STATIC_POLICY
