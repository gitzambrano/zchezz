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


def nmp_plus2_margin128(text: str) -> str:
    new = """    if (!in_check && !is_pv && depth>=3 && ply>0 && not_endgame && static_eval>=beta+128) {
        /* Experimental v3.27 NMP: larger reduction only with a 128 cp safety margin. */
        int R = 5 + depth / 3;
        if (R > 8) R = 8;
        if (static_eval - beta > 134) R += 1;
"""
    return exact(text, NMP_BASE, new, "NMP +2 with 128 cp eligibility margin")


CANDIDATES = {
    "lmr-pos768": lambda text: lmr_positive_threshold(text, 768),
    "lmr-pos1024": lambda text: lmr_positive_threshold(text, 1024),
    "lmr-pos1536": lambda text: lmr_positive_threshold(text, 1536),
    "lmr-pos2048": lambda text: lmr_positive_threshold(text, 2048),
    "lmr-pos4000": lambda text: lmr_positive_threshold(text, 4000),
    "nmp-plus2-margin128": nmp_plus2_margin128,
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
