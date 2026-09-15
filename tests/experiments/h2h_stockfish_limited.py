#!/usr/bin/env python3
"""Serial paired-opening UCI H2H against Stockfish UCI_LimitStrength."""
from __future__ import annotations

import argparse
import json
import math
import random
from pathlib import Path

import chess
import chess.engine


def load_epd(path: Path, count: int, seed: int) -> list[chess.Board]:
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


def configure_common(engine: chess.engine.SimpleEngine, hash_mb: int, threads: int) -> None:
    opts: dict[str, object] = {}
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


def configure_stockfish(engine: chess.engine.SimpleEngine, elo: int) -> None:
    if "UCI_LimitStrength" not in engine.options or "UCI_Elo" not in engine.options:
        raise SystemExit("Stockfish does not expose UCI_LimitStrength/UCI_Elo")
    elo_opt = engine.options["UCI_Elo"]
    if elo_opt.min is not None and elo < elo_opt.min:
        raise SystemExit(f"requested Elo {elo} below Stockfish minimum {elo_opt.min}")
    if elo_opt.max is not None and elo > elo_opt.max:
        raise SystemExit(f"requested Elo {elo} above Stockfish maximum {elo_opt.max}")
    engine.configure({"UCI_LimitStrength": True, "UCI_Elo": elo})


def elo_from_score(score: float) -> float:
    if score <= 0.0:
        return float("-inf")
    if score >= 1.0:
        return float("inf")
    return 400.0 * math.log10(score / (1.0 - score))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--zchezz", required=True)
    ap.add_argument("--stockfish", required=True)
    ap.add_argument("--stockfish-elo", type=int, required=True)
    ap.add_argument("--pairs", type=int, default=25)
    ap.add_argument("--movetime-ms", type=int, default=200)
    ap.add_argument("--hash-mb", type=int, default=64)
    ap.add_argument("--threads", type=int, default=1)
    ap.add_argument("--opening-file", required=True)
    ap.add_argument("--opening-seed", type=int, default=3290926)
    ap.add_argument("--max-plies", type=int, default=260)
    ap.add_argument("--json", default="")
    args = ap.parse_args()

    opening_path = Path(args.opening_file)
    openings = load_epd(opening_path, args.pairs, args.opening_seed)
    limit = chess.engine.Limit(time=args.movetime_ms / 1000.0)
    z = chess.engine.SimpleEngine.popen_uci(args.zchezz, timeout=20.0)
    sf = chess.engine.SimpleEngine.popen_uci(args.stockfish, timeout=20.0)

    wins = draws = losses = 0
    game_no = 0
    try:
        configure_common(z, args.hash_mb, args.threads)
        configure_common(sf, args.hash_mb, args.threads)
        configure_stockfish(sf, args.stockfish_elo)
        for pair_no, opening in enumerate(openings, 1):
            for swapped in (False, True):
                game_no += 1
                board = opening.copy(stack=False)
                white = sf if swapped else z
                black = z if swapped else sf
                white_is_z = not swapped
                start_ply = board.ply()
                while not board.is_game_over(claim_draw=True) and board.ply() - start_ply < args.max_plies:
                    mover = white if board.turn == chess.WHITE else black
                    result = mover.play(board, limit, game=game_no)
                    if result.move is None or result.move not in board.legal_moves:
                        raise RuntimeError(f"game {game_no}: invalid/null UCI move")
                    board.push(result.move)
                outcome = board.outcome(claim_draw=True)
                if outcome is None or outcome.winner is None:
                    score_z = 0.5
                else:
                    z_won = (outcome.winner == chess.WHITE) == white_is_z
                    score_z = 1.0 if z_won else 0.0
                if score_z == 1.0:
                    wins += 1; tag = "Z"
                elif score_z == 0.0:
                    losses += 1; tag = "S"
                else:
                    draws += 1; tag = "D"
                print(f"game {game_no:03d} pair={pair_no:03d} swap={int(swapped)} result={tag} plies={board.ply()-start_ply}", flush=True)
    finally:
        try:
            z.quit()
        finally:
            sf.quit()

    total = wins + draws + losses
    score = (wins + 0.5 * draws) / total
    payload = {"zchezz":"v329","stockfish_elo":args.stockfish_elo,"games":total,"wins_zchezz":wins,"draws":draws,"losses_zchezz":losses,"score_zchezz":score,"elo_zchezz_vs_limited_sf":elo_from_score(score),"movetime_ms":args.movetime_ms,"hash_mb":args.hash_mb,"threads":args.threads,"pairs":args.pairs,"opening_file":str(opening_path),"opening_seed":args.opening_seed}
    print("RESULT " + json.dumps(payload, sort_keys=True), flush=True)
    if args.json:
        Path(args.json).write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
