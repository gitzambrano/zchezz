#!/usr/bin/env python3
"""Tune negative-history LMR thresholds on top of the v3.27 deep5 policy."""
from __future__ import annotations

import argparse
from pathlib import Path

SOURCE = Path("engine/c/zchezz_v326/search.c")
OLD = """                            if (ch < -512) reduce += 1;
                            if (ch < -1024) reduce += 1;
                            if (ch > 512 && reduce > 0) reduce -= 1;
"""


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--negative", type=int, choices=(384, 640, 768), required=True)
    ap.add_argument("--source", type=Path, default=SOURCE)
    args = ap.parse_args()

    text = args.source.read_text(encoding="utf-8")
    if text.count(OLD) != 1:
        raise RuntimeError(f"expected one LMR history block, found {text.count(OLD)}")
    first=args.negative
    new=f"""                            if (ch < -{first}) reduce += 1;
                            if (ch < -{2*first}) reduce += 1;
                            if (depth >= 5 && ch > 512 && reduce > 0) reduce -= 1;
"""
    args.source.write_text(text.replace(OLD,new,1),encoding="utf-8")
    print(f"Applied deep5 with negative thresholds {first}/{2*first} to {args.source}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
