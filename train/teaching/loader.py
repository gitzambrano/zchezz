"""Training-time adapters for architecture-neutral teaching datasets.

The on-disk corpus stores raw chess-domain labels. This module derives value
probabilities, soft policies, or pairwise move-order targets at training time,
so loss/temperature/top-k choices never require relabeling the corpus.

The file is both importable as ``train.teaching.loader`` and directly
executable as required by the repository bare-run convention.
"""
from __future__ import annotations

import math
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from train.teaching.format import (  # noqa: E402
    MISSING_CP, TeachingDataset, move_scores_to_policy, unpack_move_uci,
)

VALUE_SCALE_CP = 320.0


def choose_value_cp(row, mode: str = "search-preferred") -> int | None:
    """Choose a raw White-relative centipawn target from one position row."""
    fields = {
        "search": ("search_cp",),
        "static": ("static_cp",),
        "source": ("source_cp",),
        "student": ("student_cp",),
        "search-preferred": ("search_cp", "static_cp", "source_cp"),
        "teacher": ("search_cp", "static_cp"),
    }
    if mode not in fields:
        raise ValueError(f"unknown value mode {mode!r}; choose {', '.join(fields)}")
    for field in fields[mode]:
        value = int(row[field])
        if value != MISSING_CP:
            return value
    return None


def cp_to_probability(cp: float, scale_cp: float = VALUE_SCALE_CP) -> float:
    x = max(-60.0, min(60.0, float(cp) / float(scale_cp)))
    return 1.0 / (1.0 + math.exp(-x))


def value_target(row, mode: str = "search-preferred",
                 perspective: str = "stm", scale_cp: float = VALUE_SCALE_CP) -> float | None:
    """Return a 0..1 value target, optionally normalized to side-to-move POV."""
    cp = choose_value_cp(row, mode)
    if cp is None:
        return None
    p_white = cp_to_probability(cp, scale_cp)
    if perspective == "white":
        return p_white
    if perspective != "stm":
        raise ValueError("perspective must be 'white' or 'stm'")
    return p_white if int(row["stm"]) == 0 else 1.0 - p_white


def policy_target(dataset: TeachingDataset, index: int,
                  temperature_cp: float = 120.0, top_k: int = 0,
                  prefer_search: bool = True) -> tuple[list[str], np.ndarray]:
    """Return legal UCI move labels and a derived soft policy for one row."""
    row = dataset.positions[index]
    moves = dataset.moves_for(index)
    packed, probability = move_scores_to_policy(
        moves, white_to_move=int(row["stm"]) == 0,
        temperature_cp=temperature_cp, prefer_search=prefer_search, top_k=top_k)
    return [unpack_move_uci(int(move)) for move in packed], probability


def pairwise_policy_targets(dataset: TeachingDataset, index: int,
                            min_margin_cp: float = 20.0,
                            prefer_search: bool = True) -> list[tuple[str, str, float]]:
    """Derive (better_move, worse_move, cp_margin) move-order supervision."""
    row = dataset.positions[index]
    moves = dataset.moves_for(index)
    scored = []
    sign = 1.0 if int(row["stm"]) == 0 else -1.0
    for move in moves:
        score = int(move["search_cp"]) if prefer_search else MISSING_CP
        if score == MISSING_CP:
            score = int(move["static_cp"])
        if score != MISSING_CP:
            scored.append((unpack_move_uci(int(move["move"])), sign * float(score)))
    scored.sort(key=lambda item: item[1], reverse=True)
    pairs = []
    for i, (better, better_score) in enumerate(scored):
        for worse, worse_score in scored[i + 1:]:
            margin = better_score - worse_score
            if margin >= min_margin_cp:
                pairs.append((better, worse, margin))
    return pairs


class TeachingBatchAdapter:
    """Memory-mapped value/policy adapter shared by current and future trainers."""

    def __init__(self, root: str | Path):
        self.dataset = TeachingDataset(root)

    def value_batch(self, indices, mode: str = "search-preferred",
                    perspective: str = "stm", scale_cp: float = VALUE_SCALE_CP):
        rows = self.dataset.positions[np.asarray(indices, dtype=np.int64)]
        targets = np.full(len(rows), np.nan, dtype=np.float32)
        valid = np.zeros(len(rows), dtype=np.bool_)
        for i, row in enumerate(rows):
            target = value_target(row, mode, perspective, scale_cp)
            if target is not None:
                targets[i] = target
                valid[i] = True
        return rows, targets, valid


if __name__ == "__main__":
    print("Teaching loader ready: value, soft-policy, and pairwise move-order targets.")
