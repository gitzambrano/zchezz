#!/usr/bin/env python3
"""Repair and tune v3.25 singular verification with narrow exclusions.

The current singular verification recursively searches the same position while
excluding the TT move, but the ordinary TT score cutoff can immediately return
the very entry being tested. This transform prevents that self-confirming TT
cutoff and prevents excluded searches from storing a normal root-position TT
entry. Eligibility can then be tightened independently by minimum depth and TT
depth lag. An optional mode also disables NMP in the excluded search.

Defaults are conservative and work without CLI arguments.
"""
from __future__ import annotations

import argparse
from pathlib import Path

SOURCE = Path("engine/c/zchezz_v325/search.c")
MODE = "tt-only"
MIN_DEPTH = 10
TT_LAG = 2


def exact(text: str, old: str, new: str, label: str) -> str:
    n = text.count(old)
    if n != 1:
        raise RuntimeError(f"{label}: expected exactly one match, found {n}")
    return text.replace(old, new, 1)


def apply(text: str, mode: str, min_depth: int, tt_lag: int) -> str:
    text = exact(
        text,
        "        if (tte_hit == 1 && tte.depth >= depth && ply > 0 && ss->excluded_root_n == 0) {\n",
        "        if (tte_hit == 1 && tte.depth >= depth && ply > 0 && ss->excluded_root_n == 0 &&\n"
        "            ss->sing_from[ply] < 0) {\n",
        "excluded-search TT score cutoff",
    )

    text = exact(
        text,
        "    if ((best_move.from||best_move.to) && !ss->time_up)\n        tt_store(b->hash, best, depth, flag, &best_move, ply, raw_eval);\n",
        "    if ((best_move.from||best_move.to) && !ss->time_up && ss->sing_from[ply] < 0)\n"
        "        tt_store(b->hash, best, depth, flag, &best_move, ply, raw_eval);\n",
        "excluded-search TT write",
    )

    text = exact(
        text,
        "    if (!in_check && depth>=7 && tte_hit && tte.depth>=depth-4 &&\n"
        "        ss->sing_from[ply]<0 && ply>0 && (tte.flag==TT_EXACT||tte.flag==TT_LOWER)) {\n",
        f"    if (!in_check && depth>={min_depth} && tte_hit && tte.depth>=depth-{tt_lag} &&\n"
        "        ss->sing_from[ply]<0 && ply>0 && (tte.flag==TT_EXACT||tte.flag==TT_LOWER)) {\n",
        "singular eligibility",
    )

    if mode == "tt-nmp":
        text = exact(
            text,
            "    if (!in_check && !is_pv && depth>=3 && ply>0 && not_endgame && static_eval>=beta) {\n",
            "    if (!in_check && !is_pv && depth>=3 && ply>0 && not_endgame && static_eval>=beta &&\n"
            "        ss->sing_from[ply] < 0) {\n",
            "excluded-search NMP",
        )
    elif mode != "tt-only":
        raise ValueError(mode)

    return text


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--source", type=Path, default=SOURCE)
    ap.add_argument("--mode", choices=("tt-only", "tt-nmp"), default=MODE)
    ap.add_argument("--min-depth", type=int, default=MIN_DEPTH)
    ap.add_argument("--tt-lag", type=int, default=TT_LAG)
    args = ap.parse_args()
    if args.min_depth < 6:
        raise SystemExit("--min-depth must be >= 6")
    if args.tt_lag < 0:
        raise SystemExit("--tt-lag must be >= 0")
    before = args.source.read_text(encoding="utf-8")
    after = apply(before, args.mode, args.min_depth, args.tt_lag)
    args.source.write_text(after, encoding="utf-8")
    print(
        f"applied singular repair mode={args.mode} min_depth={args.min_depth} "
        f"tt_lag={args.tt_lag} to {args.source}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
