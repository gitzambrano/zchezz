#!/usr/bin/env python3
"""Triangular tournament runner for active Zchezz lineages (NNU5, NNU4, NNU3).

Runs paired-opening matches for each pairwise matchup across the three active lines:
  1. v605 (NNU5) vs v510 (NNU4)
  2. v605 (NNU5) vs v335 (NNU3)
  3. v510 (NNU4) vs v335 (NNU3)
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
    ea: Path,
    la: str,
    eb: Path,
    lb: str,
    games_openings: int,
    concurrency: int,
    movetime_ms: int,
    results_dir: Path,
) -> int:
    print(f"\n{'='*70}")
    print(f" >>> MATCHUP: {la} vs {lb} ({games_openings*2} games)")
    print(f"     Engine A: {ea}")
    print(f"     Engine B: {eb}")
    print(f"     Movetime: {movetime_ms}ms | Concurrency: {concurrency}")
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
        print(f"[WARNING] Matchup {la} vs {lb} exited with code {res.returncode}")
    else:
        print(f"\n[SUCCESS] Matchup {la} vs {lb} finished in {elapsed:.1f}s")
    return res.returncode


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--games", type=int, default=100, help="Openings per matchup (x2 with color swap)")
    parser.add_argument("--concurrency", type=int, default=5, help="Concurrent games (default: 5)")
    parser.add_argument("--movetime", type=int, default=100, help="Time per move in ms (default: 100)")
    parser.add_argument("--show-config", action="store_true", help="Print configuration and exit")
    parser.add_argument("--prof-nnu5", default="v605", help="NNU5 profile (default: v605)")
    parser.add_argument("--prof-nnu4", default="v510", help="NNU4 profile (default: v510)")
    parser.add_argument("--prof-nnu3", default="v335", help="NNU3 profile (default: v335)")
    args = parser.parse_args()

    nnu5_exe = get_engine_exe(args.prof_nnu5)
    nnu4_exe = get_engine_exe(args.prof_nnu4)
    nnu3_exe = get_engine_exe(args.prof_nnu3)

    if args.show_config:
        print("triangular_tournament:")
        print(f"  games_per_matchup={args.games * 2}")
        print(f"  concurrency={args.concurrency}")
        print(f"  movetime_ms={args.movetime}")
        print(f"  nnu5_exe={nnu5_exe} ({args.prof_nnu5})")
        print(f"  nnu4_exe={nnu4_exe} ({args.prof_nnu4})")
        print(f"  nnu3_exe={nnu3_exe} ({args.prof_nnu3})")
        return 0

    assert nnu5_exe.is_file(), f"Missing NNU5 executable: {nnu5_exe}"
    assert nnu4_exe.is_file(), f"Missing NNU4 executable: {nnu4_exe}"
    assert nnu3_exe.is_file(), f"Missing NNU3 executable: {nnu3_exe}"

    results_dir = ROOT / "artifacts" / "experiments" / f"triangular_{args.prof_nnu5}_{args.prof_nnu4}_{args.prof_nnu3}"
    results_dir.mkdir(parents=True, exist_ok=True)

    print("\n" + "#" * 70)
    print(f" ZCHEZZ TRIANGULAR TOURNAMENT: {args.prof_nnu5} vs {args.prof_nnu4} vs {args.prof_nnu3}")
    print(f" Configuration: {args.games * 2} games per matchup ({args.games} openings x 2 colors)")
    print(f" Concurrency: {args.concurrency} | Movetime: {args.movetime}ms")
    print("#" * 70)

    # 1. NNU5 vs NNU4
    run_match(nnu5_exe, args.prof_nnu5, nnu4_exe, args.prof_nnu4, args.games, args.concurrency, args.movetime, results_dir)

    # 2. NNU5 vs NNU3
    run_match(nnu5_exe, args.prof_nnu5, nnu3_exe, args.prof_nnu3, args.games, args.concurrency, args.movetime, results_dir)

    # 3. NNU4 vs NNU3
    run_match(nnu4_exe, args.prof_nnu4, nnu3_exe, args.prof_nnu3, args.games, args.concurrency, args.movetime, results_dir)

    print("\n" + "#" * 70)
    print(" TRIANGULAR TOURNAMENT COMPLETE")
    print(f" Results and PGNs saved to: {results_dir}")
    print("#" * 70)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
