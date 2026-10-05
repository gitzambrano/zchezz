#!/usr/bin/env python3
"""Inspect a Zchezz teaching dataset. Bare run inspects the default corpus."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

INPUT = ROOT / "data" / "teaching" / "stockfish_cascade_v1"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=INPUT)
    parser.add_argument("--show-config", action="store_true")
    args = parser.parse_args()
    if args.show_config:
        print(f"input={args.input}")
        return 0
    if not (args.input / "metadata.json").is_file():
        print(f"teaching dataset not found: {args.input}", file=sys.stderr)
        return 2

    from train.teaching.format import (
        FLAG_DEEP_REFINED, FLAG_HARD, FLAG_POLICY, FLAG_SEARCH_REFINED,
        MISSING_CP, TeachingDataset)

    dataset = TeachingDataset(args.input)
    positions = dataset.positions
    count = len(positions)

    def pct(mask) -> float:
        return 0.0 if count == 0 else 100.0 * float(np.count_nonzero(mask)) / count

    print(f"dataset: {args.input}")
    print(f"positions: {count:,}")
    print(f"moves: {len(dataset.moves):,}")
    if count:
        print(f"static labels: {pct(positions['static_cp'] != MISSING_CP):.2f}%")
        print(f"search labels: {pct(positions['search_cp'] != MISSING_CP):.2f}%")
        print(f"policy coverage: {pct((positions['flags'] & FLAG_POLICY) != 0):.2f}%")
        print(f"hard: {pct((positions['flags'] & FLAG_HARD) != 0):.2f}%")
        print(f"shallow refined: {pct((positions['flags'] & FLAG_SEARCH_REFINED) != 0):.2f}%")
        print(f"deep refined: {pct((positions['flags'] & FLAG_DEEP_REFINED) != 0):.2f}%")
        print(
            "interest mean/p95/max: "
            f"{float(positions['interest'].mean()):.3f} / "
            f"{float(np.quantile(positions['interest'], 0.95)):.3f} / "
            f"{float(positions['interest'].max()):.3f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
