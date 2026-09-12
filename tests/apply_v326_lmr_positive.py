#!/usr/bin/env python3
"""Apply positive-only history modulation to v3.25 LMR.

The baseline thresholds are effectively dead at observed history magnitudes.
This experiment isolates only the strong-history effect: historically good
quiet moves may recover one ply of LMR, while negative-history reductions stay
unchanged. Defaults work without CLI flags.
"""
from __future__ import annotations

import argparse
from pathlib import Path

SOURCE = Path("engine/c/zchezz_v325/search.c")
THRESHOLD = 512


def exact(text: str, old: str, new: str, label: str) -> str:
    n = text.count(old)
    if n != 1:
        raise RuntimeError(f"{label}: expected exactly one match, found {n}")
    return text.replace(old, new, 1)


def apply_positive(text: str, threshold: int) -> str:
    old = """                            if (ch < -4000) reduce += 1;
                            if (ch < -8000) reduce += 1;
                            if (ch > 4000 && reduce > 0) reduce -= 1;
"""
    new = f"""                            if (ch > {threshold} && reduce > 0) reduce -= 1;
"""
    return exact(text, old, new, "LMR positive-history thresholds")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--source", type=Path, default=SOURCE)
    ap.add_argument("--threshold", type=int, default=THRESHOLD)
    args = ap.parse_args()
    if args.threshold <= 0:
        raise SystemExit("--threshold must be > 0")
    before = args.source.read_text(encoding="utf-8")
    after = apply_positive(before, args.threshold)
    args.source.write_text(after, encoding="utf-8")
    print(f"applied positive-only LMR history to {args.source}: threshold={args.threshold}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
