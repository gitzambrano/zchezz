#!/usr/bin/env python3
"""Run Zchezz self-play from the hardest teacher/student positions.

This wrapper deliberately reuses tests/run_selfplay.py instead of duplicating
its persistent-engine/opening logic. Bare execution exports hard seeds using
the defaults below, then starts self-play from that opening folder.
"""
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
INPUT_TEACHING = ROOT / "data" / "teaching" / "stockfish_cascade_v1"
OPENING_DIR = ROOT / "data" / "teaching" / "hard_openings"
OPENING_FILE = OPENING_DIR / "hard_seeds.epd"
PROFILE = "v325"
MIN_INTEREST = 0.90
MAX_SEEDS = 100_000
EXPAND_PLIES = 0
BRANCHES_PER_SEED = 1
GAMES = 2_000
CONCURRENCY = 4
MOVETIME_MS = 200
GENERATE_SEEDS = True


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=INPUT_TEACHING)
    parser.add_argument("--openings", type=Path, default=OPENING_DIR)
    parser.add_argument("--profile", default=PROFILE)
    parser.add_argument("--min-interest", type=float, default=MIN_INTEREST)
    parser.add_argument("--max-seeds", type=int, default=MAX_SEEDS)
    parser.add_argument("--expand-plies", type=int, default=EXPAND_PLIES)
    parser.add_argument("--branches", type=int, default=BRANCHES_PER_SEED)
    parser.add_argument("--games", type=int, default=GAMES)
    parser.add_argument("--concurrency", type=int, default=CONCURRENCY)
    parser.add_argument("--movetime", type=int, default=MOVETIME_MS)
    parser.add_argument("--no-generate-seeds", action="store_true")
    parser.add_argument("--show-config", action="store_true")
    args = parser.parse_args()

    opening_file = args.openings / OPENING_FILE.name
    if args.show_config:
        print(f"input={args.input}")
        print(f"opening_dir={args.openings}")
        print(f"opening_file={opening_file}")
        print(f"profile={args.profile}")
        print(f"min_interest={args.min_interest}")
        print(f"max_seeds={args.max_seeds}")
        print(f"expand_plies={args.expand_plies}")
        print(f"branches={args.branches}")
        print(f"games={args.games}")
        print(f"concurrency={args.concurrency}")
        print(f"movetime_ms={args.movetime}")
        print(f"generate_seeds={not args.no_generate_seeds}")
        return 0

    args.openings.mkdir(parents=True, exist_ok=True)
    if not args.no_generate_seeds:
        seed_cmd = [
            sys.executable, str(ROOT / "train" / "teaching" / "seeds.py"),
            "--input", str(args.input), "--output", str(opening_file),
            "--min-interest", str(args.min_interest),
            "--max-seeds", str(args.max_seeds),
            "--expand-plies", str(args.expand_plies),
            "--branches", str(args.branches),
        ]
        rc = subprocess.run(seed_cmd, cwd=ROOT).returncode
        if rc != 0:
            return rc
    if not opening_file.is_file():
        print(f"hard opening file not found: {opening_file}", file=sys.stderr)
        return 2

    command = [
        sys.executable, str(ROOT / "tests" / "run_selfplay.py"),
        "--profile", args.profile,
        "--opening-mode", "book",
        "--openings", str(args.openings),
        "--games", str(max(1, args.games)),
        "--concurrency", str(max(1, args.concurrency)),
        "--movetime", str(max(1, args.movetime)),
    ]
    print("targeted self-play:", " ".join(map(str, command)), flush=True)
    return subprocess.run(command, cwd=ROOT).returncode


if __name__ == "__main__":
    raise SystemExit(main())
