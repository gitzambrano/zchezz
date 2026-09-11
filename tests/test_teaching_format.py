from pathlib import Path
import sys

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from train.teaching.format import (  # noqa: E402
    MISSING_CP, MOVE_DTYPE, POSITION_DTYPE, TeachingDataset, TeachingWriter,
    move_scores_to_policy, pack_move_uci, unpack_move_uci,
)


def test_move_pack_roundtrip():
    for uci in ("e2e4", "a7a8q", "h2h1n", "b1c3"):
        assert unpack_move_uci(pack_move_uci(uci)) == uci


def test_teaching_binary_roundtrip(tmp_path):
    position = np.zeros(1, dtype=POSITION_DTYPE)
    position[0]["board"][0] = 4
    position[0]["static_cp"] = 25
    position[0]["search_cp"] = MISSING_CP
    moves = np.zeros(2, dtype=MOVE_DTYPE)
    moves[0]["move"] = pack_move_uci("e2e4")
    moves[0]["static_cp"] = 30
    moves[0]["search_cp"] = MISSING_CP
    moves[1]["move"] = pack_move_uci("d2d4")
    moves[1]["static_cp"] = 20
    moves[1]["search_cp"] = MISSING_CP
    with TeachingWriter(tmp_path, {"teacher": "unit"}) as writer:
        writer.write(position, moves)
    dataset = TeachingDataset(tmp_path)
    assert len(dataset) == 1
    assert len(dataset.moves_for(0)) == 2
    assert int(dataset.positions[0]["policy_offset"]) == 0
    assert int(dataset.positions[0]["policy_count"]) == 2
    assert dataset.metadata["score_pov"] == "white"


def test_policy_is_derived_and_respects_side_to_move():
    moves = np.zeros(2, dtype=MOVE_DTYPE)
    moves[0]["move"] = pack_move_uci("e2e4")
    moves[0]["static_cp"] = 100
    moves[0]["search_cp"] = MISSING_CP
    moves[1]["move"] = pack_move_uci("d2d4")
    moves[1]["static_cp"] = 0
    moves[1]["search_cp"] = MISSING_CP
    _, white = move_scores_to_policy(moves, True, 100)
    _, black = move_scores_to_policy(moves, False, 100)
    assert white[0] > white[1]
    assert black[0] < black[1]
    assert np.isclose(white.sum(), 1.0)


def test_empty_dataset_is_readable(tmp_path):
    with TeachingWriter(tmp_path, {"teacher": "unit"}):
        pass
    dataset = TeachingDataset(tmp_path)
    assert len(dataset) == 0
    assert len(dataset.moves) == 0


def test_resume_rejects_recipe_changes_but_allows_operational_changes(tmp_path):
    base = {
        "teacher": "unit",
        "inputs": ["a.bin"],
        "methods": ["static_value"],
        "config": {"WORKERS": 2, "BATCH_SIZE": 64, "SHALLOW_NODES": 2000},
    }
    with TeachingWriter(tmp_path, base):
        pass
    operational = {
        **base,
        "config": {"WORKERS": 8, "BATCH_SIZE": 512, "SHALLOW_NODES": 2000},
    }
    with TeachingWriter(tmp_path, operational, append=True):
        pass
    changed_recipe = {
        **base,
        "config": {"WORKERS": 8, "BATCH_SIZE": 512, "SHALLOW_NODES": 4000},
    }
    with pytest.raises(ValueError, match="different teacher/labeling recipe"):
        TeachingWriter(tmp_path, changed_recipe, append=True)
