"""Composable teaching methods and active-learning metrics.

New methods register with @register("name") and receive one TeachingContext.
They can add labels, flags, move targets, or request more expensive work.
"""
from __future__ import annotations

import hashlib
import math
from dataclasses import dataclass, field
from typing import Callable

import numpy as np

from .format import (
    FLAG_DEEP_REFINED, FLAG_DISAGREEMENT, FLAG_HARD, FLAG_HIGH_ENTROPY,
    FLAG_LOW_MARGIN, FLAG_POLICY, FLAG_SEARCH_REFINED,
    METHOD_DEEP_SEARCH, METHOD_GAP_MINING, METHOD_SHALLOW_SEARCH,
    METHOD_STATIC_POLICY, METHOD_STATIC_VALUE, MISSING_CP, MOVE_DTYPE,
    pack_move_uci,
)

Method = Callable[["TeachingContext"], None]
REGISTRY: dict[str, Method] = {}


def register(name: str):
    def deco(fn: Method) -> Method:
        if name in REGISTRY:
            raise ValueError(f"duplicate teaching method {name}")
        REGISTRY[name] = fn
        return fn
    return deco


@dataclass
class TeachingContext:
    board: object
    backend: object
    cfg: object
    source_cp: int | None = None
    student_cp: int | None = None
    static_cp: int | None = None
    search_cp: int | None = None
    flags: int = 0
    methods: int = 0
    interest: float = 0.0
    search_nodes: int = 0
    moves: list[dict] = field(default_factory=list)

    @property
    def fen(self) -> str:
        return self.board.fen()


def stable_fraction(fen: str, salt: str = "policy") -> float:
    h = hashlib.blake2b((salt + "\0" + fen).encode("utf-8"), digest_size=8).digest()
    return int.from_bytes(h, "little") / float(1 << 64)


def policy_metrics(ctx: TeachingContext) -> tuple[float | None, float | None]:
    values = []
    for move in ctx.moves:
        cp = move.get("search_cp")
        if cp is None:
            cp = move.get("static_cp")
        if cp is not None:
            values.append(float(cp if ctx.board.turn else -cp))
    if len(values) < 2:
        return None, None
    values = np.asarray(values, dtype=np.float64)
    values.sort()
    values = values[::-1]
    margin = float(values[0] - values[1])
    temperature = max(1.0, float(ctx.cfg.POLICY_TEMPERATURE_CP))
    z = (values - values.max()) / temperature
    probability = np.exp(z)
    probability /= probability.sum()
    entropy = float(
        -(probability * np.log(np.maximum(probability, 1e-12))).sum()
        / math.log(len(probability)))
    return margin, entropy


def compute_interest(ctx: TeachingContext) -> float:
    score = 0.0
    teacher = ctx.search_cp if ctx.search_cp is not None else ctx.static_cp
    student = ctx.student_cp if ctx.student_cp is not None else ctx.source_cp
    if teacher is not None and student is not None:
        gap = abs(int(teacher) - int(student))
        score += min(1.0, gap / max(1.0, float(ctx.cfg.GAP_FULL_SCALE_CP))) * float(ctx.cfg.W_GAP)
        if gap >= int(ctx.cfg.GAP_HARD_CP):
            ctx.flags |= FLAG_DISAGREEMENT
    margin, entropy = policy_metrics(ctx)
    if margin is not None:
        low = max(0.0, 1.0 - margin / max(1.0, float(ctx.cfg.MARGIN_FULL_SCALE_CP)))
        score += low * float(ctx.cfg.W_MARGIN)
        if margin <= float(ctx.cfg.LOW_MARGIN_CP):
            ctx.flags |= FLAG_LOW_MARGIN
    if entropy is not None:
        score += entropy * float(ctx.cfg.W_ENTROPY)
        if entropy >= float(ctx.cfg.HIGH_ENTROPY):
            ctx.flags |= FLAG_HIGH_ENTROPY
    return float(score)


@register("static_value")
def static_value(ctx: TeachingContext) -> None:
    ctx.static_cp = int(ctx.backend.static_eval(ctx.fen, bool(ctx.board.turn)))
    ctx.methods |= METHOD_STATIC_VALUE


@register("gap_mining")
def gap_mining(ctx: TeachingContext) -> None:
    ctx.interest = compute_interest(ctx)
    ctx.methods |= METHOD_GAP_MINING
    if (ctx.flags & FLAG_DISAGREEMENT) or ctx.interest >= float(ctx.cfg.HARD_INTEREST):
        ctx.flags |= FLAG_HARD


@register("static_policy")
def static_policy(ctx: TeachingContext) -> None:
    # Every hard case plus a stable uniform sample gets per-child labels.
    should = bool(ctx.flags & FLAG_HARD) or (
        stable_fraction(ctx.fen) < float(ctx.cfg.POLICY_SAMPLE_RATE))
    if not should:
        return
    import chess

    rows = []
    parent_white = bool(ctx.board.turn)
    for move in list(ctx.board.legal_moves):
        uci = move.uci()
        ctx.board.push(move)
        if ctx.board.is_checkmate():
            # The side to move after push is mated.
            cp = -ctx.cfg.MATE_CP if ctx.board.turn == chess.WHITE else ctx.cfg.MATE_CP
        else:
            cp = int(ctx.backend.static_eval(ctx.board.fen(), bool(ctx.board.turn)))
        ctx.board.pop()
        rows.append({"uci": uci, "static_cp": int(cp), "search_cp": None})
    rows.sort(key=lambda x: x["static_cp"], reverse=parent_white)
    for rank, row in enumerate(rows):
        row["rank_static"] = rank
    ctx.moves = rows
    ctx.flags |= FLAG_POLICY
    ctx.methods |= METHOD_STATIC_POLICY
    ctx.interest = compute_interest(ctx)
    if ctx.interest >= float(ctx.cfg.HARD_INTEREST):
        ctx.flags |= FLAG_HARD


@register("adaptive_search")
def adaptive_search(ctx: TeachingContext) -> None:
    if ctx.interest < float(ctx.cfg.SEARCH_INTEREST) and not (ctx.flags & FLAG_HARD):
        return
    lines = ctx.backend.search(
        ctx.fen, bool(ctx.board.turn), nodes=int(ctx.cfg.SHALLOW_NODES),
        multipv=int(ctx.cfg.SEARCH_MULTIPV))
    if lines:
        ctx.search_cp = int(lines[0].cp_white)
        ctx.search_nodes = int(ctx.cfg.SHALLOW_NODES)
        by_uci = {move["uci"]: move for move in ctx.moves}
        for rank, line in enumerate(lines):
            row = by_uci.get(line.move)
            if row is None:
                row = {"uci": line.move, "static_cp": None, "rank_static": 65535}
                ctx.moves.append(row)
                by_uci[line.move] = row
            row["search_cp"] = int(line.cp_white)
            row["rank_search"] = rank
        ctx.flags |= FLAG_SEARCH_REFINED
        ctx.methods |= METHOD_SHALLOW_SEARCH

    ctx.interest = compute_interest(ctx)
    if (ctx.interest >= float(ctx.cfg.DEEP_INTEREST)
            and int(ctx.cfg.DEEP_NODES) > int(ctx.cfg.SHALLOW_NODES)):
        lines = ctx.backend.search(
            ctx.fen, bool(ctx.board.turn), nodes=int(ctx.cfg.DEEP_NODES),
            multipv=int(ctx.cfg.DEEP_MULTIPV))
        if lines:
            ctx.search_cp = int(lines[0].cp_white)
            ctx.search_nodes = int(ctx.cfg.DEEP_NODES)
            by_uci = {move["uci"]: move for move in ctx.moves}
            for rank, line in enumerate(lines):
                row = by_uci.get(line.move)
                if row is None:
                    row = {"uci": line.move, "static_cp": None, "rank_static": 65535}
                    ctx.moves.append(row)
                    by_uci[line.move] = row
                row["search_cp"] = int(line.cp_white)
                row["rank_search"] = rank
            ctx.flags |= FLAG_DEEP_REFINED
            ctx.methods |= METHOD_DEEP_SEARCH

    ctx.interest = compute_interest(ctx)
    if ctx.interest >= float(ctx.cfg.HARD_INTEREST):
        ctx.flags |= FLAG_HARD


def run_methods(ctx: TeachingContext, names: list[str] | tuple[str, ...]) -> None:
    for name in names:
        try:
            method = REGISTRY[name]
        except KeyError as exc:
            raise ValueError(
                f"unknown teaching method {name!r}; available: {', '.join(sorted(REGISTRY))}") from exc
        method(ctx)


def encode_moves(ctx: TeachingContext) -> np.ndarray:
    out = np.zeros(len(ctx.moves), dtype=MOVE_DTYPE)
    for i, row in enumerate(ctx.moves):
        out[i]["move"] = pack_move_uci(row["uci"])
        out[i]["static_cp"] = (
            MISSING_CP if row.get("static_cp") is None else int(row["static_cp"]))
        out[i]["search_cp"] = (
            MISSING_CP if row.get("search_cp") is None else int(row["search_cp"]))
        out[i]["rank_static"] = int(row.get("rank_static", 65535))
        out[i]["rank_search"] = int(row.get("rank_search", 65535))
    return out
