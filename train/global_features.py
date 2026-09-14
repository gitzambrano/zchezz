"""Perspective-relative global chess features for NNU4 side-channel experiments.

The 31 values intentionally mirror the manual features used by v3.28 NNU3:
  0..5   own P/N/B/R/Q/K counts divided by 8/2/2/2/1/1
  6..11  opponent counts with the same normalization
  12     total non-king material divided by 78 (P=1,N=3,B=3,R=5,Q=9)
  13     constant 1
  14..21 own passed-pawn presence by file a..h
  22..29 opponent passed-pawn presence by file a..h
  30     Chebyshev king distance divided by 7

Values are not clipped: promotions may legitimately make normalized piece counts
or material exceed one, matching the v3.28 feature definition.
"""
from __future__ import annotations

import numpy as np

MAX_COUNTS = np.asarray([8.0, 2.0, 2.0, 2.0, 1.0, 1.0], dtype=np.float32)
MAT_VALUES = np.asarray([1.0, 3.0, 3.0, 5.0, 9.0, 0.0], dtype=np.float32)
GLOBAL_DIM = 31


def _passed_files(board, color: bool) -> np.ndarray:
    """Return 8 float flags indicating whether `color` has a passed pawn per file."""
    import chess

    flags = np.zeros(8, dtype=np.float32)
    own = board.pieces(chess.PAWN, color)
    opp = board.pieces(chess.PAWN, not color)
    opp_squares = list(opp)
    for sq in own:
        f = chess.square_file(sq)
        r = chess.square_rank(sq)
        passed = True
        for osq in opp_squares:
            of = chess.square_file(osq)
            if abs(of - f) > 1:
                continue
            orank = chess.square_rank(osq)
            if (color == chess.WHITE and orank > r) or (color == chess.BLACK and orank < r):
                passed = False
                break
        if passed:
            flags[f] = 1.0
    return flags


def global_features_board(board, perspective: bool) -> np.ndarray:
    """Return the 31 v3-style features from `perspective` (chess.WHITE/BLACK)."""
    import chess

    out = np.zeros(GLOBAL_DIM, dtype=np.float32)
    piece_types = (chess.PAWN, chess.KNIGHT, chess.BISHOP, chess.ROOK, chess.QUEEN, chess.KING)
    own_counts = np.asarray([len(board.pieces(pt, perspective)) for pt in piece_types], dtype=np.float32)
    opp_counts = np.asarray([len(board.pieces(pt, not perspective)) for pt in piece_types], dtype=np.float32)
    out[0:6] = own_counts / MAX_COUNTS
    out[6:12] = opp_counts / MAX_COUNTS

    white_counts = np.asarray([len(board.pieces(pt, chess.WHITE)) for pt in piece_types], dtype=np.float32)
    black_counts = np.asarray([len(board.pieces(pt, chess.BLACK)) for pt in piece_types], dtype=np.float32)
    out[12] = float(np.dot(white_counts + black_counts, MAT_VALUES) / 78.0)
    out[13] = 1.0
    out[14:22] = _passed_files(board, perspective)
    out[22:30] = _passed_files(board, not perspective)

    wk = board.king(chess.WHITE)
    bk = board.king(chess.BLACK)
    if wk is not None and bk is not None:
        df = abs(chess.square_file(wk) - chess.square_file(bk))
        dr = abs(chess.square_rank(wk) - chess.square_rank(bk))
        out[30] = max(df, dr) / 7.0
    return out


def global_features_fen(fen: str) -> tuple[np.ndarray, np.ndarray]:
    """Return `(stm_features, opponent_features)` for one FEN."""
    import chess

    board = chess.Board(fen)
    stm = bool(board.turn)
    return global_features_board(board, stm), global_features_board(board, not stm)


def encode_global_features(fens: list[str]) -> tuple[np.ndarray, np.ndarray]:
    """Batch encoder returning float32 arrays shaped [N,31] for STM and opponent."""
    stm = np.empty((len(fens), GLOBAL_DIM), dtype=np.float32)
    opp = np.empty((len(fens), GLOBAL_DIM), dtype=np.float32)
    for i, fen in enumerate(fens):
        stm[i], opp[i] = global_features_fen(fen)
    return stm, opp


def quantize_features_256(x: np.ndarray) -> np.ndarray:
    """Match the runtime's Q8 feature representation (1.0 -> 256)."""
    x = np.asarray(x, dtype=np.float32)
    return np.rint(x * 256.0).astype(np.int32)
