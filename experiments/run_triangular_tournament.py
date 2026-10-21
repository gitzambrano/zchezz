#!/usr/bin/env python3
"""Triangular tournament runner for Zchezz v600, v507 and v331.

Runs 200 paired-opening games (100 openings x 2 colors reversed) for each
pairwise matchup with 5 concurrent games (10 cores max, Threads=1):
  1. v600 (NNUE5) vs v507 (NNU4)
  2. v600 (NNUE5) vs v331 (NNU3)
  3. v507 (NNU4) vs v331 (NNU3)
"""
from __future__ import annotations
import argparse
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "utils"))
from engine_profiles import profile

def get_engine_exe(prof_name: str) -> Path:
    p = profile(prof_name)
    for name in ("zchezz.exe", "zchezz"):
        exe = p.engine_dir / name
        if exe.is_file():
            return exe
    return p.engine_dir / "zchezz.exe"

def run_match(
    ea: str,
    la: str,
    eb: str,
    lb: str,
    games_openings: int,
    concurrency: int,
    movetime_ms: int,
    results_dir: Path,
):
    print(f"\n{'='*70}")
    print(f" >>> CONFRONTO: {la} vs {lb} ({games_openings*2} jogos)")
    print(f"     Engine A: {ea}")
    print(f"     Engine B: {eb}")
    print(f"     Movetime: {movetime_ms}ms | Concorrência: {concurrency}")
    print(f"{'='*70}\n")
    
    cmd = [
        sys.executable,
        str(ROOT / "tests" / "_run_tournament_quick_core.py"),
        "--engine-a", str(ea),
        "--label-a", la,
        "--engine-b", str(eb),
        "--label-b", lb,
        "--games", str(games_openings),
        "--concurrency", str(concurrency),
        "--movetime", str(movetime_ms),
        "--threads", "1",
        "--results-dir", str(results_dir),
    ]
    t0 = time.time()
    res = subprocess.run(cmd, cwd=ROOT)
    elapsed = time.time() - t0
    if res.returncode != 0:
        print(f"[AVISO] Confronto {la} vs {lb} encerrou com código {res.returncode}")
    else:
        print(f"\n[SUCESSO] Confronto {la} vs {lb} finalizado em {elapsed:.1f}s")
    return res.returncode

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--games", type=int, default=100, help="Aberturas por confronto (x2 com troca de cores)")
    parser.add_argument("--concurrency", type=int, default=5, help="Jogos concomitantes (padrão: 5)")
    parser.add_argument("--movetime", type=int, default=100, help="Tempo por lance em ms (padrão: 100)")
    parser.add_argument("--show-config", action="store_true", help="Mostra a configuração e sai")
    parser.add_argument("--prof-6xx", default="v604", help="Perfil NNU5 (padrão: v604)")
    parser.add_argument("--prof-5xx", default="v510", help="Perfil NNU4 (padrão: v510)")
    parser.add_argument("--prof-3xx", default="v334", help="Perfil NNU3 (padrão: v334)")
    args = parser.parse_args()

    v600_exe = get_engine_exe(args.prof_6xx)
    v507_exe = get_engine_exe(args.prof_5xx)
    v331_exe = get_engine_exe(args.prof_3xx)

    if args.show_config:
        print(f"triangular_tournament:")
        print(f"  games_per_matchup={args.games * 2}")
        print(f"  concurrency={args.concurrency}")
        print(f"  movetime_ms={args.movetime}")
        print(f"  v600_exe={v600_exe}")
        print(f"  v507_exe={v507_exe}")
        print(f"  v331_exe={v331_exe}")
        return 0

    assert v600_exe.is_file(), f"Faltando executável v600: {v600_exe}"
    assert v507_exe.is_file(), f"Faltando executável v507: {v507_exe}"
    assert v331_exe.is_file(), f"Faltando executável v331: {v331_exe}"

    results_dir = ROOT / "artifacts" / "triangular_tournament"
    results_dir.mkdir(parents=True, exist_ok=True)

    print("\n" + "#"*70)
    print(" TORNEIO TRIANGULAR ZCHEZZ: v600 (NNUE5) vs v507 (NNU4) vs v331 (NNU3)")
    print(f" Configuração: {args.games * 2} partidas por par ({args.games} aberturas x 2 cores)")
    print(f" Concorrência: {args.concurrency} jogos simultâneos | Movetime: {args.movetime}ms")
    print("#"*70)

    # 1. v600 vs v507
    run_match(v600_exe, args.prof_6xx, v507_exe, args.prof_5xx, args.games, args.concurrency, args.movetime, results_dir)

    # 2. 6xx vs 3xx
    run_match(v600_exe, args.prof_6xx, v331_exe, args.prof_3xx, args.games, args.concurrency, args.movetime, results_dir)

    # 3. 5xx vs 3xx
    run_match(v507_exe, args.prof_5xx, v331_exe, args.prof_3xx, args.games, args.concurrency, args.movetime, results_dir)

    print("\n" + "#"*70)
    print(" TORNEIO TRIANGULAR COMPLETO!")
    print(f" Resultados e PGNs salvos em: {results_dir}")
    print("#"*70)
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
