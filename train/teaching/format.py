"""Architecture-neutral binary format for Zchezz teacher datasets.

A teaching dataset is a directory with three files:
  metadata.json  run-level provenance and the format contract
  positions.bin  fixed-size POSITION_DTYPE records
  moves.bin      sparse MOVE_DTYPE records referenced by offset/count

All evaluation scores are WHITE-relative centipawns. The board encoding is
chess-domain data, not an NNUE feature layout: squares are a1..h8 and piece
codes are 0 empty, 1..6 white P/N/B/R/Q/K, 7..12 black P/N/B/R/Q/K.
"""
from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Sequence

import numpy as np

MAGIC = "ZCHEZZ_TEACH_V1"
FORMAT_VERSION = 1
MISSING_CP = -32768
UNKNOWN_RESULT = 2
MATE_CP = 30000

FLAG_QUIET = 1 << 0
FLAG_IN_CHECK = 1 << 1
FLAG_TERMINAL = 1 << 2
FLAG_TACTICAL = 1 << 3
FLAG_HARD = 1 << 4
FLAG_DISAGREEMENT = 1 << 5
FLAG_LOW_MARGIN = 1 << 6
FLAG_HIGH_ENTROPY = 1 << 7
FLAG_SEARCH_REFINED = 1 << 8
FLAG_DEEP_REFINED = 1 << 9
FLAG_GENERATED = 1 << 10
FLAG_SOURCE_CP = 1 << 11
FLAG_POLICY = 1 << 12

METHOD_STATIC_VALUE = 1 << 0
METHOD_STATIC_POLICY = 1 << 1
METHOD_SHALLOW_SEARCH = 1 << 2
METHOD_DEEP_SEARCH = 1 << 3
METHOD_GAP_MINING = 1 << 4
METHOD_RANDOM_GENERATION = 1 << 5
METHOD_EXTERNAL_STUDENT = 1 << 6

POSITION_DTYPE = np.dtype([
    ("board", "u1", (64,)),
    ("stm", "u1"),
    ("castling", "u1"),
    ("ep_square", "u1"),
    ("rule50", "u1"),
    ("fullmove", "<u2"),
    ("result_wdl", "i1"),
    ("source_cp", "<i2"),
    ("static_cp", "<i2"),
    ("search_cp", "<i2"),
    ("student_cp", "<i2"),
    ("interest", "<f4"),
    ("policy_offset", "<u8"),
    ("policy_count", "<u2"),
    ("flags", "<u4"),
    ("methods", "<u4"),
    ("search_nodes", "<u4"),
    ("source_tag", "<u4"),
], align=False)

MOVE_DTYPE = np.dtype([
    ("move", "<u2"),
    ("static_cp", "<i2"),
    ("search_cp", "<i2"),
    ("rank_static", "<u2"),
    ("rank_search", "<u2"),
    ("flags", "<u2"),
], align=False)


def missing_cp(value: int | None) -> np.int16:
    if value is None:
        return np.int16(MISSING_CP)
    return np.int16(max(-32000, min(32000, int(round(value)))))


def cp_or_none(value: int) -> int | None:
    value = int(value)
    return None if value == MISSING_CP else value


def pack_move_uci(uci: str) -> int:
    """Pack a normal UCI move without depending on Zchezz pack_move()."""
    if len(uci) < 4:
        raise ValueError(f"invalid UCI move {uci!r}")

    def sq(token: str) -> int:
        f = ord(token[0]) - ord("a")
        r = ord(token[1]) - ord("1")
        if not (0 <= f < 8 and 0 <= r < 8):
            raise ValueError(f"invalid UCI square {token!r}")
        return r * 8 + f

    fr, to = sq(uci[:2]), sq(uci[2:4])
    promo = 0
    if len(uci) >= 5:
        promo = {"n": 1, "b": 2, "r": 3, "q": 4}.get(uci[4].lower(), 0)
    return fr | (to << 6) | (promo << 12)


def unpack_move_uci(value: int) -> str:
    value = int(value)

    def name(s: int) -> str:
        return chr(ord("a") + (s & 7)) + chr(ord("1") + (s >> 3))

    fr = value & 63
    to = (value >> 6) & 63
    promo = (value >> 12) & 7
    return name(fr) + name(to) + {0: "", 1: "n", 2: "b", 3: "r", 4: "q"}.get(promo, "")


def board_to_codes(board) -> np.ndarray:
    out = np.zeros(64, dtype=np.uint8)
    for square, piece in board.piece_map().items():
        out[square] = piece.piece_type + (0 if piece.color else 6)
    return out


def fill_position_board(rec, board) -> None:
    rec["board"] = board_to_codes(board)
    rec["stm"] = 0 if board.turn else 1
    rec["castling"] = (
        (1 if board.has_kingside_castling_rights(True) else 0)
        | (2 if board.has_queenside_castling_rights(True) else 0)
        | (4 if board.has_kingside_castling_rights(False) else 0)
        | (8 if board.has_queenside_castling_rights(False) else 0)
    )
    rec["ep_square"] = 64 if board.ep_square is None else int(board.ep_square)
    rec["rule50"] = min(255, int(board.halfmove_clock))
    rec["fullmove"] = min(65535, max(1, int(board.fullmove_number)))


def record_to_fen(rec) -> str:
    """Decode a POSITION_DTYPE record to FEN. Imports python-chess lazily."""
    import chess

    board = chess.Board(fen=None)
    for square, code in enumerate(rec["board"]):
        code = int(code)
        if not code:
            continue
        color = chess.WHITE if code <= 6 else chess.BLACK
        piece_type = code if code <= 6 else code - 6
        board.set_piece_at(square, chess.Piece(piece_type, color))
    board.turn = chess.WHITE if int(rec["stm"]) == 0 else chess.BLACK
    rights = chess.BB_EMPTY
    ca = int(rec["castling"])
    if ca & 1:
        rights |= chess.BB_H1
    if ca & 2:
        rights |= chess.BB_A1
    if ca & 4:
        rights |= chess.BB_H8
    if ca & 8:
        rights |= chess.BB_A8
    board.castling_rights = rights
    ep = int(rec["ep_square"])
    board.ep_square = None if ep >= 64 else ep
    board.halfmove_clock = int(rec["rule50"])
    board.fullmove_number = max(1, int(rec["fullmove"]))
    return board.fen()


def move_scores_to_policy(moves: np.ndarray, white_to_move: bool,
                          temperature_cp: float = 120.0,
                          prefer_search: bool = True,
                          top_k: int = 0) -> tuple[np.ndarray, np.ndarray]:
    """Derive a soft policy without baking temperature into the dataset."""
    if len(moves) == 0:
        return np.empty(0, dtype=np.uint16), np.empty(0, dtype=np.float32)
    scores = np.empty(len(moves), dtype=np.float64)
    valid = np.zeros(len(moves), dtype=bool)
    for i, row in enumerate(moves):
        score = cp_or_none(row["search_cp"]) if prefer_search else None
        if score is None:
            score = cp_or_none(row["static_cp"])
        if score is not None:
            scores[i] = float(score if white_to_move else -score)
            valid[i] = True
        else:
            scores[i] = -1e9
    if not valid.any():
        return moves["move"].copy(), np.full(
            len(moves), 1.0 / len(moves), dtype=np.float32)
    if top_k and top_k < valid.sum():
        order = np.argsort(-scores)
        keep = np.zeros(len(moves), dtype=bool)
        keep[order[:top_k]] = True
        valid &= keep
        scores[~valid] = -1e9
    temperature = max(float(temperature_cp), 1e-6)
    z = scores / temperature
    z[valid] -= np.max(z[valid])
    probability = np.zeros(len(moves), dtype=np.float64)
    probability[valid] = np.exp(z[valid])
    probability /= probability.sum()
    return moves["move"].copy(), probability.astype(np.float32)


class TeachingWriter:
    def __init__(self, root: str | os.PathLike, metadata: dict | None = None,
                 append: bool = False):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self.meta_path = self.root / "metadata.json"
        self.pos_path = self.root / "positions.bin"
        self.move_path = self.root / "moves.bin"
        self.metadata = dict(metadata or {})
        if append and self.meta_path.exists():
            old = json.loads(self.meta_path.read_text(encoding="utf-8"))
            self._validate_meta(old)
            old.update(self.metadata)
            self.metadata = old
        elif not append:
            self.pos_path.write_bytes(b"")
            self.move_path.write_bytes(b"")
        self.pos_f = self.pos_path.open("ab")
        self.move_f = self.move_path.open("ab")
        self.positions = self.pos_path.stat().st_size // POSITION_DTYPE.itemsize
        self.moves = self.move_path.stat().st_size // MOVE_DTYPE.itemsize
        self._write_meta()

    @staticmethod
    def _validate_meta(meta: dict) -> None:
        if meta.get("magic") != MAGIC or int(meta.get("version", -1)) != FORMAT_VERSION:
            raise ValueError("not a compatible Zchezz teaching dataset")
        if int(meta.get("position_itemsize", -1)) != POSITION_DTYPE.itemsize:
            raise ValueError("POSITION_DTYPE itemsize mismatch")
        if int(meta.get("move_itemsize", -1)) != MOVE_DTYPE.itemsize:
            raise ValueError("MOVE_DTYPE itemsize mismatch")

    def _write_meta(self) -> None:
        self.metadata.update({
            "magic": MAGIC,
            "version": FORMAT_VERSION,
            "position_itemsize": POSITION_DTYPE.itemsize,
            "move_itemsize": MOVE_DTYPE.itemsize,
            "score_pov": "white",
            "score_unit": "centipawn",
            "board_encoding": "a1..h8; 0 empty; 1..6 white PNBRQK; 7..12 black PNBRQK",
            "positions": int(self.positions),
            "moves": int(self.moves),
            "updated_unix": int(time.time()),
        })
        tmp = self.meta_path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(self.metadata, indent=2, sort_keys=True),
                       encoding="utf-8")
        os.replace(tmp, self.meta_path)

    def write(self, position: np.ndarray, moves: np.ndarray | Sequence = ()) -> None:
        pos = np.asarray(position, dtype=POSITION_DTYPE).reshape(-1)
        if len(pos) != 1:
            raise ValueError("write() accepts exactly one position record")
        mov = np.asarray(moves, dtype=MOVE_DTYPE).reshape(-1)
        pos = pos.copy()
        pos[0]["policy_offset"] = self.moves
        pos[0]["policy_count"] = len(mov)
        pos.tofile(self.pos_f)
        if len(mov):
            mov.tofile(self.move_f)
        self.positions += 1
        self.moves += len(mov)

    def checkpoint(self, extra: dict | None = None) -> None:
        self.pos_f.flush()
        self.move_f.flush()
        if extra:
            self.metadata.update(extra)
        self._write_meta()

    def close(self, extra: dict | None = None) -> None:
        self.checkpoint(extra)
        self.pos_f.close()
        self.move_f.close()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        self.close({"complete": exc_type is None})


class TeachingDataset:
    def __init__(self, root: str | os.PathLike):
        self.root = Path(root)
        self.metadata = json.loads(
            (self.root / "metadata.json").read_text(encoding="utf-8"))
        TeachingWriter._validate_meta(self.metadata)
        pos_path = self.root / "positions.bin"
        move_path = self.root / "moves.bin"
        if pos_path.stat().st_size % POSITION_DTYPE.itemsize:
            raise ValueError("positions.bin size is not a multiple of POSITION_DTYPE")
        if move_path.stat().st_size % MOVE_DTYPE.itemsize:
            raise ValueError("moves.bin size is not a multiple of MOVE_DTYPE")
        self.positions = np.memmap(pos_path, dtype=POSITION_DTYPE, mode="r")
        self.moves = np.memmap(move_path, dtype=MOVE_DTYPE, mode="r")

    def __len__(self) -> int:
        return len(self.positions)

    def moves_for(self, index: int) -> np.ndarray:
        row = self.positions[index]
        offset = int(row["policy_offset"])
        count = int(row["policy_count"])
        if offset + count > len(self.moves):
            raise ValueError(f"position {index} points outside moves.bin")
        return self.moves[offset:offset + count]
