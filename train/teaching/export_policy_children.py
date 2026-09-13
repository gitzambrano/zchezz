#!/usr/bin/env python3
"""Distill teacher move policy into child-position value samples.

The teaching corpus stores White-relative scores for legal moves.  For each
policy-labelled parent this exporter writes a balanced set of post-move child
positions to the legacy SAMPLE_DTYPE format.  Training the current NNU4 value
network on these children teaches the local move ordering surface without
adding a policy head to the engine hot path.

Use the exported file with the existing value trainer and k=0.
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
from train.teaching.format import (  # noqa: E402
    FLAG_HARD, FLAG_HIGH_ENTROPY, MISSING_CP, TeachingDataset,
    record_to_fen, unpack_move_uci,
)
from train.teaching.loader import choose_value_cp  # noqa: E402

INPUT = ROOT / "data" / "teaching" / "stockfish_cascade_v1"
OUTPUT = ROOT / "data" / "teaching" / "stockfish_policy_children.bin"
TOP_K = 4
NEAR_BEST_CP = 80
TAIL_K = 2
MAX_CHILDREN = 8
PARENT_REPEATS = 2
HARD_BONUS_CHILDREN = 2
VALUE_MODE = "search-preferred"
CHUNK_SIZE = 200_000


def _clamp_cp(value: int) -> np.int16:
    return np.int16(max(-32000, min(32000, int(value))))


def board_to_sample(board, cp_white: int, result_white: int = 2) -> np.void:
    """Encode a python-chess board as one legacy training record."""
    import chess

    rec = np.zeros(1, dtype=SAMPLE_DTYPE)
    mailbox = rec[0]["board"]
    for square, piece in board.piece_map().items():
        zsq = int(square) ^ 56
        mailbox[zsq] = (8 if piece.color == chess.WHITE else 16) | piece.piece_type

    stm_black = 0 if board.turn == chess.WHITE else 1
    rec[0]["stm"] = stm_black
    rec[0]["rule50"] = min(255, int(board.halfmove_clock))
    castling = 0
    if board.has_kingside_castling_rights(chess.WHITE): castling |= 1
    if board.has_queenside_castling_rights(chess.WHITE): castling |= 2
    if board.has_kingside_castling_rights(chess.BLACK): castling |= 4
    if board.has_queenside_castling_rights(chess.BLACK): castling |= 8
    rec[0]["castling"] = castling
    rec[0]["ep_file"] = 8 if board.ep_square is None else chess.square_file(board.ep_square)
    cp_stm = int(cp_white) if not stm_black else -int(cp_white)
    rec[0]["eval_cp"] = _clamp_cp(cp_stm)
    if result_white in (-1, 0, 1):
        rec[0]["game_result"] = result_white if not stm_black else -result_white
    else:
        rec[0]["game_result"] = 0
    rec[0]["move_played"] = 0
    rec[0]["_pad"] = 0
    return rec[0]


def _scored_moves(row, moves, prefer_search: bool = True):
    """Return (packed_move, cp_white, parent_pov_cp) sorted best first."""
    white = int(row["stm"]) == 0
    scored = []
    for move in moves:
        cp = int(move["search_cp"]) if prefer_search else MISSING_CP
        if cp == MISSING_CP:
            cp = int(move["static_cp"])
        if cp == MISSING_CP:
            continue
        scored.append((int(move["move"]), cp, float(cp if white else -cp)))
    scored.sort(key=lambda item: item[2], reverse=True)
    return scored


def select_policy_children(row, moves, *, top_k: int = TOP_K,
                           near_best_cp: int = NEAR_BEST_CP,
                           tail_k: int = TAIL_K,
                           max_children: int = MAX_CHILDREN,
                           hard_bonus_children: int = HARD_BONUS_CHILDREN):
    """Select strong, ambiguous, and contrastive moves deterministically."""
    scored = _scored_moves(row, moves)
    if not scored or max_children <= 0:
        return []
    target_max = max_children
    flags = int(row["flags"])
    if flags & (FLAG_HARD | FLAG_HIGH_ENTROPY):
        target_max += max(0, hard_bonus_children)
    selected = []
    seen = set()

    def add(item):
        if item[0] not in seen and len(selected) < target_max:
            selected.append(item); seen.add(item[0])

    for item in scored[:max(1, top_k)]:
        add(item)
    best = scored[0][2]
    for item in scored:
        if best - item[2] <= max(0, near_best_cp):
            add(item)
    remaining = [item for item in scored if item[0] not in seen]
    if remaining and tail_k > 0:
        # Contrastive coverage: worst first, then roughly evenly spaced tail.
        picks = []
        if tail_k == 1:
            picks = [remaining[-1]]
        else:
            for i in range(tail_k):
                idx = round(i * (len(remaining) - 1) / (tail_k - 1))
                picks.append(remaining[idx])
            picks.reverse()
        for item in picks:
            add(item)
    return selected


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=INPUT)
    parser.add_argument("--output", type=Path, default=OUTPUT)
    parser.add_argument("--top-k", type=int, default=TOP_K)
    parser.add_argument("--near-best-cp", type=int, default=NEAR_BEST_CP)
    parser.add_argument("--tail-k", type=int, default=TAIL_K)
    parser.add_argument("--max-children", type=int, default=MAX_CHILDREN)
    parser.add_argument("--parent-repeats", type=int, default=PARENT_REPEATS)
    parser.add_argument("--hard-bonus-children", type=int, default=HARD_BONUS_CHILDREN)
    parser.add_argument("--value-mode", default=VALUE_MODE,
                        choices=("search-preferred", "teacher", "static", "search", "source"))
    parser.add_argument("--chunk-size", type=int, default=CHUNK_SIZE)
    parser.add_argument("--show-config", action="store_true")
    args = parser.parse_args()
    if args.show_config:
        for key in ("input", "output", "top_k", "near_best_cp", "tail_k",
                    "max_children", "parent_repeats", "hard_bonus_children",
                    "value_mode", "chunk_size"):
            print(f"{key}={getattr(args, key)}")
        print("trainer_k=0")
        return 0
    if not (args.input / "metadata.json").is_file():
        print(f"teaching dataset not found: {args.input}", file=sys.stderr)
        return 2

    import chess
    dataset = TeachingDataset(args.input)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    capacity = max(1, int(args.chunk_size))
    buffer = np.empty(capacity, dtype=SAMPLE_DTYPE)
    fill = written = parents = children = skipped_policy = illegal = 0

    def emit(handle, sample):
        nonlocal fill, written
        buffer[fill] = sample; fill += 1
        if fill == capacity:
            buffer.tofile(handle); written += fill; fill = 0

    with args.output.open("wb") as handle:
        for index, row in enumerate(dataset.positions):
            moves = dataset.moves_for(index)
            selected = select_policy_children(
                row, moves, top_k=max(1, args.top_k),
                near_best_cp=max(0, args.near_best_cp), tail_k=max(0, args.tail_k),
                max_children=max(1, args.max_children),
                hard_bonus_children=max(0, args.hard_bonus_children))
            if not selected:
                skipped_policy += 1
                continue
            result_white = int(row["result_wdl"])
            parent_cp = choose_value_cp(row, args.value_mode)
            board = chess.Board(record_to_fen(row))
            if parent_cp is not None:
                sample = board_to_sample(board, parent_cp, result_white)
                for _ in range(max(0, args.parent_repeats)):
                    emit(handle, sample); parents += 1
            for packed, cp_white, _ in selected:
                try:
                    move = chess.Move.from_uci(unpack_move_uci(packed))
                except ValueError:
                    illegal += 1; continue
                if move not in board.legal_moves:
                    illegal += 1; continue
                board.push(move)
                emit(handle, board_to_sample(board, cp_white, result_white))
                children += 1
                board.pop()
        if fill:
            buffer[:fill].tofile(handle); written += fill

    manifest = {
        "format": "Zchezz SAMPLE_DTYPE policy-to-value distillation export",
        "source_teaching_dataset": str(args.input),
        "source_recipe_signature": dataset.metadata.get("recipe_signature"),
        "teacher": dataset.metadata.get("teacher"),
        "teacher_sha256": dataset.metadata.get("teacher_sha256"),
        "records": written,
        "parent_records": parents,
        "child_records": children,
        "positions_without_policy": skipped_policy,
        "illegal_or_unusable_move_labels": illegal,
        "selection": {
            "top_k": args.top_k, "near_best_cp": args.near_best_cp,
            "tail_k": args.tail_k, "max_children": args.max_children,
            "hard_bonus_children": args.hard_bonus_children,
            "parent_repeats": args.parent_repeats,
        },
        "required_training_k": 0.0,
        "label_frame": "child position eval_cp is side-to-move relative; teacher move cp is White-relative",
    }
    args.output.with_suffix(args.output.suffix + ".json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8")
    print(f"wrote {written:,} records: {parents:,} parent + {children:,} policy children")
    print(f"skipped {skipped_policy:,} positions without usable policy; illegal labels={illegal:,}")
    print("existing value trainers: use this source with k=0")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
