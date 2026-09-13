#!/usr/bin/env python3
"""Deterministic serial paired-opening UCI H2H with equal Hash/Threads settings."""
from __future__ import annotations

import argparse
import json
import math
import random
from pathlib import Path

import chess
import chess.engine
import chess.pgn


def _load_pgn(path: Path, count: int, plies: int, seed: int) -> list[chess.Board]:
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
    if len(candidates) < count:
        raise SystemExit(f"need {count} openings, found {len(candidates)} in {path}")
    rng = random.Random(seed)
    return [candidates[i] for i in rng.sample(range(len(candidates)), count)]


def _load_epd(path: Path, count: int, seed: int) -> list[chess.Board]:
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
    if len(candidates) < count:
        raise SystemExit(f"need {count} openings, found {len(candidates)} in {path}")
    rng = random.Random(seed)
    return [candidates[i] for i in rng.sample(range(len(candidates)), count)]


def load_openings(path: Path, count: int, plies: int, seed: int) -> list[chess.Board]:
    suffix = path.suffix.lower()
    if suffix == ".pgn":
        return _load_pgn(path, count, plies, seed)
    if suffix in {".epd", ".fen"}:
        return _load_epd(path, count, seed)
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
    ap.add_argument("--pairs", type=int, default=10)
    ap.add_argument("--movetime-ms", type=int, default=200)
    ap.add_argument("--hash-mb", type=int, default=64)
    ap.add_argument("--threads", type=int, default=1)
    ap.add_argument("--opening-file", required=True)
    ap.add_argument("--opening-plies", type=int, default=16)
    ap.add_argument("--opening-seed", type=int, default=3280926)
    ap.add_argument("--max-plies", type=int, default=300)
    ap.add_argument("--json", default="")
    args = ap.parse_args()

    opening_path = Path(args.opening_file)
    if not opening_path.is_file():
        raise SystemExit(f"opening file not found: {opening_path}")
    openings = load_openings(opening_path, args.pairs, args.opening_plies, args.opening_seed)
    limit = chess.engine.Limit(time=args.movetime_ms / 1000.0)
    a = chess.engine.SimpleEngine.popen_uci(args.engine_a, timeout=20.0)
    b = chess.engine.SimpleEngine.popen_uci(args.engine_b, timeout=20.0)
    configure(a, args.hash_mb, args.threads)
    configure(b, args.hash_mb, args.threads)

    wins = draws = losses = 0
    game_no = 0
    try:
        for pair_no, opening in enumerate(openings, 1):
            for swapped in (False, True):
                game_no += 1
                board = opening.copy(stack=False)
                white = b if swapped else a
                black = a if swapped else b
                white_is_a = not swapped
                start_ply = board.ply()
                while not board.is_game_over(claim_draw=True) and board.ply() - start_ply < args.max_plies:
                    mover = white if board.turn == chess.WHITE else black
                    result = mover.play(board, limit, game=game_no)
                    if result.move is None or result.move not in board.legal_moves:
                        raise RuntimeError(f"game {game_no}: invalid/null move from {'white' if board.turn else 'black'}")
                    board.push(result.move)

                outcome = board.outcome(claim_draw=True)
                if outcome is None or outcome.winner is None:
                    result_a = 0.5
                else:
                    a_won = (outcome.winner == chess.WHITE) == white_is_a
                    result_a = 1.0 if a_won else 0.0

                if result_a == 1.0:
                    wins += 1
                    tag = "A"
                elif result_a == 0.0:
                    losses += 1
                    tag = "B"
                else:
                    draws += 1
                    tag = "D"
                print(f"game {game_no:03d} pair={pair_no:03d} swap={int(swapped)} result={tag} plies={board.ply()-start_ply}", flush=True)
    finally:
        try:
            a.quit()
        finally:
            b.quit()

    total = wins + draws + losses
    score = (wins + 0.5 * draws) / total
    elo = elo_from_score(score)
    payload = {
        "label_a": args.label_a,
        "label_b": args.label_b,
        "games": total,
        "wins_a": wins,
        "draws": draws,
        "losses_a": losses,
        "score_a": score,
        "elo_a": elo,
        "movetime_ms": args.movetime_ms,
        "hash_mb": args.hash_mb,
        "threads": args.threads,
        "pairs": args.pairs,
        "opening_file": str(opening_path),
        "opening_seed": args.opening_seed,
    }
    print("RESULT " + json.dumps(payload, sort_keys=True), flush=True)
    if args.json:
        Path(args.json).write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
