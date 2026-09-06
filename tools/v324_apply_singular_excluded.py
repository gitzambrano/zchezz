#!/usr/bin/env python3
"""Apply v3.24 singular-extension experimental variants to v3.23 search.c.

Modes:
  safe       Make singular excluded search respect TT/NMP/ProbCut/TT-store isolation.
  nosingular Disable the singular-extension block entirely.

This script is experimental and intentionally edits v323 in-place in CI only.
"""
from __future__ import annotations

import argparse
from pathlib import Path

SEARCH = Path("engine/c/zchezz_v323/search.c")


def replace_one(s: str, old: str, new: str) -> str:
    n = s.count(old)
    if n != 1:
        raise SystemExit(f"expected exactly one anchor, found {n}: {old}")
    return s.replace(old, new, 1)


def apply_safe(s: str) -> str:
    s = replace_one(
        s,
        "if (tte_hit == 1 && tte.depth >= depth && ply > 0 && ss->excluded_root_n == 0) {",
        "if (tte_hit == 1 && tte.depth >= depth && ply > 0 && ss->excluded_root_n == 0 && ss->sing_from[ply] < 0) {",
    )
    s = replace_one(
        s,
        "if (tte_hit == 1 && tte.score != TT_EVAL_NONE) {",
        "if (ss->sing_from[ply] < 0 && tte_hit == 1 && tte.score != TT_EVAL_NONE) {",
    )
    s = replace_one(
        s,
        "if (!in_check && !is_pv && depth>=3 && ply>0 && not_endgame && static_eval>=beta) {",
        "if (ss->sing_from[ply] < 0 && !in_check && !is_pv && depth>=3 && ply>0 && not_endgame && static_eval>=beta) {",
    )
    s = replace_one(
        s,
        "        for (int pi = 0; pi < pc_n; pi++) {\n            Move *pm = &pc_moves[pi];",
        "        for (int pi = 0; pi < pc_n; pi++) {\n            Move *pm = &pc_moves[pi];\n            if (ss->sing_from[ply] >= 0 && pm->from == ss->sing_from[ply] && pm->to == ss->sing_to[ply]) continue;",
    )
    s = replace_one(
        s,
        "    if ((best_move.from||best_move.to) && !ss->time_up)\n        tt_store(b->hash, best, depth, flag, &best_move, ply, raw_eval);",
        "    if ((best_move.from||best_move.to) && !ss->time_up && ss->sing_from[ply] < 0)\n        tt_store(b->hash, best, depth, flag, &best_move, ply, raw_eval);",
    )
    return s


def apply_no_singular(s: str) -> str:
    return replace_one(
        s,
        "if (!in_check && depth>=7 && tte_hit && tte.depth>=depth-4 &&",
        "if (0 && !in_check && depth>=7 && tte_hit && tte.depth>=depth-4 &&",
    )


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("mode", choices=("safe", "nosingular"))
    args = ap.parse_args()

    s = SEARCH.read_text(encoding="utf-8")
    if args.mode == "safe":
        s = apply_safe(s)
    else:
        s = apply_no_singular(s)
    SEARCH.write_text(s, encoding="utf-8")
    print(f"applied singular variant: {args.mode}")


if __name__ == "__main__":
    main()
