#!/usr/bin/env python3
"""Export teaching value labels to the current Zchezz SAMPLE_DTYPE .bin.

This is the compatibility bridge for the existing v325/NNU3 and v500/NNU4
value trainers. Use k=0 for this exported source so training follows the
teacher eval rather than the placeholder/unknown game outcome.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
TRAIN = ROOT / "train"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(TRAIN) not in sys.path:
    sys.path.insert(0, str(TRAIN))

from dataset import SAMPLE_DTYPE  # noqa: E402
from train.teaching.format import TeachingDataset  # noqa: E402
from train.teaching.loader import choose_value_cp  # noqa: E402

INPUT = ROOT / "data" / "teaching" / "stockfish_cascade_v1"
OUTPUT = ROOT / "data" / "teaching" / "stockfish_eval.bin"
VALUE_MODE = "search-preferred"   # search-preferred | teacher | static | search | source
CHUNK_SIZE = 200_000
REQUIRE_LABEL = True


def teaching_to_sample(row, cp_white: int) -> np.ndarray:
    """Convert one architecture-neutral row to the legacy packed sample record."""
    rec = np.zeros(1, dtype=SAMPLE_DTYPE)
    mailbox = rec[0]["board"]
    for square, code_raw in enumerate(row["board"]):
        code = int(code_raw)
        if code == 0:
            continue
        white = code <= 6
        piece_type = code if white else code - 6
        zsq = square ^ 56
        mailbox[zsq] = (8 if white else 16) | piece_type

    stm_black = int(row["stm"])
    rec[0]["stm"] = stm_black
    rec[0]["rule50"] = int(row["rule50"])
    rec[0]["castling"] = int(row["castling"])
    ep_square = int(row["ep_square"])
    rec[0]["ep_file"] = 8 if ep_square >= 64 else ep_square & 7
    cp_stm = int(cp_white) if stm_black == 0 else -int(cp_white)
    rec[0]["eval_cp"] = np.int16(max(-32000, min(32000, cp_stm)))

    result_white = int(row["result_wdl"])
    if result_white in (-1, 0, 1):
        rec[0]["game_result"] = result_white if stm_black == 0 else -result_white
    else:
        # Unknown outcome. Existing value trainers must use k=0 for this export.
        rec[0]["game_result"] = 0
    rec[0]["move_played"] = 0
    rec[0]["_pad"] = 0
    return rec


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=INPUT)
    parser.add_argument("--output", type=Path, default=OUTPUT)
    parser.add_argument("--value-mode", default=VALUE_MODE,
                        choices=("search-preferred", "teacher", "static", "search", "source"))
    parser.add_argument("--chunk-size", type=int, default=CHUNK_SIZE)
    parser.add_argument("--allow-missing", action="store_true", default=not REQUIRE_LABEL)
    parser.add_argument("--show-config", action="store_true")
    args = parser.parse_args()

    if args.show_config:
        print(f"input={args.input}")
        print(f"output={args.output}")
        print(f"value_mode={args.value_mode}")
        print(f"chunk_size={args.chunk_size}")
        print("trainer_k=0")
        return 0
    if not (args.input / "metadata.json").is_file():
        print(f"teaching dataset not found: {args.input}", file=sys.stderr)
        return 2

    dataset = TeachingDataset(args.input)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    written = skipped = 0
    with args.output.open("wb") as handle:
        buffer = np.empty(max(1, args.chunk_size), dtype=SAMPLE_DTYPE)
        fill = 0
        for row in dataset.positions:
            cp = choose_value_cp(row, args.value_mode)
            if cp is None:
                skipped += 1
                if not args.allow_missing:
                    continue
                cp = 0
            buffer[fill] = teaching_to_sample(row, cp)[0]
            fill += 1
            if fill == len(buffer):
                buffer.tofile(handle)
                written += fill
                fill = 0
        if fill:
            buffer[:fill].tofile(handle)
            written += fill

    manifest = {
        "format": "Zchezz SAMPLE_DTYPE legacy-headerless compatibility export",
        "source_teaching_dataset": str(args.input),
        "source_recipe_signature": dataset.metadata.get("recipe_signature"),
        "teacher": dataset.metadata.get("teacher"),
        "teacher_sha256": dataset.metadata.get("teacher_sha256"),
        "value_mode": args.value_mode,
        "records": written,
        "skipped_missing_label": skipped,
        "required_training_k": 0.0,
        "warning": "game_result may be unknown; train this evaluator export with k=0",
    }
    args.output.with_suffix(args.output.suffix + ".json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8")
    print(f"wrote {written:,} evaluator samples to {args.output}; skipped {skipped:,}")
    print("existing value trainers: use this source with k=0")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
