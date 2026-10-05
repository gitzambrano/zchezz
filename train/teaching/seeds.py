#!/usr/bin/env python3
"""Export hard teaching positions as EPD seeds for targeted self-play."""
from __future__ import annotations

import argparse
import random
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

INPUT = ROOT / "data" / "teaching" / "stockfish_cascade_v1"
OUTPUT = ROOT / "data" / "teaching" / "hard_seeds.epd"
MIN_INTEREST = 0.90
MAX_SEEDS = 100_000
SAMPLE_RATE = 1.0
SEED = 20260911
EXPAND_PLIES = 0
BRANCHES_PER_SEED = 1


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=INPUT)
    parser.add_argument("--output", type=Path, default=OUTPUT)
    parser.add_argument("--min-interest", type=float, default=MIN_INTEREST)
    parser.add_argument("--max-seeds", type=int, default=MAX_SEEDS)
    parser.add_argument("--sample-rate", type=float, default=SAMPLE_RATE)
    parser.add_argument("--expand-plies", type=int, default=EXPAND_PLIES)
    parser.add_argument("--branches", type=int, default=BRANCHES_PER_SEED)
    parser.add_argument("--show-config", action="store_true")
    args = parser.parse_args()

    if args.show_config:
        print(f"input={args.input}")
        print(f"output={args.output}")
        print(f"min_interest={args.min_interest}")
        print(f"max_seeds={args.max_seeds}")
        print(f"sample_rate={args.sample_rate}")
        print(f"expand_plies={args.expand_plies}")
        print(f"branches={args.branches}")
        return 0
    if not (args.input / "metadata.json").is_file():
        print(f"dataset not found: {args.input}", file=sys.stderr)
        return 2
    try:
        import chess
    except ImportError:
        print("python-chess is required", file=sys.stderr)
        return 2

    from train.teaching.format import (
        FLAG_HARD, MISSING_CP, TeachingDataset, record_to_fen)

    dataset = TeachingDataset(args.input)
    rng = random.Random(SEED)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    written = 0
    with args.output.open("w", encoding="utf-8") as handle:
        for row in dataset.positions:
            if written >= args.max_seeds:
                break
            if (not (int(row["flags"]) & FLAG_HARD)
                    and float(row["interest"]) < args.min_interest):
                continue
            if rng.random() > args.sample_rate:
                continue

            base = chess.Board(record_to_fen(row))
            roots = [base]
            if args.expand_plies > 0:
                roots = []
                for _ in range(max(1, args.branches)):
                    board = base.copy(stack=False)
                    for _ in range(args.expand_plies):
                        if board.is_game_over():
                            break
                        moves = list(board.legal_moves)
                        if not moves:
                            break
                        board.push(rng.choice(moves))
                    if not board.is_game_over():
                        roots.append(board)

            cp = int(row["search_cp"])
            if cp == MISSING_CP:
                cp = int(row["static_cp"])
            for board in roots:
                if written >= args.max_seeds:
                    break
                fen4 = " ".join(board.fen().split()[:4])
                handle.write(
                    f'{fen4} c1 "{cp}"; c2 "teaching-hard-seed";\n')
                written += 1

    print(f"wrote {written:,} targeted self-play seeds to {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
