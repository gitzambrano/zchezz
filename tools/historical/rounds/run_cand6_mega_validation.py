"""
tools/run_cand6_mega_validation.py — Official Mega-Validation for cand6_combo_clean (+45.4 Elo screening).

Runs:
1. 600 games H2H vs v335_release @ 100ms (300 openings x 2 colors reversed)
2. 400 games vs Stockfish 2900 @ 200ms (200 openings x 2 colors reversed)
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
OUT_DIR = ROOT / "artifacts" / "cand6_mega_validation"
OUT_DIR.mkdir(parents=True, exist_ok=True)

V335_EXE = ROOT / "engine" / "c" / "zchezz_v335" / "zchezz.exe"
STOCKFISH_EXE = ROOT / "engine" / "stockfish" / "stockfish.exe"
CAND6_EXE = ROOT / "experiments" / "round11_clean" / "cand6_combo_clean" / "zchezz.exe"

def run_match(cand_exe: Path, cand_label: str, opp_exe: Path, opp_label: str,
              games: int, movetime: int, concurrency: int,
              opp_options: str = "") -> dict:
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
    if opp_options:
        cmd.extend(["--options-b", opp_options])

    print(f"\n{'='*75}")
    print(f" OFFICIAL MEGA-VALIDATION MATCH: {cand_label} vs {opp_label}")
    print(f" Config: {games} games ({games//2} openings x 2 colors) @ {movetime}ms/move, Concurrency={concurrency}")
    if opp_options:
        print(f" Opponent Options: {opp_options}")
    print(f"{'='*75}\n", flush=True)

    t0 = time.time()
    res = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
    elapsed = time.time() - t0

    stdout = res.stdout
    (match_out / "stdout.log").write_text(stdout, encoding="utf-8")

    # Read final report from log
    logs = sorted(match_out.glob("*.log"), key=os.path.getmtime)
    log_text = logs[-1].read_text(encoding="utf-8", errors="replace") if logs else stdout

    # Find the LAST H2H summary in log_text (final report)
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
        print(f"\n--> FINAL RESULT: {cand_label} vs {opp_label}: {elo_diff:+.1f} ± {elo_err:.1f} Elo ({score}/{total} = {pct:.1f}%) [+{wins} ={draws} -{losses}] in {elapsed:.1f}s")
    else:
        print(f"\n--> FINAL RESULT: Could not parse H2H line for {match_tag}. See {match_out}/stdout.log")

    if perf_cand and perf_opp:
        data["cand_nps"] = int(perf_cand.group(3))
        data["cand_depth"] = float(perf_cand.group(4))
        data["opp_nps"] = int(perf_opp.group(3))
        data["opp_depth"] = float(perf_opp.group(4))
        print(f"    Perf: {cand_label} {data['cand_nps']:,} NPS, depth {data['cand_depth']} | {opp_label} {data['opp_nps']:,} NPS, depth {data['opp_depth']}")

    return data

def main():
    p = argparse.ArgumentParser()
    p.add_argument("--h2h-games", type=int, default=600)
    p.add_argument("--sf-games", type=int, default=400)
    p.add_argument("--h2h-movetime", type=int, default=100)
    p.add_argument("--sf-movetime", type=int, default=200)
    p.add_argument("--concurrency", type=int, default=10)
    args = p.parse_args()

    print("=" * 80)
    print(" OFFICIAL CAND6_COMBO_CLEAN MEGA-VALIDATION (1,000 GAMES)")
    print("=" * 80)

    # 1. 600 games H2H vs v335
    res_h2h = run_match(CAND6_EXE, "cand6_combo_clean", V335_EXE, "v335_release",
                        games=args.h2h_games, movetime=args.h2h_movetime,
                        concurrency=args.concurrency)

    # 2. 400 games vs Stockfish 2900
    res_sf = run_match(CAND6_EXE, "cand6_combo_clean", STOCKFISH_EXE, "Stockfish_2900",
                       games=args.sf_games, movetime=args.sf_movetime,
                       concurrency=args.concurrency,
                       opp_options="UCI_LimitStrength=true,UCI_Elo=2900")

    final_payload = {
        "candidate": "cand6_combo_clean",
        "description": "v335 + Pure LMR History (ch/768) + Dual Fast Cutoff depth<=4",
        "h2h_600": res_h2h,
        "stockfish_400": res_sf,
    }
    (OUT_DIR / "final_report.json").write_text(json.dumps(final_payload, indent=2), encoding="utf-8")

    print("\n" + "=" * 85)
    print(" MEGA-VALIDATION COMPLETE!")
    print(f" H2H (600g vs v335):  {res_h2h.get('elo_diff', 0):+.1f} ± {res_h2h.get('elo_err', 0):.1f} Elo ({res_h2h.get('score_pct', 0):.1f}%)")
    print(f" SF 2900 (400g):       {res_sf.get('elo_diff', 0):+.1f} ± {res_sf.get('elo_err', 0):.1f} Elo ({res_sf.get('score_pct', 0):.1f}%)")
    print("=" * 85)

if __name__ == "__main__":
    main()
