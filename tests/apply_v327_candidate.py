#!/usr/bin/env python3
"""Apply one v3.27 search candidate to the promoted v3.26 search source.

Bare execution applies the default candidate. All constants below are editable and
CLI arguments are optional overrides, following the repository convention.
"""
from __future__ import annotations

import argparse
from pathlib import Path

SOURCE = Path("engine/c/zchezz_v326/search.c")
DEFAULT_CANDIDATE = "lmr-pos1024"

LMR_BASE = """                            if (ch < -512) reduce += 1;
                            if (ch < -1024) reduce += 1;
                            if (ch > 512 && reduce > 0) reduce -= 1;
"""

LMR_BLOCK = """                            int ft_idx = mfr * 64 + mto;
                            int ch = ss->mv_history[ft_idx];
                            if (cmh0 >= 0) ch += ss->cont_hist[0][cmh0][ft_idx];
                            if (cmh1 >= 0) ch += ss->cont_hist[1][cmh1][ft_idx];
                            if (ch < -512) reduce += 1;
                            if (ch < -1024) reduce += 1;
                            if (ch > 512 && reduce > 0) reduce -= 1;
"""

NMP_BASE = """    if (!in_check && !is_pv && depth>=3 && ply>0 && not_endgame && static_eval>=beta) {
        /* NMP reduction: base 3 + depth/3, capped at 6.
         * Add +1 if static_eval is much above beta (eval margin bonus). */
        int R = 3 + depth / 3;
        if (R > 6) R = 6;
        if (static_eval - beta > 134) R += 1;
"""


def exact(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"{label}: expected one exact match, found {count}")
    return text.replace(old, new, 1)


def lmr_positive_threshold(text: str, threshold: int) -> str:
    new = f"""                            if (ch < -512) reduce += 1;
                            if (ch < -1024) reduce += 1;
                            if (ch > {threshold} && reduce > 0) reduce -= 1;
"""
    return exact(text, LMR_BASE, new, f"LMR positive threshold {threshold}")


def lmr_positive_min_depth(text: str, min_depth: int) -> str:
    new = f"""                            if (ch < -512) reduce += 1;
                            if (ch < -1024) reduce += 1;
                            if (depth >= {min_depth} && ch > 512 && reduce > 0) reduce -= 1;
"""
    return exact(text, LMR_BASE, new, f"LMR positive min depth {min_depth}")


def lmr_positive_min_depth_threshold(text: str, min_depth: int, threshold: int) -> str:
    """Keep the deep-only positive-history bonus but tune its activation threshold."""
    new = f"""                            if (ch < -512) reduce += 1;
                            if (ch < -1024) reduce += 1;
                            if (depth >= {min_depth} && ch > {threshold} && reduce > 0) reduce -= 1;
"""
    return exact(text, LMR_BASE, new, f"LMR positive min depth {min_depth}, threshold {threshold}")


def lmr_positive_shallow_threshold(text: str, shallow_threshold: int) -> str:
    """Require stronger positive history only in the shallow LMR regime."""
    new = f"""                            if (ch < -512) reduce += 1;
                            if (ch < -1024) reduce += 1;
                            int pos_hist_threshold = depth < 5 ? {shallow_threshold} : 512;
                            if (ch > pos_hist_threshold && reduce > 0) reduce -= 1;
"""
    return exact(text, LMR_BASE, new, f"LMR shallow positive threshold {shallow_threshold}")


def lmr_positive_early(text: str, max_move: int) -> str:
    new = f"""                            if (ch < -512) reduce += 1;
                            if (ch < -1024) reduce += 1;
                            if (legal_count <= {max_move} && ch > 512 && reduce > 0) reduce -= 1;
"""
    return exact(text, LMR_BASE, new, f"LMR positive early-move limit {max_move}")


def lmr_weighted_main(text: str, threshold: int) -> str:
    """Give main history about twice the continuation-history weight."""
    new = f"""                            int ft_idx = mfr * 64 + mto;
                            int ch = 2 * ss->mv_history[ft_idx];
                            if (cmh0 >= 0) ch += ss->cont_hist[0][cmh0][ft_idx];
                            if (cmh1 >= 0) ch += ss->cont_hist[1][cmh1][ft_idx];
                            if (ch < -{threshold}) reduce += 1;
                            if (ch < -{2 * threshold}) reduce += 1;
                            if (ch > {threshold} && reduce > 0) reduce -= 1;
"""
    return exact(text, LMR_BLOCK, new, f"weighted-main LMR threshold {threshold}")


def nmp_plus2_margin128(text: str) -> str:
    new = """    if (!in_check && !is_pv && depth>=3 && ply>0 && not_endgame && static_eval>=beta+128) {
        /* Experimental v3.27 NMP: larger reduction only with a 128 cp safety margin. */
        int R = 5 + depth / 3;
        if (R > 8) R = 8;
        if (static_eval - beta > 134) R += 1;
"""
    return exact(text, NMP_BASE, new, "NMP +2 with 128 cp eligibility margin")


def nmp_extra1(text: str, min_depth: int, margin: int) -> str:
    """Preserve baseline NMP everywhere, adding one extra ply only on clearly winning deep nodes."""
    new = f"""    if (!in_check && !is_pv && depth>=3 && ply>0 && not_endgame && static_eval>=beta) {{
        /* v3.27 adaptive NMP: preserve the baseline gate/reduction and add
         * one extra ply only when depth and eval margin both justify it. */
        int R = 3 + depth / 3;
        if (R > 6) R = 6;
        if (static_eval - beta > 134) R += 1;
        if (depth >= {min_depth} && static_eval - beta > {margin}) R += 1;
"""
    return exact(text, NMP_BASE, new, f"adaptive NMP extra1 d{min_depth} margin {margin}")


CANDIDATES = {
    "lmr-pos768": lambda text: lmr_positive_threshold(text, 768),
    "lmr-pos1024": lambda text: lmr_positive_threshold(text, 1024),
    "lmr-pos1536": lambda text: lmr_positive_threshold(text, 1536),
    "lmr-pos2048": lambda text: lmr_positive_threshold(text, 2048),
    "lmr-pos4000": lambda text: lmr_positive_threshold(text, 4000),
    "lmr-pos-deep4": lambda text: lmr_positive_min_depth(text, 4),
    "lmr-pos-deep5": lambda text: lmr_positive_min_depth(text, 5),
    "lmr-pos-deep6": lambda text: lmr_positive_min_depth(text, 6),
    "lmr-pos-deep5-th384": lambda text: lmr_positive_min_depth_threshold(text, 5, 384),
    "lmr-pos-deep5-th640": lambda text: lmr_positive_min_depth_threshold(text, 5, 640),
    "lmr-pos-deep5-th768": lambda text: lmr_positive_min_depth_threshold(text, 5, 768),
    "lmr-pos-shallow768": lambda text: lmr_positive_shallow_threshold(text, 768),
    "lmr-pos-shallow1024": lambda text: lmr_positive_shallow_threshold(text, 1024),
    "lmr-pos-early8": lambda text: lmr_positive_early(text, 8),
    "lmr-pos-early12": lambda text: lmr_positive_early(text, 12),
    "lmr-main2-768": lambda text: lmr_weighted_main(text, 768),
    "lmr-main2-1024": lambda text: lmr_weighted_main(text, 1024),
    "nmp-plus2-margin128": nmp_plus2_margin128,
    "nmp-extra1-d6-m256": lambda text: nmp_extra1(text, 6, 256),
    "nmp-extra1-d6-m384": lambda text: nmp_extra1(text, 6, 384),
    "nmp-extra1-d8-m256": lambda text: nmp_extra1(text, 8, 256),
}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--candidate", choices=sorted(CANDIDATES), default=DEFAULT_CANDIDATE)
    ap.add_argument("--source", type=Path, default=SOURCE)
    ap.add_argument("--show-config", action="store_true")
    args = ap.parse_args()

    if args.show_config:
        print(f"candidate={args.candidate}")
        print(f"source={args.source}")
        return 0

    text = args.source.read_text(encoding="utf-8")
    updated = CANDIDATES[args.candidate](text)
    args.source.write_text(updated, encoding="utf-8")
    print(f"Applied {args.candidate} to {args.source}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
