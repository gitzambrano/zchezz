#!/usr/bin/env python3
"""Apply isolated v3.26 search candidates to a CI working copy of v3.25.

Each transform is deliberately small and independently benchmarkable. The file
runs with useful defaults and CLI flags only override them.
"""
from __future__ import annotations
import argparse
from pathlib import Path

SOURCE = Path("engine/c/zchezz_v325/search.c")
CANDIDATE = "no-check-extension"


def exact(text: str, old: str, new: str, label: str) -> str:
    n = text.count(old)
    if n != 1:
        raise RuntimeError(f"{label}: expected exactly one match, found {n}")
    return text.replace(old, new, 1)


def no_check_extension(text: str) -> str:
    return exact(
        text,
        "    if (in_check) depth++;\n\n    int is_pv = (beta - alpha > 1);\n",
        "    /* v3.26 candidate: no blanket check extension. Check evasions remain\n"
        "     * fully searched, and qsearch handles in-check horizon nodes. */\n\n"
        "    int is_pv = (beta - alpha > 1);\n",
        "blanket check extension",
    )


def stale_miss(text: str) -> str:
    old = """        if (tt_age(e, gen) != 0) {
            out->score = TT_EVAL_NONE;
            out->depth = 0;
            out->flag = TT_UPPER;
            out->static_eval = TT_EVAL_NONE;
            return 2;
        }
"""
    return exact(text, old, "        if (tt_age(e, gen) != 0) continue;\n", "stale TT move-only")


def history_prune(text: str, scale: int) -> str:
    """Rescale a dead threshold to the measured history-score magnitude.

    The d12 diagnostic observed minima around -2.5k while v3.25 requires
    -4000*depth (down to -16k), producing exactly zero history-pruned moves.
    Scale 64 is the moderate candidate; 128 is the conservative sibling.
    """
    return exact(
        text,
        "                        int hp_thresh = -4000 * depth;\n",
        f"                        int hp_thresh = -{scale} * depth;\n",
        "history pruning threshold",
    )


def history_prune_64d(text: str) -> str:
    return history_prune(text, 64)


def history_prune_128d(text: str) -> str:
    return history_prune(text, 128)


def singular_exclusion_guard(text: str) -> str:
    """Make singular verification actually search the position without TT move.

    v3.25 marks the TT move in sing_from/sing_to, but its recursive verification
    can be cut off by the same TT score (or NMP/ProbCut using the excluded move),
    and can write the constrained result back into the normal TT. Stockfish's
    excludedMove path explicitly blocks TT cutoff/NMP/TT write and skips the
    excluded move in ProbCut. This candidate establishes the same invariants.
    """
    text = exact(
        text,
        "        if (tte_hit == 1 && tte.depth >= depth && ply > 0 && ss->excluded_root_n == 0) {\n",
        "        if (tte_hit == 1 && tte.depth >= depth && ply > 0 && ss->excluded_root_n == 0 &&\n"
        "            ss->sing_from[ply] < 0) {\n",
        "singular TT score cutoff guard",
    )
    text = exact(
        text,
        "        if (tte_hit == 1 && tte.score != TT_EVAL_NONE) {\n",
        "        if (tte_hit == 1 && tte.score != TT_EVAL_NONE && ss->sing_from[ply] < 0) {\n",
        "singular TT eval-correction guard",
    )
    text = exact(
        text,
        "    if (!in_check && !is_pv && depth>=3 && ply>0 && not_endgame && static_eval>=beta) {\n",
        "    if (!in_check && !is_pv && depth>=3 && ply>0 && not_endgame && static_eval>=beta &&\n"
        "        ss->sing_from[ply] < 0) {\n",
        "singular NMP guard",
    )
    text = exact(
        text,
        "            Move *pm = &pc_moves[pi];\n            /* Skip bad captures (SEE < 0 relative to pc_beta margin) */\n",
        "            Move *pm = &pc_moves[pi];\n"
        "            if (ss->sing_from[ply] >= 0 && pm->from == ss->sing_from[ply] &&\n"
        "                pm->to == ss->sing_to[ply]) continue;\n"
        "            /* Skip bad captures (SEE < 0 relative to pc_beta margin) */\n",
        "singular ProbCut exclusion",
    )
    text = exact(
        text,
        "    if ((best_move.from||best_move.to) && !ss->time_up)\n        tt_store(b->hash, best, depth, flag, &best_move, ply, raw_eval);\n",
        "    if ((best_move.from||best_move.to) && !ss->time_up && ss->sing_from[ply] < 0)\n"
        "        tt_store(b->hash, best, depth, flag, &best_move, ply, raw_eval);\n",
        "singular TT write guard",
    )
    text = exact(
        text,
        "    if (ply > 0 && !is_pv_early && b->hm == 0) {\n",
        "    if (ply > 0 && !is_pv_early && b->hm == 0 && ss->sing_from[ply] < 0) {\n",
        "singular tablebase guard",
    )
    return text


TRANSFORMS = {
    "no-check-extension": no_check_extension,
    "stale-miss": stale_miss,
    "history-prune-64d": history_prune_64d,
    "history-prune-128d": history_prune_128d,
    "singular-exclusion-guard": singular_exclusion_guard,
}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--source", type=Path, default=SOURCE)
    ap.add_argument("--candidate", choices=sorted(TRANSFORMS), default=CANDIDATE)
    args = ap.parse_args()
    before = args.source.read_text(encoding="utf-8")
    after = TRANSFORMS[args.candidate](before)
    args.source.write_text(after, encoding="utf-8")
    print(f"applied candidate={args.candidate} to {args.source}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
