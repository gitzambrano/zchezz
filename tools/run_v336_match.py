"""
tools/run_v336_match.py — Benchmark cand_v336_sf_anneal vs v335_release.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = ROOT / "artifacts" / "v336_validation"
OUT_DIR.mkdir(parents=True, exist_ok=True)

V336_EXE = ROOT / "experiments" / "cand_v336_sf_anneal" / "zchezz.exe"
V335_EXE = ROOT / "engine" / "c" / "zchezz_v335" / "zchezz.exe"

def run_match(cand_exe: Path, cand_label: str, opp_exe: Path, opp_label: str,
              games: int, movetime: int, concurrency: int) -> dict:
    match_tag = f"{cand_label}_vs_{opp_label}_{games}g"
    match_out = OUT_DIR / match_tag
    match_out.mkdir(parents=True, exist_ok=True)

    cmd = [
        sys.executable,
        str(ROOT / "tests" / "_run_tournament_quick_core.py"),
        "--engine-a", str(cand_exe),
        "--label-a", cand_label,
        "--engine-b", str(opp_exe),
        "--label-b", opp_label,
        "--games", str(games // 2),
        "--movetime", str(movetime),
        "--concurrency", str(concurrency),
        "--results-dir", str(match_out),
        "--perf",
        "--no-pgn",
        "--no-epd",
        "--no-bin",
    ]

    print(f"\n{'='*75}")
    print(f" MATCH: {cand_label} vs {opp_label}")
    print(f" Config: {games} games ({games//2} openings x 2 colors) @ {movetime}ms/move, Concurrency={concurrency}")
    print(f"{'='*75}\n", flush=True)

    t0 = time.time()
    res = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
    elapsed = time.time() - t0

    stdout = res.stdout
    (match_out / "stdout.log").write_text(stdout, encoding="utf-8")

    logs = sorted(match_out.glob("*.log"), key=os.path.getmtime)
    log_text = logs[-1].read_text(encoding="utf-8", errors="replace") if logs else stdout

    matches = list(re.finditer(rf"{cand_label}\s+vs\s+{opp_label}:\s*([+-]?[\d\.]+)\s*.*?([\d\.]+)\s*Elo\s*\(V:(\d+)\s+E:(\d+)\s+D:(\d+)\)", log_text))
    h2h_match = matches[-1] if matches else None

    perf_cand_m = list(re.finditer(rf"{cand_label}\s+\|\s+(\d+)\s+\|\s+(\d+)ms\s+\|\s+(\d+)\s+\|\s+([\d\.]+)", log_text))
    perf_cand = perf_cand_m[-1] if perf_cand_m else None

    perf_opp_m = list(re.finditer(rf"{opp_label}\s+\|\s+(\d+)\s+\|\s+(\d+)ms\s+\|\s+(\d+)\s+\|\s+([\d\.]+)", log_text))
    perf_opp = perf_opp_m[-1] if perf_opp_m else None

    data = {
        "match": match_tag,
        "cand": cand_label,
        "opp": opp_label,
        "elapsed_s": round(elapsed, 1),
        "games": games,
        "movetime": movetime,
    }

    if h2h_match:
        elo_diff = float(h2h_match.group(1))
        elo_err = float(h2h_match.group(2))
        wins = int(h2h_match.group(3))
        draws = int(h2h_match.group(4))
        losses = int(h2h_match.group(5))
        total = wins + draws + losses
        score = wins + 0.5 * draws
        pct = (score / total) * 100.0 if total else 0.0
        data.update({
            "elo_diff": elo_diff,
            "elo_err": elo_err,
            "wins": wins,
            "draws": draws,
            "losses": losses,
            "total_games": total,
            "score": score,
            "score_pct": round(pct, 1),
        })
        print(f"\n--> RESULT: {cand_label} vs {opp_label}: {elo_diff:+.1f} ± {elo_err:.1f} Elo ({score}/{total} = {pct:.1f}%) [+{wins} ={draws} -{losses}] in {elapsed:.1f}s")
    else:
        print(f"\n--> RESULT: Could not parse H2H line for {match_tag}. See {match_out}/stdout.log")

    if perf_cand and perf_opp:
        data["cand_nps"] = int(perf_cand.group(1))
        data["cand_depth"] = float(perf_cand.group(4))
        data["opp_nps"] = int(perf_opp.group(1))
        data["opp_depth"] = float(perf_opp.group(4))
        print(f"    Perf: {cand_label} {data['cand_nps']:,} NPS, depth {data['cand_depth']} | {opp_label} {data['opp_nps']:,} NPS, depth {data['opp_depth']}")

    return data

def main():
    p = argparse.ArgumentParser()
    p.add_argument("--games", type=int, default=200)
    p.add_argument("--movetime", type=int, default=100)
    p.add_argument("--concurrency", type=int, default=10)
    args = p.parse_args()

    print("=" * 80)
    print(" BENCHMARKING RETRAINED v336 (SF ANNEALED) vs v335 MAIN")
    print("=" * 80)

    res = run_match(V336_EXE, "cand_v336", V335_EXE, "v335_release",
                    games=args.games, movetime=args.movetime, concurrency=args.concurrency)

    (OUT_DIR / "final_report.json").write_text(json.dumps(res, indent=2), encoding="utf-8")

if __name__ == "__main__":
    main()
