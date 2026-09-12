#!/usr/bin/env python3
"""Apply one conservative singular-search v3.27 experiment."""
from __future__ import annotations

import argparse
from pathlib import Path

SOURCE = Path("engine/c/zchezz_v326/search.c")
OLD = """    if (!in_check && depth>=7 && tte_hit && tte.depth>=depth-4 &&
        ss->sing_from[ply]<0 && ply>0 && (tte.flag==TT_EXACT||tte.flag==TT_LOWER)) {
"""


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--candidate", choices=("off", "depth8", "depth9"), required=True)
    ap.add_argument("--source", type=Path, default=SOURCE)
    args = ap.parse_args()

    text = args.source.read_text(encoding="utf-8")
    if text.count(OLD) != 1:
        raise RuntimeError(f"expected one singular eligibility block, found {text.count(OLD)}")

    if args.candidate == "off":
        new = """    if (0 && !in_check && depth>=7 && tte_hit && tte.depth>=depth-4 &&
        ss->sing_from[ply]<0 && ply>0 && (tte.flag==TT_EXACT||tte.flag==TT_LOWER)) {
"""
    else:
        depth = 8 if args.candidate == "depth8" else 9
        new = f"""    if (!in_check && depth>={depth} && tte_hit && tte.depth>=depth-4 &&
        ss->sing_from[ply]<0 && ply>0 && (tte.flag==TT_EXACT||tte.flag==TT_LOWER)) {{
"""

    args.source.write_text(text.replace(OLD, new, 1), encoding="utf-8")
    print(f"Applied singular candidate={args.candidate} to {args.source}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
