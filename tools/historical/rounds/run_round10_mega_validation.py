"""
tools/run_round10_mega_validation.py — Mega Validation Campaign for Round 10 (2900 Push).

Workflow:
1. Quick screening (100 games @ 100ms, concurrency=10) for cand1, cand2, and cand3 vs v335.
2. Identifies the #1 candidate with highest Elo gain.
3. Fires the full Mega-Validation requested by user:
   - 600 games H2H vs v335_release @ 100ms (300 openings x 2 colors)
   - 400 games vs Stockfish 2900 @ 200ms (200 openings x 2 colors)
4. Saves full results to artifacts/round10_mega_results.json.
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
OUT_DIR = ROOT / "artifacts" / "round10_mega_validation"
OUT_DIR.mkdir(parents=True, exist_ok=True)

V335_EXE = ROOT / "engine" / "c" / "zchezz_v335" / "zchezz.exe"
STOCKFISH_EXE = ROOT / "engine" / "stockfish" / "stockfish.exe"
CAND_DIR = ROOT / "experiments" / "round10_2900"

CANDIDATES = [
    ("cand1_fast_delta_qs", CAND_DIR / "cand1_fast_delta_qs" / "zchezz.exe", "v335 + Fast Delta Pruning in QS"),
    ("cand2_extended_dual", CAND_DIR / "cand2_extended_dual" / "zchezz.exe", "Cand1 + Extended Fast Cutoff in AB (depth <= 5)"),
    ("cand3_gm_combo",      CAND_DIR / "cand3_gm_combo" / "zchezz.exe",      "Cand2 + Dynamic LMR History (ch / 768)"),
]

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
    print(f" MATCH: {cand_label} vs {opp_label}")
    print(f" Config: {games} games ({games//2} openings x 2 colors) @ {movetime}ms/move, Concurrency={concurrency}")
    if opp_options:
        print(f" Opponent Options: {opp_options}")
    print(f"{'='*75}\n", flush=True)

    t0 = time.time()
    res = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
    elapsed = time.time() - t0

    stdout = res.stdout
    (match_out / "stdout.log").write_text(stdout, encoding="utf-8")

    logs = sorted(match_out.glob("*.log"), key=os.path.getmtime)
    log_text = logs[-1].read_text(encoding="utf-8", errors="replace") if logs else stdout

    h2h_match = re.search(rf"{cand_label}\s+vs\s+{opp_label}:\s*([+-]?[\d\.]+)\s*.*?([\d\.]+)\s*Elo\s*\(V:(\d+)\s+E:(\d+)\s+D:(\d+)\)", log_text)
    perf_cand = re.search(rf"{cand_label}\s+\|\s+(\d+)\s+\|\s+(\d+)ms\s+\|\s+(\d+)\s+\|\s+([\d\.]+)", log_text)
    perf_opp  = re.search(rf"{opp_label}\s+\|\s+(\d+)\s+\|\s+(\d+)ms\s+\|\s+(\d+)\s+\|\s+([\d\.]+)", log_text)

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
        data["cand_nps"] = int(perf_cand.group(3))
        data["cand_depth"] = float(perf_cand.group(4))
        data["opp_nps"] = int(perf_opp.group(3))
        data["opp_depth"] = float(perf_opp.group(4))
        print(f"    Perf: {cand_label} {data['cand_nps']:,} NPS, depth {data['cand_depth']} | {opp_label} {data['opp_nps']:,} NPS, depth {data['opp_depth']}")

    return data

def main():
    p = argparse.ArgumentParser()
    p.add_argument("--screen-games", type=int, default=100)
    p.add_argument("--h2h-games", type=int, default=600)
    p.add_argument("--sf-games", type=int, default=400)
    p.add_argument("--h2h-movetime", type=int, default=100)
    p.add_argument("--sf-movetime", type=int, default=200)
    p.add_argument("--concurrency", type=int, default=10)
    args = p.parse_args()

    print("=" * 80)
    print(" ROUND 10 MEGA-CAMPAIGN — ROAD TO 2900 ELO")
    print("=" * 80)

    # Phase 1: Screening 3 candidates vs v335
    print("\n>>> PHASE 1: SCREENING CANDIDATES (100 games each vs v335)")
    screening_results = []
    for label, exe, desc in CANDIDATES:
        res = run_match(exe, label, V335_EXE, "v335_release",
                        games=args.screen_games, movetime=args.h2h_movetime,
                        concurrency=args.concurrency)
        res["desc"] = desc
        screening_results.append(res)

    # Sort by Elo difference
    screening_results.sort(key=lambda x: x.get("elo_diff", -999.0), reverse=True)
    best = screening_results[0]
    best_label = best["cand"]
    best_exe = CAND_DIR / best_label / "zchezz.exe"

    print("\n" + "=" * 80)
    print(f" PHASE 1 WINNER: {best_label} ({best.get('elo_diff', 0):+.1f} Elo vs v335)")
    print(f" Description: {best.get('desc', '')}")
    print("=" * 80)

    # Phase 2: Full Mega-Validation of the Best Candidate
    print(f"\n>>> PHASE 2: FULL MEGA-VALIDATION ON {best_label}")
    print(f" 1. 600 games H2H vs v335 @ {args.h2h_movetime}ms")
    print(f" 2. 400 games vs Stockfish 2900 @ {args.sf_movetime}ms")

    # 1. 600 H2H games vs v335
    res_h2h_600 = run_match(best_exe, best_label, V335_EXE, "v335_release",
                            games=args.h2h_games, movetime=args.h2h_movetime,
                            concurrency=args.concurrency)

    # 2. 400 games vs Stockfish 2900
    res_sf_400 = run_match(best_exe, best_label, STOCKFISH_EXE, "Stockfish_2900",
                           games=args.sf_games, movetime=args.sf_movetime,
                           concurrency=args.concurrency,
                           opp_options="UCI_LimitStrength=true,UCI_Elo=2900")

    final_payload = {
        "screening": screening_results,
        "best_candidate": best_label,
        "mega_h2h_600": res_h2h_600,
        "mega_sf_400": res_sf_400,
    }
    (OUT_DIR / "final_report.json").write_text(json.dumps(final_payload, indent=2), encoding="utf-8")

    print("\n" + "=" * 85)
    print(" ROUND 10 MEGA-VALIDATION CAMPAIGN COMPLETE!")
    print(f" Best: {best_label}")
    print(f" Mega H2H (600g): {res_h2h_600.get('elo_diff', 0):+.1f} ± {res_h2h_600.get('elo_err', 0):.1f} Elo ({res_h2h_600.get('score_pct', 0):.1f}%)")
    print(f" Mega SF (400g):  {res_sf_400.get('elo_diff', 0):+.1f} ± {res_sf_400.get('elo_err', 0):.1f} Elo ({res_sf_400.get('score_pct', 0):.1f}%)")
    print("=" * 85)

if __name__ == "__main__":
    main()
