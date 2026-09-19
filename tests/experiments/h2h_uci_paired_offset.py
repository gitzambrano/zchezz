#!/usr/bin/env python3
"""Deterministic serial paired-opening UCI H2H with disjoint opening offsets."""
from __future__ import annotations

import argparse
import json
import math
import random
from pathlib import Path

import chess
import chess.engine
import chess.pgn


def _select(candidates: list[chess.Board], count: int, seed: int, offset: int) -> list[chess.Board]:
    if len(candidates) < offset + count:
        raise SystemExit(f"need at least {offset + count} openings, found {len(candidates)}")
    order = list(range(len(candidates)))
    random.Random(seed).shuffle(order)
    return [candidates[i] for i in order[offset:offset + count]]


def _load_pgn(path: Path, count: int, plies: int, seed: int, offset: int) -> list[chess.Board]:
    candidates: list[chess.Board] = []
    with path.open("r", encoding="utf-8", errors="replace") as f:
        while True:
            game = chess.pgn.read_game(f)
            if game is None:
                break
            board = game.board()
            for i, move in enumerate(game.mainline_moves()):
                if i >= plies:
                    break
                board.push(move)
            candidates.append(board.copy(stack=False))
    return _select(candidates, count, seed, offset)


def _load_epd(path: Path, count: int, seed: int, offset: int) -> list[chess.Board]:
    candidates: list[chess.Board] = []
    with path.open("r", encoding="utf-8", errors="replace") as f:
        for raw in f:
            line = raw.strip()
            if not line or line.startswith("#"):
                continue
            board = chess.Board()
            try:
                board.set_epd(line)
            except ValueError:
                fields = line.split()
                if len(fields) < 4:
                    continue
                board = chess.Board(" ".join(fields[:4] + ["0", "1"]))
            candidates.append(board.copy(stack=False))
    return _select(candidates, count, seed, offset)


def load_openings(path: Path, count: int, plies: int, seed: int, offset: int) -> list[chess.Board]:
    if path.suffix.lower() == ".pgn":
        return _load_pgn(path, count, plies, seed, offset)
    if path.suffix.lower() in {".epd", ".fen"}:
        return _load_epd(path, count, seed, offset)
    raise SystemExit(f"unsupported opening format: {path}")


def configure(engine: chess.engine.SimpleEngine, hash_mb: int, threads: int) -> None:
    opts = {}
    if "Hash" in engine.options:
        opts["Hash"] = hash_mb
    if "Threads" in engine.options:
        opts["Threads"] = threads
    if "SyzygyPath" in engine.options:
        opts["SyzygyPath"] = ""
    if "OwnBook" in engine.options:
        opts["OwnBook"] = False
    if opts:
        engine.configure(opts)


def elo_from_score(score: float) -> float:
    if score <= 0.0:
        return float("-inf")
    if score >= 1.0:
        return float("inf")
    return 400.0 * math.log10(score / (1.0 - score))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--engine-a", required=True)
    ap.add_argument("--engine-b", required=True)
    ap.add_argument("--label-a", default="A")
    ap.add_argument("--label-b", default="B")
    ap.add_argument("--pairs", type=int, default=25)
    ap.add_argument("--movetime-ms", type=int, default=80)
    ap.add_argument("--nodes", type=int, default=0)
    ap.add_argument("--hash-mb", type=int, default=64)
    ap.add_argument("--threads", type=int, default=1)
    ap.add_argument("--opening-file", required=True)
    ap.add_argument("--opening-plies", type=int, default=16)
    ap.add_argument("--opening-seed", type=int, default=3303201)
    ap.add_argument("--opening-offset", type=int, default=0)
    ap.add_argument("--max-plies", type=int, default=260)
    ap.add_argument("--json", required=True)
    args = ap.parse_args()

    openings = load_openings(Path(args.opening_file), args.pairs, args.opening_plies,
                             args.opening_seed, args.opening_offset)
    limit = chess.engine.Limit(nodes=args.nodes) if args.nodes > 0 else chess.engine.Limit(time=args.movetime_ms / 1000.0)
    a = chess.engine.SimpleEngine.popen_uci(args.engine_a, timeout=20.0)
    b = chess.engine.SimpleEngine.popen_uci(args.engine_b, timeout=20.0)
    configure(a, args.hash_mb, args.threads)
    configure(b, args.hash_mb, args.threads)

    wins = draws = losses = 0
    pair_points: list[float] = []
    metrics = {
        "a": {"nodes": 0, "time_s": 0.0, "depth": 0, "moves": 0},
        "b": {"nodes": 0, "time_s": 0.0, "depth": 0, "moves": 0},
    }
    game_no = 0
    try:
        for pair_no, opening in enumerate(openings, 1):
            pp = 0.0
            for swapped in (False, True):
                game_no += 1
                board = opening.copy(stack=False)
                white = b if swapped else a
                black = a if swapped else b
                white_is_a = not swapped
                start_ply = board.ply()
                while not board.is_game_over(claim_draw=True) and board.ply() - start_ply < args.max_plies:
                    mover = white if board.turn == chess.WHITE else black
                    is_a = mover is a
                    result = mover.play(board, limit, game=game_no, info=chess.engine.INFO_BASIC)
                    if result.move is None or result.move not in board.legal_moves:
                        raise RuntimeError(f"game {game_no}: invalid/null move")
                    m = metrics["a" if is_a else "b"]
                    info = result.info or {}
                    m["nodes"] += int(info.get("nodes", 0) or 0)
                    m["time_s"] += float(info.get("time", 0.0) or 0.0)
                    m["depth"] += int(info.get("depth", 0) or 0)
                    m["moves"] += 1
                    board.push(result.move)
                outcome = board.outcome(claim_draw=True)
                if outcome is None or outcome.winner is None:
                    result_a = 0.5
                else:
                    result_a = 1.0 if ((outcome.winner == chess.WHITE) == white_is_a) else 0.0
                pp += result_a
                if result_a == 1.0:
                    wins += 1; tag = "A"
                elif result_a == 0.0:
                    losses += 1; tag = "B"
                else:
                    draws += 1; tag = "D"
                print(f"game {game_no:03d} pair={pair_no:03d} swap={int(swapped)} result={tag} plies={board.ply()-start_ply}", flush=True)
            pair_points.append(pp)
    finally:
        try:
            a.quit()
        finally:
            b.quit()

    total = wins + draws + losses
    score = (wins + 0.5 * draws) / total
    for key in ("a", "b"):
        m = metrics[key]
        m["nps"] = (m["nodes"] / m["time_s"]) if m["time_s"] > 0 else 0.0
        m["avg_depth"] = (m["depth"] / m["moves"]) if m["moves"] else 0.0
    payload = {
        "label_a": args.label_a, "label_b": args.label_b, "games": total,
        "wins_a": wins, "draws": draws, "losses_a": losses,
        "score_a": score, "elo_a": elo_from_score(score),
        "pairs": args.pairs, "pair_points_a": pair_points,
        "movetime_ms": args.movetime_ms if args.nodes <= 0 else None,
        "nodes_limit": args.nodes if args.nodes > 0 else None,
        "hash_mb": args.hash_mb, "threads": args.threads,
        "opening_file": args.opening_file, "opening_seed": args.opening_seed,
        "opening_offset": args.opening_offset,
        "metrics": metrics,
    }
    print("RESULT " + json.dumps(payload, sort_keys=True), flush=True)
    Path(args.json).write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
