#!/usr/bin/env python3
"""Fast, extensible Stockfish distillation and active-teaching pipeline.

Bare execution uses the CONFIGURATION block below. CLI options are optional
overrides. The default cascade evaluates every position statically, mines
teacher/source gaps, labels sparse child policy on a deterministic subset plus
all hard cases, and spends search only where cheap signals justify it.
"""
from __future__ import annotations

import argparse
import importlib
import json
import os
import sys
import time
from concurrent.futures import ProcessPoolExecutor
from dataclasses import asdict, dataclass
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
UTILS = ROOT / "utils"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(UTILS) not in sys.path:
    sys.path.insert(0, str(UTILS))
from engine_profiles import stockfish_executable  # noqa: E402

# =============================== CONFIGURATION ===============================
INPUTS = [str(ROOT / "data" / "teacher_input.epd")]
OUTPUT = str(ROOT / "data" / "teaching" / "stockfish_cascade_v1")
SOURCE_MODE = "database"          # database | random | mixed
LIMIT = 0                         # 0 = unlimited
RESUME = True
SEED = 20260911
WORKERS = max(1, min(8, (os.cpu_count() or 2) // 2))
BATCH_SIZE = 128
CHECKPOINT_EVERY = 5000

METHODS = ("static_value", "gap_mining", "static_policy", "gap_mining", "adaptive_search")
PLUGIN_MODULES = ()               # modules importing methods.register("...")
QUIET_MODE = "stratified"         # all | quiet-only | stratified
POLICY_SAMPLE_RATE = 0.10         # hard positions are always policy-labeled
POLICY_TEMPERATURE_CP = 120.0     # metadata/default; raw move scores are stored
SEARCH_MULTIPV = 8
SHALLOW_NODES = 2_000
DEEP_MULTIPV = 8
DEEP_NODES = 50_000
SEARCH_INTEREST = 0.70
DEEP_INTEREST = 1.35
HARD_INTEREST = 0.90
GAP_HARD_CP = 120
GAP_FULL_SCALE_CP = 400
LOW_MARGIN_CP = 35
MARGIN_FULL_SCALE_CP = 180
HIGH_ENTROPY = 0.75
W_GAP = 1.0
W_MARGIN = 0.35
W_ENTROPY = 0.35
MATE_CP = 30000

SF_HASH_MB = 32
SF_THREADS = 1
STATIC_FALLBACK_NODES = 1
STUDENT_PATH = ""                 # optional UCI student; else source_cp is reused
STUDENT_NODES = 256

RANDOM_COUNT = 100_000
RANDOM_MIN_PLIES = 8
RANDOM_MAX_PLIES = 80
PGN_SKIP_PLIES = 8
PGN_MAX_PLIES = 0
# ============================================================================


@dataclass
class Config:
    INPUTS: list[str]
    OUTPUT: str
    SOURCE_MODE: str
    LIMIT: int
    RESUME: bool
    SEED: int
    WORKERS: int
    BATCH_SIZE: int
    CHECKPOINT_EVERY: int
    METHODS: tuple[str, ...]
    PLUGIN_MODULES: tuple[str, ...]
    QUIET_MODE: str
    POLICY_SAMPLE_RATE: float
    POLICY_TEMPERATURE_CP: float
    SEARCH_MULTIPV: int
    SHALLOW_NODES: int
    DEEP_MULTIPV: int
    DEEP_NODES: int
    SEARCH_INTEREST: float
    DEEP_INTEREST: float
    HARD_INTEREST: float
    GAP_HARD_CP: int
    GAP_FULL_SCALE_CP: int
    LOW_MARGIN_CP: int
    MARGIN_FULL_SCALE_CP: int
    HIGH_ENTROPY: float
    W_GAP: float
    W_MARGIN: float
    W_ENTROPY: float
    MATE_CP: int
    SF_HASH_MB: int
    SF_THREADS: int
    STATIC_FALLBACK_NODES: int
    STUDENT_PATH: str
    STUDENT_NODES: int
    RANDOM_COUNT: int
    RANDOM_MIN_PLIES: int
    RANDOM_MAX_PLIES: int
    PGN_SKIP_PLIES: int
    PGN_MAX_PLIES: int


def default_config() -> Config:
    return Config(
        INPUTS.copy(), OUTPUT, SOURCE_MODE, LIMIT, RESUME, SEED, WORKERS,
        BATCH_SIZE, CHECKPOINT_EVERY, METHODS, PLUGIN_MODULES, QUIET_MODE,
        POLICY_SAMPLE_RATE, POLICY_TEMPERATURE_CP, SEARCH_MULTIPV,
        SHALLOW_NODES, DEEP_MULTIPV, DEEP_NODES, SEARCH_INTEREST,
        DEEP_INTEREST, HARD_INTEREST, GAP_HARD_CP, GAP_FULL_SCALE_CP,
        LOW_MARGIN_CP, MARGIN_FULL_SCALE_CP, HIGH_ENTROPY, W_GAP,
        W_MARGIN, W_ENTROPY, MATE_CP, SF_HASH_MB, SF_THREADS,
        STATIC_FALLBACK_NODES, STUDENT_PATH, STUDENT_NODES, RANDOM_COUNT,
        RANDOM_MIN_PLIES, RANDOM_MAX_PLIES, PGN_SKIP_PLIES, PGN_MAX_PLIES)


def parse_args(cfg: Config) -> tuple[Config, bool]:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", action="append", dest="inputs",
                        help="file/dir/glob; repeatable")
    parser.add_argument("--output", default=cfg.OUTPUT)
    parser.add_argument("--source-mode", choices=("database", "random", "mixed"),
                        default=cfg.SOURCE_MODE)
    parser.add_argument("--limit", type=int, default=cfg.LIMIT)
    parser.add_argument("--workers", type=int, default=cfg.WORKERS)
    parser.add_argument("--batch-size", type=int, default=cfg.BATCH_SIZE)
    parser.add_argument("--methods", default=",".join(cfg.METHODS))
    parser.add_argument("--plugin", action="append", dest="plugins",
                        help="import module registering extra teaching methods")
    parser.add_argument("--quiet-mode", choices=("all", "quiet-only", "stratified"),
                        default=cfg.QUIET_MODE)
    parser.add_argument("--policy-sample-rate", type=float,
                        default=cfg.POLICY_SAMPLE_RATE)
    parser.add_argument("--shallow-nodes", type=int, default=cfg.SHALLOW_NODES)
    parser.add_argument("--deep-nodes", type=int, default=cfg.DEEP_NODES)
    parser.add_argument("--gap-hard-cp", type=int, default=cfg.GAP_HARD_CP)
    parser.add_argument("--search-interest", type=float, default=cfg.SEARCH_INTEREST)
    parser.add_argument("--deep-interest", type=float, default=cfg.DEEP_INTEREST)
    parser.add_argument("--random-count", type=int, default=cfg.RANDOM_COUNT)
    parser.add_argument("--student", default=cfg.STUDENT_PATH)
    parser.add_argument("--no-resume", action="store_true")
    parser.add_argument("--show-config", action="store_true")
    args = parser.parse_args()

    cfg.INPUTS = args.inputs or cfg.INPUTS
    cfg.OUTPUT = args.output
    cfg.SOURCE_MODE = args.source_mode
    cfg.LIMIT = max(0, args.limit)
    cfg.WORKERS = max(1, args.workers)
    cfg.BATCH_SIZE = max(1, args.batch_size)
    cfg.METHODS = tuple(x.strip() for x in args.methods.split(",") if x.strip())
    cfg.PLUGIN_MODULES = tuple(args.plugins or cfg.PLUGIN_MODULES)
    cfg.QUIET_MODE = args.quiet_mode
    cfg.POLICY_SAMPLE_RATE = min(1.0, max(0.0, args.policy_sample_rate))
    cfg.SHALLOW_NODES = max(1, args.shallow_nodes)
    cfg.DEEP_NODES = max(cfg.SHALLOW_NODES, args.deep_nodes)
    cfg.GAP_HARD_CP = max(0, args.gap_hard_cp)
    cfg.SEARCH_INTEREST = args.search_interest
    cfg.DEEP_INTEREST = args.deep_interest
    cfg.RANDOM_COUNT = max(0, args.random_count)
    cfg.STUDENT_PATH = args.student
    cfg.RESUME = not args.no_resume
    return cfg, bool(args.show_config)


_WORKER = None


def _worker_init(cfg_dict: dict, sf_path: str):
    global _WORKER
    from train.teaching.backends import UciBackend

    for module in cfg_dict.get("PLUGIN_MODULES", ()):
        importlib.import_module(module)
    _WORKER = {
        "cfg": Config(**cfg_dict),
        "sf": UciBackend(
            sf_path, cfg_dict["SF_HASH_MB"], cfg_dict["SF_THREADS"],
            cfg_dict["STATIC_FALLBACK_NODES"]),
        "student": None,
    }
    if cfg_dict.get("STUDENT_PATH"):
        _WORKER["student"] = UciBackend(cfg_dict["STUDENT_PATH"], 8, 1, 1)


def _classify(board) -> tuple[int, bool]:
    from train.teaching.format import (
        FLAG_IN_CHECK, FLAG_QUIET, FLAG_TACTICAL, FLAG_TERMINAL)

    flags = 0
    terminal = board.is_game_over(claim_draw=False)
    if terminal:
        flags |= FLAG_TERMINAL
    if board.is_check():
        flags |= FLAG_IN_CHECK
    tactical = bool(board.is_check()) or any(
        board.is_capture(move) or move.promotion for move in board.legal_moves)
    if tactical:
        flags |= FLAG_TACTICAL
    else:
        flags |= FLAG_QUIET
    return flags, not tactical and not terminal


def _label_one(src: dict):
    import chess
    from train.teaching.format import (
        FLAG_GENERATED, FLAG_SOURCE_CP, METHOD_EXTERNAL_STUDENT,
        POSITION_DTYPE, fill_position_board, missing_cp)
    from train.teaching.methods import TeachingContext, encode_moves, run_methods

    cfg = _WORKER["cfg"]
    board = chess.Board(src["fen"])
    flags, quiet = _classify(board)
    if cfg.QUIET_MODE == "quiet-only" and not quiet:
        return None
    if src.get("generated"):
        flags |= FLAG_GENERATED
    if src.get("source_cp") is not None:
        flags |= FLAG_SOURCE_CP

    ctx = TeachingContext(
        board=board, backend=_WORKER["sf"], cfg=cfg,
        source_cp=src.get("source_cp"), flags=flags)
    if _WORKER["student"] is not None:
        lines = _WORKER["student"].search(
            board.fen(), bool(board.turn), nodes=cfg.STUDENT_NODES, multipv=1)
        if lines:
            ctx.student_cp = int(lines[0].cp_white)
            ctx.methods |= METHOD_EXTERNAL_STUDENT
    else:
        ctx.student_cp = src.get("source_cp")

    run_methods(ctx, cfg.METHODS)
    rec = np.zeros(1, dtype=POSITION_DTYPE)
    fill_position_board(rec[0], board)
    rec[0]["result_wdl"] = int(src.get("result_wdl", 2))
    rec[0]["source_cp"] = missing_cp(src.get("source_cp"))
    rec[0]["static_cp"] = missing_cp(ctx.static_cp)
    rec[0]["search_cp"] = missing_cp(ctx.search_cp)
    rec[0]["student_cp"] = missing_cp(ctx.student_cp)
    rec[0]["interest"] = float(ctx.interest)
    rec[0]["flags"] = int(ctx.flags)
    rec[0]["methods"] = int(ctx.methods)
    rec[0]["search_nodes"] = int(ctx.search_nodes)
    rec[0]["source_tag"] = int(src.get("source_tag", 0))
    moves = encode_moves(ctx)
    return rec.tobytes(), moves.tobytes(), len(moves)


def _label_batch(batch: list[dict]):
    return len(batch), [_label_one(src) for src in batch]


def _source_iter(cfg: Config):
    from train.teaching.inputs import iter_inputs, iter_random_positions

    if cfg.SOURCE_MODE in ("database", "mixed"):
        yield from iter_inputs(
            cfg.INPUTS, pgn_skip_plies=cfg.PGN_SKIP_PLIES,
            pgn_max_plies=cfg.PGN_MAX_PLIES)
    if cfg.SOURCE_MODE in ("random", "mixed"):
        yield from iter_random_positions(
            cfg.RANDOM_COUNT, cfg.RANDOM_MIN_PLIES,
            cfg.RANDOM_MAX_PLIES, cfg.SEED)


def main() -> int:
    cfg, show = parse_args(default_config())
    sf = stockfish_executable()
    if show:
        data = asdict(cfg)
        data["stockfish"] = str(sf) if sf else "not found"
        print(json.dumps(data, indent=2, default=str))
        return 0

    try:
        import chess  # noqa: F401
    except ImportError:
        print(
            "python-chess is required. Install repository dev dependencies: "
            "pip install -e '.[dev]'", file=sys.stderr)
        return 2
    if sf is None:
        print(
            "Stockfish not found. Set ZCHEZZ_STOCKFISH, install under "
            "engine/stockfish/, or put stockfish on PATH.", file=sys.stderr)
        return 2

    if cfg.SOURCE_MODE in ("database", "mixed"):
        from train.teaching.inputs import expand_inputs
        files = expand_inputs(cfg.INPUTS)
        if not files and cfg.SOURCE_MODE == "database":
            print(f"No supported input files found in: {cfg.INPUTS}", file=sys.stderr)
            return 2

    from train.teaching.format import MOVE_DTYPE, POSITION_DTYPE, TeachingWriter

    out = Path(cfg.OUTPUT)
    progress_path = out / "progress.json"
    consumed = 0
    if cfg.RESUME and progress_path.exists():
        try:
            progress = json.loads(progress_path.read_text(encoding="utf-8"))
            consumed = int(progress.get("consumed", 0))
        except Exception:
            consumed = 0

    meta = {
        "teacher": "Stockfish",
        "teacher_path": str(sf),
        "config": asdict(cfg),
        "inputs": cfg.INPUTS,
        "methods": list(cfg.METHODS),
        "notes": (
            "raw white-relative cp and sparse move scores; soft policy is "
            "derived at training time"),
    }
    writer = TeachingWriter(
        out, meta, append=cfg.RESUME and (out / "metadata.json").exists())
    kept = int(writer.positions)
    resume_consumed = consumed
    started = time.time()
    next_checkpoint = kept + cfg.CHECKPOINT_EVERY

    def batches():
        batch = []
        emitted = 0
        for index, src in enumerate(_source_iter(cfg)):
            if index < resume_consumed:
                continue
            if cfg.LIMIT and resume_consumed + emitted >= cfg.LIMIT:
                break
            batch.append(src.__dict__)
            emitted += 1
            if len(batch) >= cfg.BATCH_SIZE:
                yield batch
                batch = []
        if batch:
            yield batch

    ok = False
    try:
        with ProcessPoolExecutor(
                max_workers=cfg.WORKERS, initializer=_worker_init,
                initargs=(asdict(cfg), str(sf))) as pool:
            for batch_n, results in pool.map(_label_batch, batches(), chunksize=1):
                for item in results:
                    if item is None:
                        continue
                    pos_bytes, move_bytes, _ = item
                    pos = np.frombuffer(pos_bytes, dtype=POSITION_DTYPE).copy()
                    moves = (
                        np.frombuffer(move_bytes, dtype=MOVE_DTYPE).copy()
                        if move_bytes else np.empty(0, dtype=MOVE_DTYPE))
                    writer.write(pos, moves)
                    kept += 1
                consumed += batch_n
                if kept >= next_checkpoint:
                    elapsed = max(1e-9, time.time() - started)
                    writer.checkpoint({
                        "consumed": consumed,
                        "kept": kept,
                        "positions_per_s": kept / elapsed,
                    })
                    progress_path.write_text(json.dumps({
                        "consumed": consumed,
                        "kept": kept,
                        "complete": False,
                    }, indent=2), encoding="utf-8")
                    print(
                        f"teaching: consumed={consumed:,} kept={kept:,} "
                        f"rate={kept / elapsed:.1f} pos/s", flush=True)
                    next_checkpoint = kept + cfg.CHECKPOINT_EVERY
        ok = True
    finally:
        elapsed = max(1e-9, time.time() - started)
        writer.close({
            "consumed": consumed,
            "kept": kept,
            "elapsed_s": elapsed,
            "positions_per_s": kept / elapsed,
            "complete": ok,
        })
        progress_path.write_text(json.dumps({
            "consumed": consumed,
            "kept": kept,
            "complete": ok,
        }, indent=2), encoding="utf-8")

    print(f"wrote {kept:,} positions to {out} in {elapsed:.1f}s")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
