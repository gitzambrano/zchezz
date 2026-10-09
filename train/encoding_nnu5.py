"""train/encoding_nnu5.py — HalfKAv2_hm-32Bucket feature encoding (Zchezz v6.00 NNU5)

Feature specification:
  - 32 King Buckets:
      4 files (a-d; e-h mirrored horizontally) x 8 ranks = 32 buckets.
  - Relative piece planes (11 planes per square):
      Ally  P, N, B, R, Q -> 0, 1, 2, 3, 4
      Enemy P, N, B, R, Q -> 5, 6, 7, 8, 9
      Enemy King          -> 10
      (Perspective king is NOT a feature plane; it selects the king bucket)
  - Features per bucket: 11 * 64 = 704
  - Total sparse features: 32 * 704 = 22,528
"""
from __future__ import annotations

import chess
import numpy as np

NN_KING_BUCKETS = 32
NN_FEAT_PER_BUCKET = 704          # 11 relative piece planes x 64 squares
NN_FEAT_IN = 22528                # NN_KING_BUCKETS * NN_FEAT_PER_BUCKET
MAX_ACTIVE_FEATURES = 62
LEGAL_MAX_ACTIVE_FEATURES = 31

_PIECE_TYPE_TO_REL = {
    chess.PAWN: 0,
    chess.KNIGHT: 1,
    chess.BISHOP: 2,
    chess.ROOK: 3,
    chess.QUEEN: 4,
}


def king_bucket(pov_square: int) -> tuple[int, bool]:
    """King bucket and horizontal mirroring flag for a POV king square.

    pov_square: 0=a1 .. 63=h8 in POV coordinates.
    Files 0..3 (a-d): no flip (hm=False).
    Files 4..7 (e-h): horizontal flip (hm=True, file -> 7 - file).
    Bucket index: rank * 4 + file_hm in 0..31.
    """
    rank = pov_square // 8
    file = pov_square % 8
    if file >= 4:
        return rank * 4 + (7 - file), True
    return rank * 4 + file, False


def king_buckets_of(board: chess.Board) -> tuple[tuple[int, bool], tuple[int, bool]]:
    """(white_bucket, black_bucket) each as (bucket_idx, hm_flag)."""
    wk = board.king(chess.WHITE)
    bk = board.king(chess.BLACK)
    bw = king_bucket(wk) if wk is not None else (0, False)
    bb = king_bucket(bk ^ 56) if bk is not None else (0, False)
    return bw, bb


def halfkp_active_indices(board: chess.Board, pov_is_white: bool) -> np.ndarray:
    """Return active NNU5 feature indices for the given perspective."""
    ally_color = chess.WHITE if pov_is_white else chess.BLACK
    enemy_color = chess.BLACK if pov_is_white else chess.WHITE

    k_sq = board.king(ally_color)
    if k_sq is None:
        return np.empty(0, dtype=np.int32)

    k_pov = k_sq if pov_is_white else (k_sq ^ 56)
    bucket, hm = king_bucket(k_pov)
    base = bucket * NN_FEAT_PER_BUCKET

    indices: list[int] = []

    for sq, piece in board.piece_map().items():
        if piece.color == ally_color and piece.piece_type == chess.KING:
            continue

        pov_sq = sq if pov_is_white else (sq ^ 56)
        if hm:
            pov_sq ^= 7

        if piece.color == ally_color:
            rel = _PIECE_TYPE_TO_REL[piece.piece_type]
        else:
            if piece.piece_type == chess.KING:
                rel = 10
            else:
                rel = 5 + _PIECE_TYPE_TO_REL[piece.piece_type]

        indices.append(base + rel * 64 + pov_sq)

    return np.array(sorted(indices), dtype=np.int32)


def _bag(idx_lists: list[np.ndarray]) -> tuple[np.ndarray, np.ndarray]:
    counts = [len(x) for x in idx_lists]
    offsets = np.zeros(len(idx_lists), dtype=np.int64)
    if len(idx_lists) > 1:
        offsets[1:] = np.cumsum(counts)[:-1]
    flat = np.concatenate(idx_lists) if counts and sum(counts) else np.empty(0, dtype=np.int32)
    return flat.astype(np.int32), offsets


def encode_positions(fens: list[str]) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """Encode a list of FEN strings to sparse EmbeddingBag inputs (stm, opp)."""
    stm_lists: list[np.ndarray] = []
    opp_lists: list[np.ndarray] = []

    for fen in fens:
        board = chess.Board(fen)
        stm_is_white = board.turn == chess.WHITE
        stm_lists.append(halfkp_active_indices(board, pov_is_white=stm_is_white))
        opp_lists.append(halfkp_active_indices(board, pov_is_white=not stm_is_white))

    stm_idx, stm_off = _bag(stm_lists)
    opp_idx, opp_off = _bag(opp_lists)
    return stm_idx, stm_off, opp_idx, opp_off


def encode_mailbox_batch(boards: np.ndarray, stms: np.ndarray
                          ) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """Vectorized NNU5 sparse encoder directly from packed mailbox board arrays."""
    boards = np.asarray(boards)
    stms = np.asarray(stms)
    n = boards.shape[0]
    if n == 0:
        empty = np.empty(0, dtype=np.int32)
        zero_off = np.zeros(0, dtype=np.int64)
        return empty, zero_off, empty, zero_off

    codes = boards.astype(np.int32)
    color = codes & 24            # 8=white, 16=black, 0=empty
    ptype = codes & 7             # 1..6 (P,N,B,R,Q,K), 0=empty
    occupied = codes != 0
    is_king = ptype == 6

    zsq_idx = np.arange(64, dtype=np.int32)   # 0=a8..63=h1
    sq_w = zsq_idx ^ 56                        # 0=a1..63=h8

    def _perspective(color_bit: int, pov_is_white: bool):
        ally_king_mask = is_king & (color == color_bit)
        has_king = ally_king_mask.any(axis=1)
        king_zsq = np.argmax(ally_king_mask, axis=1).astype(np.int32)
        king_pov = (king_zsq ^ 56) if pov_is_white else king_zsq

        k_rank = king_pov >> 3
        k_file = king_pov & 7
        hm = k_file >= 4
        file_hm = np.where(hm, 7 - k_file, k_file)
        bucket = (k_rank * 4 + file_hm).astype(np.int32)
        base = bucket * NN_FEAT_PER_BUCKET                       # (N,)

        is_ally = color == color_bit                              # (N, 64)
        is_enemy = (color != color_bit) & occupied

        # Relative piece planes:
        # Ally non-king: 0..4
        # Enemy non-king: 5..9
        # Enemy king: 10
        rel_type = np.zeros_like(codes)
        # For non-kings: ptype 1..5 -> 0..4
        rel_type = np.where(is_ally & ~is_king, ptype - 1, rel_type)
        rel_type = np.where(is_enemy & ~is_king, 5 + (ptype - 1), rel_type)
        rel_type = np.where(is_enemy & is_king, 10, rel_type)

        pov_sq = sq_w if pov_is_white else zsq_idx                # (64,)
        # Broadcast POV square with horizontal mirroring per position
        hm_sq = pov_sq[None, :] ^ np.where(hm[:, None], 7, 0)     # (N, 64)

        feat = base[:, None] + rel_type * 64 + hm_sq

        # Active features are all pieces except the ally king
        valid = occupied & ~(is_king & is_ally) & has_king[:, None]
        return feat.astype(np.int32), valid

    white_feat, white_valid = _perspective(8, True)
    black_feat, black_valid = _perspective(16, False)

    is_white_stm = (stms == 0)[:, None]
    stm_feat = np.where(is_white_stm, white_feat, black_feat)
    stm_valid = np.where(is_white_stm, white_valid, black_valid)
    opp_feat = np.where(is_white_stm, black_feat, white_feat)
    opp_valid = np.where(is_white_stm, black_valid, white_valid)

    def _pack(feat: np.ndarray, valid: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        counts = valid.sum(axis=1).astype(np.int64)
        offsets = np.zeros(n, dtype=np.int64)
        if n > 1:
            offsets[1:] = np.cumsum(counts)[:-1]
        flat = feat[valid].astype(np.int32)
        return flat, offsets

    stm_idx, stm_off = _pack(stm_feat, stm_valid)
    opp_idx, opp_off = _pack(opp_feat, opp_valid)
    return stm_idx, stm_off, opp_idx, opp_off
