#!/usr/bin/env python3
"""Paired 3+2 H2H: identical engine with pondering enabled vs disabled.

The candidate and baseline use the same executable.  The only experimental
difference is python-chess driving the candidate with ponder=True, which
exercises the engine's UCI bestmove/ponder/go ponder/ponderhit path.
"""
from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

import chess
import chess.engine

ROOT = Path(__file__).resolve().parents[1]

OPENINGS = [
    ["e2e4", "e7e5", "g1f3", "b8c6", "f1b5", "a7a6"],
    ["d2d4", "d7d5", "c2c4", "e7e6", "b1c3", "g8f6"],
    ["c2c4", "e7e5", "b1c3", "g8f6", "g2g3", "d7d5"],
    ["g1f3", "d7d5", "g2g3", "g8f6", "f1g2", "g7g6"],
    ["e2e4", "c7c5", "g1f3", "d7d6", "d2d4", "c5d4"],
    ["e2e4", "e7e6", "d2d4", "d7d5", "b1c3", "g8f6"],
]


def engine_path(profile: str) -> Path:
    d = ROOT / "engine" / "c" / f"zchezz_{profile}"
    for name in ("zchezz.exe", "zchezz"):
        p = d / name
        if p.is_file():
            return p
    raise FileNotFoundError(f"engine executable not found under {d}")


def configure(eng: chess.engine.SimpleEngine) -> None:
    opts = {}
    for name, value in (("Threads", 1), ("Hash", 64), ("OwnBook", False)):
        if name in eng.options:
            opts[name] = value
    if opts:
        eng.configure(opts)


def apply_opening(board: chess.Board, moves: list[str]) -> None:
    for uci in moves:
        move = chess.Move.from_uci(uci)
        if move not in board.legal_moves:
            raise ValueError(f"illegal opening move {uci} in {board.fen()}")
        board.push(move)


def play_one(
    candidate: chess.engine.SimpleEngine,
    baseline: chess.engine.SimpleEngine,
    candidate_color: chess.Color,
    opening: list[str],
    base_seconds: float,
    increment: float,
    max_plies: int,
    game_id: str,
) -> dict:
    board = chess.Board()
    apply_opening(board, opening)
    clocks = {chess.WHITE: base_seconds, chess.BLACK: base_seconds}
    move_times = {"candidate": [], "baseline": []}
    ponder_hits_before = None

    for ply in range(max_plies):
        if board.is_game_over(claim_draw=True):
            break
        color = board.turn
        is_candidate = color == candidate_color
        eng = candidate if is_candidate else baseline
        label = "candidate" if is_candidate else "baseline"
        limit = chess.engine.Limit(
            white_clock=max(0.001, clocks[chess.WHITE]),
            black_clock=max(0.001, clocks[chess.BLACK]),
            white_inc=increment,
            black_inc=increment,
        )
        t0 = time.monotonic()
        try:
            result = eng.play(
                board,
                limit,
                game=game_id,
                ponder=is_candidate,
                info=chess.engine.INFO_BASIC,
            )
        except Exception as exc:
            winner = not color
            return {
                "result": "1-0" if winner == chess.WHITE else "0-1",
                "termination": f"engine_error:{label}:{type(exc).__name__}",
                "plies": ply,
                "candidate_color": "white" if candidate_color else "black",
                "move_times": move_times,
            }
        elapsed = time.monotonic() - t0
        move_times[label].append(elapsed)
        clocks[color] -= elapsed
        if clocks[color] < -0.25:
            winner = not color
            return {
                "result": "1-0" if winner == chess.WHITE else "0-1",
                "termination": f"timeout:{label}",
                "plies": ply,
                "candidate_color": "white" if candidate_color else "black",
                "move_times": move_times,
            }
        if result.move is None or result.move not in board.legal_moves:
            winner = not color
            return {
                "result": "1-0" if winner == chess.WHITE else "0-1",
                "termination": f"illegal_or_null:{label}",
                "plies": ply,
                "candidate_color": "white" if candidate_color else "black",
                "move_times": move_times,
            }
        board.push(result.move)
        clocks[color] += increment

    if board.is_game_over(claim_draw=True):
        outcome = board.outcome(claim_draw=True)
        result_str = outcome.result() if outcome else "1/2-1/2"
        termination = str(outcome.termination.name) if outcome else "unknown"
    else:
        result_str = "1/2-1/2"
        termination = "max_plies"

    return {
        "result": result_str,
        "termination": termination,
        "plies": board.ply(),
        "candidate_color": "white" if candidate_color else "black",
        "move_times": move_times,
        "final_fen": board.fen(),
    }


def candidate_score(game: dict) -> float:
    r = game["result"]
    white_candidate = game["candidate_color"] == "white"
    if r == "1/2-1/2":
        return 0.5
    white_won = r == "1-0"
    return 1.0 if white_won == white_candidate else 0.0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--profile", required=True, choices=("v331", "v507"))
    ap.add_argument("--opening-index", type=int, required=True)
    ap.add_argument("--base-seconds", type=float, default=180.0)
    ap.add_argument("--increment", type=float, default=2.0)
    ap.add_argument("--max-plies", type=int, default=160)
    ap.add_argument("--output", default="")
    args = ap.parse_args()

    opening = OPENINGS[args.opening_index % len(OPENINGS)]
    exe = engine_path(args.profile)
    candidate = chess.engine.SimpleEngine.popen_uci(str(exe))
    baseline = chess.engine.SimpleEngine.popen_uci(str(exe))
    configure(candidate)
    configure(baseline)

    try:
        games = [
            play_one(candidate, baseline, chess.WHITE, opening, args.base_seconds, args.increment, args.max_plies, f"{args.profile}-{args.opening_index}-a"),
            play_one(candidate, baseline, chess.BLACK, opening, args.base_seconds, args.increment, args.max_plies, f"{args.profile}-{args.opening_index}-b"),
        ]
    finally:
        candidate.quit()
        baseline.quit()

    score = sum(candidate_score(g) for g in games)
    wins = sum(candidate_score(g) == 1.0 for g in games)
    draws = sum(candidate_score(g) == 0.5 for g in games)
    losses = 2 - wins - draws
    result = {
        "profile": args.profile,
        "opening_index": args.opening_index,
        "time_control": f"{int(args.base_seconds)}+{args.increment:g}",
        "candidate": "ponder_on",
        "baseline": "ponder_off",
        "wins": wins,
        "draws": draws,
        "losses": losses,
        "score": score,
        "games": games,
    }
    out = Path(args.output or f"ponder_result_{args.profile}_{args.opening_index}.json")
    out.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print("PONDER_RESULT " + json.dumps(result, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
