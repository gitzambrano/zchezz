import sys
from pathlib import Path

import numpy as np
import chess

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(ROOT / "train") not in sys.path:
    sys.path.insert(0, str(ROOT / "train"))

from train.teaching.export_policy_children import board_to_sample, select_policy_children
from train.teaching.format import MOVE_DTYPE, POSITION_DTYPE, pack_move_uci


def _row(stm=0, flags=0):
    r = np.zeros(1, dtype=POSITION_DTYPE)[0]
    r["stm"] = stm
    r["flags"] = flags
    return r


def _moves(items):
    out = np.zeros(len(items), dtype=MOVE_DTYPE)
    for i, (uci, cp) in enumerate(items):
        out[i]["move"] = pack_move_uci(uci)
        out[i]["static_cp"] = cp
        out[i]["search_cp"] = -32768
    return out


def test_child_sample_flips_white_cp_to_child_stm_frame():
    board = chess.Board()
    board.push_uci("e2e4")
    rec = board_to_sample(board, 30)
    assert int(rec["stm"]) == 1
    assert int(rec["eval_cp"]) == -30
    assert int(rec["ep_file"]) == 4
    assert int(rec["board"][chess.E4 ^ 56]) == 9


def test_white_and_black_policy_sort_in_parent_pov():
    white = select_policy_children(
        _row(stm=0), _moves([("e2e4", 40), ("d2d4", 25), ("g1f3", -10)]),
        top_k=1, near_best_cp=0, tail_k=0, max_children=1, hard_bonus_children=0)
    assert white[0][0] == pack_move_uci("e2e4")

    black = select_policy_children(
        _row(stm=1), _moves([("e7e5", 40), ("d7d5", 5), ("g8f6", -25)]),
        top_k=1, near_best_cp=0, tail_k=0, max_children=1, hard_bonus_children=0)
    assert black[0][0] == pack_move_uci("g8f6")


def test_selector_keeps_near_best_and_contrastive_tail():
    moves = _moves([
        ("e2e4", 100), ("d2d4", 75), ("g1f3", 50),
        ("c2c4", 10), ("b1c3", -20), ("a2a3", -100),
    ])
    chosen = select_policy_children(
        _row(stm=0), moves, top_k=1, near_best_cp=30,
        tail_k=1, max_children=4, hard_bonus_children=0)
    packed = [x[0] for x in chosen]
    assert pack_move_uci("e2e4") in packed
    assert pack_move_uci("d2d4") in packed
    assert pack_move_uci("a2a3") in packed
    assert len(packed) == len(set(packed))
