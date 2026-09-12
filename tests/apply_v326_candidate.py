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
    """Rescale a dead threshold to the measured history-score magnitude."""
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


def nmp(text: str, base: int, cap: int, deep_only: bool = False) -> str:
    """Increase null-move reduction while retaining all existing eligibility guards.

    Stockfish is substantially more aggressive here, but these candidates move
    only one or two plies at a time so strength loss can be measured directly.
    """
    old = """        int R = 3 + depth / 3;
        if (R > 6) R = 6;
        if (static_eval - beta > 134) R += 1;
"""
    if deep_only:
        new = f"""        int R = 3 + depth / 3;
        if (depth >= 5) R += 1;
        if (R > {cap}) R = {cap};
        if (static_eval - beta > 134) R += 1;
"""
    else:
        new = f"""        int R = {base} + depth / 3;
        if (R > {cap}) R = {cap};
        if (static_eval - beta > 134) R += 1;
"""
    return exact(text, old, new, "NMP reduction")


def nmp_plus1(text: str) -> str:
    return nmp(text, 4, 7)


def nmp_plus1_deep(text: str) -> str:
    return nmp(text, 4, 7, deep_only=True)


def nmp_plus2(text: str) -> str:
    return nmp(text, 5, 8)


def nmp_plus2_margin(text: str, margin: int) -> str:
    """Use the +2 reduction only when static eval clears beta by a safety margin."""
    text = nmp_plus2(text)
    return exact(
        text,
        "    if (!in_check && !is_pv && depth>=3 && ply>0 && not_endgame && static_eval>=beta) {\n",
        f"    if (!in_check && !is_pv && depth>=3 && ply>0 && not_endgame && static_eval>=beta+{margin}) {{\n",
        f"NMP +2 eligibility margin {margin}",
    )


def nmp_plus2_margin64(text: str) -> str:
    return nmp_plus2_margin(text, 64)


def nmp_plus2_margin128(text: str) -> str:
    return nmp_plus2_margin(text, 128)


def lmr_history(text: str, first: int) -> str:
    """Activate both negative and positive history-based LMR adjustments."""
    old = """                            if (ch < -4000) reduce += 1;
                            if (ch < -8000) reduce += 1;
                            if (ch > 4000 && reduce > 0) reduce -= 1;
"""
    new = f"""                            if (ch < -{first}) reduce += 1;
                            if (ch < -{2 * first}) reduce += 1;
                            if (ch > {first} && reduce > 0) reduce -= 1;
"""
    return exact(text, old, new, "LMR history thresholds")


def lmr_history_1024(text: str) -> str:
    return lmr_history(text, 1024)


def lmr_history_512(text: str) -> str:
    return lmr_history(text, 512)


def lmr_history_negative(text: str, first: int) -> str:
    """Increase reductions only for historically bad quiets.

    The symmetric second-wave candidates expanded the tree because strong
    positive history frequently removed one ply of reduction. This variant
    keeps only the negative signal, which should improve selectivity without
    rewarding already well-ordered quiet moves with extra search depth.
    """
    old = """                            if (ch < -4000) reduce += 1;
                            if (ch < -8000) reduce += 1;
                            if (ch > 4000 && reduce > 0) reduce -= 1;
"""
    new = f"""                            if (ch < -{first}) reduce += 1;
                            if (ch < -{2 * first}) reduce += 1;
"""
    return exact(text, old, new, "negative-only LMR history thresholds")


def lmr_negative_1024(text: str) -> str:
    return lmr_history_negative(text, 1024)


def lmr_negative_512(text: str) -> str:
    return lmr_history_negative(text, 512)


def qs_delta(text: str, margin: int) -> str:
    """Tighten per-capture qsearch delta pruning without touching promotions."""
    old = "        if (stand + gain + 50 < alpha && !moves[i].prom) { moves[i].score = -99999; continue; }\n"
    if margin == 0:
        expr = "stand + gain < alpha"
    elif margin > 0:
        expr = f"stand + gain + {margin} < alpha"
    else:
        expr = f"stand + gain - {-margin} < alpha"
    new = f"        if ({expr} && !moves[i].prom) {{ moves[i].score = -99999; continue; }}\n"
    return exact(text, old, new, "qsearch per-move delta margin")


def qs_delta_plus25(text: str) -> str:
    return qs_delta(text, 25)


def qs_delta_0(text: str) -> str:
    return qs_delta(text, 0)


def qs_delta_minus25(text: str) -> str:
    return qs_delta(text, -25)


def qs_delta_minus50(text: str) -> str:
    return qs_delta(text, -50)


def singular_exclusion_guard(text: str) -> str:
    """Make singular verification actually search the position without TT move."""
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
    "nmp-plus1": nmp_plus1,
    "nmp-plus1-deep": nmp_plus1_deep,
    "nmp-plus2": nmp_plus2,
    "nmp-plus2-margin64": nmp_plus2_margin64,
    "nmp-plus2-margin128": nmp_plus2_margin128,
    "lmr-history-1024": lmr_history_1024,
    "lmr-history-512": lmr_history_512,
    "lmr-negative-1024": lmr_negative_1024,
    "lmr-negative-512": lmr_negative_512,
    "qs-delta-plus25": qs_delta_plus25,
    "qs-delta-0": qs_delta_0,
    "qs-delta-minus25": qs_delta_minus25,
    "qs-delta-minus50": qs_delta_minus50,
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
