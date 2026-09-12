#!/usr/bin/env python3
"""Apply a focused v3.27 adaptive NMP experiment at depth >= 5."""
from __future__ import annotations

import argparse
from pathlib import Path

SOURCE = Path("engine/c/zchezz_v326/search.c")

OLD = """    if (!in_check && !is_pv && depth>=3 && ply>0 && not_endgame && static_eval>=beta) {
        /* NMP reduction: base 3 + depth/3, capped at 6.
         * Add +1 if static_eval is much above beta (eval margin bonus). */
        int R = 3 + depth / 3;
        if (R > 6) R = 6;
        if (static_eval - beta > 134) R += 1;
"""


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--margin", type=int, choices=(192, 256, 384), default=256)
    ap.add_argument("--source", type=Path, default=SOURCE)
    args = ap.parse_args()

    text = args.source.read_text(encoding="utf-8")
    if text.count(OLD) != 1:
        raise RuntimeError(f"expected one NMP block, found {text.count(OLD)}")
    new = f"""    if (!in_check && !is_pv && depth>=3 && ply>0 && not_endgame && static_eval>=beta) {{
        /* v3.27 adaptive NMP: preserve the baseline policy and add one
         * reduction only at depth >= 5 with a large eval margin. */
        int R = 3 + depth / 3;
        if (R > 6) R = 6;
        if (static_eval - beta > 134) R += 1;
        if (depth >= 5 && static_eval - beta > {args.margin}) R += 1;
"""
    args.source.write_text(text.replace(OLD, new, 1), encoding="utf-8")
    print(f"Applied depth-5 adaptive NMP margin={args.margin} to {args.source}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
