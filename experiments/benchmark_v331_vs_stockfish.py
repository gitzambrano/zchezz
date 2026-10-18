#!/usr/bin/env python3
"""Benchmark v331_main and v331_exp against Stockfish at Elo 2800, 2900, and 3000.

Contract:
  - 100 opening pairs (200 games with colors reversed) per Elo level per engine.
  - 600 games for v331_main + 600 games for v331_exp = 1200 games total.
  - Concurrency = 2 (low CPU usage, zero interference with GPU training).
  - Movetime = 100ms per move.
"""
from __future__ import annotations
import argparse
import datetime
import math
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
import chess
import chess.engine
import chess.pgn

ROOT = Path(__file__).resolve().parents[1]

def load_openings(path: Path, max_pairs: int) -> list[list[chess.Move]]:
    openings = []
    with open(path, "r", encoding="utf-8", errors="replace") as f:
        while len(openings) < max_pairs:
            g = chess.pgn.read_game(f)
            if g is None:
                break
            moves = list(g.mainline_moves())
            if len(moves) >= 8:
                openings.append(moves[:8])
    return openings

def play_one_game(white_path: str, white_opts: dict,
                  black_path: str, black_opts: dict,
                  opening_moves: list[chess.Move],
                  movetime_s: float, max_plies: int = 150) -> tuple[str, str, int, list[str]]:
    # Launch engines
    eng_w = chess.engine.SimpleEngine.popen_uci(white_path)
    eng_b = chess.engine.SimpleEngine.popen_uci(black_path)
    if white_opts:
        eng_w.configure(white_opts)
    if black_opts:
        eng_b.configure(black_opts)

    board = chess.Board()
    for m in opening_moves:
        board.push(m)

    limit = chess.engine.Limit(time=movetime_s)
    ply_count = len(opening_moves)
    sans = []

    try:
        while not board.is_game_over(claim_draw=True) and ply_count < max_plies:
            current_eng = eng_w if board.turn == chess.WHITE else eng_b
            res = current_eng.play(board, limit)
            if res.move is None or res.move not in board.legal_moves:
                break
            sans.append(board.san(res.move))
            board.push(res.move)
            ply_count += 1
    finally:
        eng_w.quit()
        eng_b.quit()

    if board.is_checkmate():
        result = "0-1" if board.turn == chess.WHITE else "1-0"
        term = "Checkmate"
    elif board.is_stalemate():
        result = "1/2-1/2"
        term = "Stalemate"
    elif board.is_insufficient_material():
        result = "1/2-1/2"
        term = "Insufficient Material"
    elif board.can_claim_threefold_repetition():
        result = "1/2-1/2"
        term = "3-fold Repetition"
    elif board.can_claim_fifty_moves():
        result = "1/2-1/2"
        term = "50-move Rule"
    elif ply_count >= max_plies:
        result = "1/2-1/2"
        term = "Ply Limit"
    else:
        result = "1/2-1/2"
        term = "Draw"

    return result, term, ply_count, sans

def run_match_level(engine_name: str, engine_path: str, sf_path: str, sf_elo: int,
                    openings: list[list[chess.Move]], movetime_s: float, concurrency: int,
                    out_dir: Path):
    print(f"\n{'='*75}")
    print(f" MATCH: {engine_name} vs Stockfish {sf_elo} ({len(openings)*2} games @ {int(movetime_s*1000)}ms)")
    print(f"{'='*75}\n")

    sf_opts = {"Threads": 1, "UCI_LimitStrength": True, "UCI_Elo": sf_elo}
    eng_opts = {"Threads": 1}

    tasks = []
    # Generate paired games: Game A (Engine White), Game B (Engine Black)
    for pair_idx, op in enumerate(openings):
        tasks.append((pair_idx, True, engine_path, eng_opts, sf_path, sf_opts, op))
        tasks.append((pair_idx, False, sf_path, sf_opts, engine_path, eng_opts, op))

    wins, draws, losses = 0, 0, 0
    t0 = time.time()
    completed = 0
    total = len(tasks)

    pgn_path = out_dir / f"{engine_name}_vs_SF{sf_elo}.pgn"
    pgn_file = open(pgn_path, "w", encoding="utf-8")

    with ThreadPoolExecutor(max_workers=concurrency) as executor:
        future_map = {
            executor.submit(play_one_game, w_p, w_o, b_p, b_o, op, movetime_s): (idx, eng_is_white)
            for idx, eng_is_white, w_p, w_o, b_p, b_o, op in tasks
        }

        for fut in as_completed(future_map):
            idx, eng_is_white = future_map[fut]
            try:
                res, term, plies, sans = fut.result()
            except Exception as e:
                res, term, plies, sans = "1/2-1/2", f"Error ({e})", 0, []

            # Scoring from engine perspective:
            if res == "1-0":
                if eng_is_white: wins += 1
                else: losses += 1
            elif res == "0-1":
                if eng_is_white: losses += 1
                else: wins += 1
            else:
                draws += 1

            completed += 1
            score = wins + 0.5 * draws
            score_pct = (score / completed) * 100 if completed > 0 else 0

            # Write PGN record
            w_name = engine_name if eng_is_white else f"Stockfish_{sf_elo}"
            b_name = f"Stockfish_{sf_elo}" if eng_is_white else engine_name
            pgn_file.write(f'[Event "{engine_name} vs SF {sf_elo}"]\n')
            pgn_file.write(f'[White "{w_name}"]\n')
            pgn_file.write(f'[Black "{b_name}"]\n')
            pgn_file.write(f'[Result "{res}"]\n')
            pgn_file.write(f'[Termination "{term}"]\n\n')
            pgn_file.write(" ".join(sans) + f" {res}\n\n")
            pgn_file.flush()

            if completed % 20 == 0 or completed == total:
                elapsed = time.time() - t0
                speed = completed / max(1.0, elapsed)
                print(f"  [{completed:3d}/{total:3d}] {engine_name}: {score:4.1f}/{completed} ({score_pct:4.1f}%) | "
                      f"W:{wins} D:{draws} L:{losses} | {speed:.2f} g/s | elapsed {elapsed/60:.1f}m")

    pgn_file.close()
    elapsed = time.time() - t0
    score = wins + 0.5 * draws
    pct = score / total if total > 0 else 0

    # Elo difference estimate: diff = -400 * log10(1/pct - 1)
    if 0 < pct < 1:
        elo_diff = -400.0 * math.log10((1.0 / pct) - 1.0)
        perf_elo = sf_elo + elo_diff
    elif pct >= 1:
        elo_diff = 400.0
        perf_elo = sf_elo + 400.0
    else:
        elo_diff = -400.0
        perf_elo = sf_elo - 400.0

    print(f"\n--- Result: {engine_name} vs SF {sf_elo} ---")
    print(f"Score: {score:.1f}/{total} ({pct*100:.1f}%) [W:{wins} D:{draws} L:{losses}]")
    print(f"Estimated Performance Elo: {perf_elo:.0f} (diff {elo_diff:+.0f} Elo)\n")
    return {
        "engine": engine_name,
        "sf_elo": sf_elo,
        "score": score,
        "total": total,
        "pct": pct,
        "wins": wins,
        "draws": draws,
        "losses": losses,
        "perf_elo": perf_elo,
    }

def main():
    parser = argparse.ArgumentParser(description="Benchmark v331_main vs v331_exp vs Stockfish")
    parser.add_argument("--pairs-per-level", type=int, default=100, help="Opening pairs per level (x2 games, default: 100)")
    parser.add_argument("--movetime", type=int, default=100, help="Movetime per move in ms (default: 100)")
    parser.add_argument("--concurrency", type=int, default=2, help="Concurrent games (default: 2)")
    args = parser.parse_args()

    v331_main_exe = str(ROOT / "engine" / "c" / "zchezz_v331" / "zchezz.exe")
    v331_exp_exe  = str(ROOT / "artifacts" / "engines" / "v331_exp" / "zchezz.exe")
    sf_exe        = str(ROOT / "engine" / "stockfish" / "stockfish.exe")

    out_dir = ROOT / "artifacts" / "benchmark_v331_vs_sf"
    out_dir.mkdir(parents=True, exist_ok=True)

    openings_path = ROOT / "openings" / "lines" / "8moves_v3.pgn"
    print(f"Loading {args.pairs_per_level} openings from {openings_path}...")
    openings = load_openings(openings_path, args.pairs_per_level)
    print(f"Loaded {len(openings)} opening lines.")

    levels = [2800, 2900, 3000]
    results = []

    # Alternate levels so we get comparison points early:
    for elo in levels:
        # Run v331_main vs SF
        r_main = run_match_level("v331_main", v331_main_exe, sf_exe, elo, openings, args.movetime / 1000.0, args.concurrency, out_dir)
        results.append(r_main)

        # Run v331_exp vs SF
        r_exp = run_match_level("v331_exp", v331_exp_exe, sf_exe, elo, openings, args.movetime / 1000.0, args.concurrency, out_dir)
        results.append(r_exp)

    # Final Summary Table
    print("\n" + "=" * 80)
    print(" FINAL BENCHMARK SUMMARY: v331_main vs v331_exp vs Stockfish")
    print("=" * 80)
    print(f"{'Engine':12s} | {'SF Elo':7s} | {'Score':10s} | {'Pct':6s} | {'W/D/L':12s} | {'Perf Elo':8s}")
    print("-" * 80)
    for r in results:
        wdl = f"{r['wins']}/{r['draws']}/{r['losses']}"
        print(f"{r['engine']:12s} | SF {r['sf_elo']:4d} | {r['score']:4.1f}/{r['total']:<4d} | {r['pct']*100:5.1f}% | {wdl:12s} | {r['perf_elo']:6.0f}")
    print("=" * 80 + "\n")

if __name__ == "__main__":
    main()
