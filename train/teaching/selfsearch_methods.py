"""Search-only teaching methods for generic UCI engines.

This module deliberately avoids the non-standard Stockfish ``eval`` command.
It lets Zchezz itself act as a teacher by producing MultiPV search scores for
all selected training positions.
"""
from __future__ import annotations

from .format import (
    FLAG_DEEP_REFINED,
    FLAG_POLICY,
    FLAG_SEARCH_REFINED,
    METHOD_DEEP_SEARCH,
    METHOD_SHALLOW_SEARCH,
)
from .methods import TeachingContext, register


@register("search_policy_all")
def search_policy_all(ctx: TeachingContext) -> None:
    """Label every position directly from one MultiPV search.

    ``SHALLOW_NODES`` is the search budget.  No static evaluation is requested,
    so this method is compatible with any UCI engine implementing MultiPV.
    """
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
