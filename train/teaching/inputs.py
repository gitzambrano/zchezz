"""Streaming architecture-neutral position sources for the teaching pipeline."""
from __future__ import annotations

import glob
import hashlib
import random
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator

ROOT = Path(__file__).resolve().parents[2]
TRAIN = ROOT / "train"
if str(TRAIN) not in sys.path:
    sys.path.insert(0, str(TRAIN))


@dataclass
class SourcePosition:
    fen: str
    source_cp: int | None = None
    result_wdl: int = 2
    source_tag: int = 0
    generated: bool = False


def source_tag(path: str | Path) -> int:
    h = hashlib.blake2s(str(path).encode("utf-8"), digest_size=4).digest()
    return int.from_bytes(h, "little")


def _result_token(token: str | None) -> int:
    return {"0-1": -1, "1/2-1/2": 0, "1-0": 1}.get(
        (token or "").strip(), 2)


def iter_epd(path: Path) -> Iterator[SourcePosition]:
    cp_re = re.compile(r'(?:c1|ce)\s+"?([+-]?\d+(?:\.\d+)?)')
    res_re = re.compile(r'(?:c0|result)\s+"(1-0|0-1|1/2-1/2)"')
    tag = source_tag(path)
    with path.open("r", encoding="utf-8", errors="replace") as handle:
        for raw in handle:
            line = raw.strip()
            if not line or line.startswith("#"):
                continue
            fields = line.split()
            if len(fields) < 4:
                continue
            fen = " ".join(fields[:4]) + " 0 1"
            match = cp_re.search(line)
            cp = int(round(float(match.group(1)))) if match else None
            result_match = res_re.search(line)
            result = _result_token(
                result_match.group(1) if result_match else None)
            yield SourcePosition(fen, cp, result, tag)


def iter_fen(path: Path) -> Iterator[SourcePosition]:
    tag = source_tag(path)
    with path.open("r", encoding="utf-8", errors="replace") as handle:
        for raw in handle:
            line = raw.strip()
            if not line or line.startswith("#"):
                continue
            fields = line.split()
            if len(fields) < 4:
                continue
            fen = " ".join(
                fields[:6] if len(fields) >= 6
                else fields[:4] + ["0", "1"])
            yield SourcePosition(fen, source_tag=tag)


def iter_pgn(path: Path, skip_plies: int = 0,
             max_plies: int = 0) -> Iterator[SourcePosition]:
    import chess.pgn

    tag = source_tag(path)
    with path.open("r", encoding="utf-8", errors="replace") as handle:
        while True:
            game = chess.pgn.read_game(handle)
            if game is None:
                break
            result = _result_token(game.headers.get("Result"))
            board = game.board()
            for ply, move in enumerate(game.mainline_moves()):
                if ply >= skip_plies:
                    yield SourcePosition(board.fen(), None, result, tag)
                board.push(move)
                if max_plies and ply + 1 >= max_plies:
                    break


def iter_bin(path: Path) -> Iterator[SourcePosition]:
    import numpy as np
    import chess
    from dataset import HEADER_DTYPE, SAMPLE_DTYPE, SAMPLE_FILE_MAGIC

    offset = 0
    with path.open("rb") as handle:
        magic = handle.read(8)
        if magic == SAMPLE_FILE_MAGIC:
            handle.seek(0)
            header = np.fromfile(handle, dtype=HEADER_DTYPE, count=1)
            if len(header) != 1:
                return
            offset = int(header[0]["header_size"])
    size = path.stat().st_size - offset
    if size < 0 or size % SAMPLE_DTYPE.itemsize:
        raise ValueError(f"bad Zchezz sample file size: {path}")
    rows = np.memmap(path, dtype=SAMPLE_DTYPE, mode="r", offset=offset)
    tag = source_tag(path)
    pieces = {}
    for piece_type in range(1, 7):
        pieces[8 | piece_type] = chess.Piece(piece_type, chess.WHITE)
        pieces[16 | piece_type] = chess.Piece(piece_type, chess.BLACK)

    for rec in rows:
        board = chess.Board(fen=None)
        for zsq, code in enumerate(rec["board"]):
            piece = pieces.get(int(code))
            if piece:
                board.set_piece_at(zsq ^ 56, piece)
        board.turn = chess.WHITE if int(rec["stm"]) == 0 else chess.BLACK
        castling = int(rec["castling"])
        rights = chess.BB_EMPTY
        if castling & 1:
            rights |= chess.BB_H1
        if castling & 2:
            rights |= chess.BB_A1
        if castling & 4:
            rights |= chess.BB_H8
        if castling & 8:
            rights |= chess.BB_A8
        board.castling_rights = rights
        ep_file = int(rec["ep_file"])
        if 0 <= ep_file <= 7:
            board.ep_square = chess.square(
                ep_file, 5 if board.turn else 2)
        board.halfmove_clock = int(rec["rule50"])
        board.fullmove_number = 1

        cp_stm = int(rec["eval_cp"])
        cp_white = cp_stm if board.turn else -cp_stm
        result_stm = int(rec["game_result"])
        result_white = result_stm if board.turn else -result_stm
        yield SourcePosition(
            board.fen(), cp_white, max(-1, min(1, result_white)), tag)


def expand_inputs(inputs: list[str]) -> list[Path]:
    extensions = {".epd", ".fen", ".pgn", ".bin"}
    output = []
    for raw in inputs:
        matches = (
            glob.glob(raw, recursive=True)
            if any(char in raw for char in "*?[") else [raw])
        for match in matches:
            path = Path(match)
            if path.is_dir():
                output.extend(
                    candidate for candidate in path.rglob("*")
                    if candidate.suffix.lower() in extensions)
            elif path.is_file() and path.suffix.lower() in extensions:
                output.append(path)

    seen = set()
    answer = []
    for path in sorted(output):
        key = str(path.resolve())
        if key not in seen:
            seen.add(key)
            answer.append(path)
    return answer


def iter_inputs(inputs: list[str], *, pgn_skip_plies: int = 0,
                pgn_max_plies: int = 0) -> Iterator[SourcePosition]:
    for path in expand_inputs(inputs):
        extension = path.suffix.lower()
        if extension == ".epd":
            yield from iter_epd(path)
        elif extension == ".fen":
            yield from iter_fen(path)
        elif extension == ".pgn":
            yield from iter_pgn(path, pgn_skip_plies, pgn_max_plies)
        elif extension == ".bin":
            yield from iter_bin(path)


def iter_random_positions(count: int, min_plies: int,
                          max_plies: int, seed: int) -> Iterator[SourcePosition]:
    import chess

    rng = random.Random(seed)
    tag = source_tag(f"random:{seed}")
    made = 0
    while made < count:
        board = chess.Board()
        target = rng.randint(max(0, min_plies), max(min_plies, max_plies))
        for _ in range(target):
            if board.is_game_over():
                break
            moves = list(board.legal_moves)
            if not moves:
                break
            board.push(rng.choice(moves))
        if not board.is_game_over():
            yield SourcePosition(board.fen(), None, 2, tag, True)
            made += 1
