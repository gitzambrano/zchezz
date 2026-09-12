#!/usr/bin/env python3
"""Repair v3.25 singular verification with narrowly-scoped exclusions.

The current singular verification recursively searches the same position while
excluding the TT move, but the ordinary TT score cutoff can immediately return
the very entry being tested. This transform prevents that self-confirming TT
cutoff and prevents excluded searches from storing a normal root-position TT
entry. An optional variant also disables NMP in the excluded search, because a
null-move cutoff does not demonstrate that a real alternative move exists.

Defaults work without CLI arguments.
"""
from __future__ import annotations

import argparse
from pathlib import Path

SOURCE = Path("engine/c/zchezz_v325/search.c")
MODE = "tt-only"


def exact(text: str, old: str, new: str, label: str) -> str:
    n = text.count(old)
    if n != 1:
        raise RuntimeError(f"{label}: expected exactly one match, found {n}")
    return text.replace(old, new, 1)


def apply(text: str, mode: str) -> str:
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
    args = ap.parse_args()
    before = args.source.read_text(encoding="utf-8")
    after = apply(before, args.mode)
    args.source.write_text(after, encoding="utf-8")
    print(f"applied minimal singular repair mode={args.mode} to {args.source}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
