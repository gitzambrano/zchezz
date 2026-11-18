"""Contract: the dense lookahead target looks ahead inside the same game only.

Trainers sample a random subset of .bin rows, so the target must read later
plies by global index and stop at game and shard boundaries. The expected
value for every row is computed game by game with the single-game function.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "train"))

import dataset  # noqa: E402


def _game(n_plies: int, white_wins: bool, rng, first_stm: int = 0, pieces: int = 32):
    rec = np.zeros(n_plies, dtype=dataset.SAMPLE_DTYPE)
    for i in range(n_plies):
        stm = (first_stm + i) % 2
        rec[i]["stm"] = stm
        rec[i]["eval_cp"] = int(rng.integers(-600, 600))
        white_to_move = stm == 0
        rec[i]["game_result"] = 1 if white_to_move == white_wins else -1
        n_p = max(3, pieces - i // 3)                 # piece count never grows inside a game
        rec[i]["board"][:n_p] = 9
    return rec


def _write(path: Path, games):
    path.write_bytes(np.concatenate(games).tobytes())
    return str(path)


def test_indexed_lookahead_matches_per_game(tmp_path):
    rng = np.random.default_rng(3)
    shard_a = [_game(30, True, rng), _game(17, False, rng, first_stm=0), _game(25, True, rng, first_stm=1)]
    shard_b = [_game(40, False, rng)]
    pa = _write(tmp_path / "a.bin", shard_a)
    pb = _write(tmp_path / "b.bin", shard_b)
    ds = dataset.MultiShardSelfplay([pa, pb])

    expected = np.concatenate([dataset.dense_lookahead_target(g["eval_cp"], g["game_result"], k_res=0.1)
                               for g in shard_a + shard_b])
    idx = np.sort(rng.choice(len(ds), size=60, replace=False))
    got = dataset.dense_lookahead_target_indexed(ds, idx, k_res=0.1)
    np.testing.assert_allclose(got, expected[idx], rtol=0, atol=1e-6)


def test_batch_version_rejects_rows_from_several_games():
    """The guard sees only game_result, so it catches games whose outcomes break the alternation."""
    rng = np.random.default_rng(4)
    two = np.concatenate([_game(10, True, rng), _game(10, False, rng)])
    with pytest.raises(ValueError, match="consecutive plies"):
        dataset.dense_lookahead_target(two["eval_cp"], two["game_result"], k_res=0.1)


def test_default_bin_target_is_wl_target():
    rng = np.random.default_rng(5)
    g = _game(12, True, rng)
    _, y = dataset.records_to_fens_and_targets(g, k=0.0)
    expected = 1.0 / (1.0 + np.exp(-g["eval_cp"].astype(np.float32) / dataset.CP_TO_PROB_TEMPERATURE))
    np.testing.assert_allclose(y, expected, atol=1e-6)
