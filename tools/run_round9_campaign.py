"""
tools/run_round9_campaign.py — Tournament runner for Round 9 Candidates (Toward 2900).

Runs 200 games @ 100ms for each candidate vs v335_release.
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
OUT_DIR = ROOT / "artifacts" / "round9_2900_campaign"
OUT_DIR.mkdir(parents=True, exist_ok=True)

BASELINE_EXE = ROOT / "engine" / "c" / "zchezz_v335" / "zchezz.exe"
CANDIDATES_DIR = ROOT / "experiments" / "round9_2900"

CANDIDATES = [
    ("exp22_fast_delta_qs", CANDIDATES_DIR / "exp22_fast_delta_qs" / "zchezz.exe", "Fast Delta Pruning in QS using Dual-NNUE"),
    ("exp23_quiet_see_ordering", CANDIDATES_DIR / "exp23_quiet_see_ordering" / "zchezz.exe", "Bad quiet move demotion in move ordering (SEE < 0)"),
    ("exp24_lmr_history_tuning", CANDIDATES_DIR / "exp24_lmr_history_tuning" / "zchezz.exe", "Enhanced LMR history adjustment (ch / 768)"),
    ("exp25_rfp_improving_tune", CANDIDATES_DIR / "exp25_rfp_improving_tune" / "zchezz.exe", "Tuned RFP margin with improving flag (depth*70 - 45)"),
    ("exp26_combo_2900", CANDIDATES_DIR / "exp26_combo_2900" / "zchezz.exe", "Grand Master Combo (Fast Delta + SEE Order + LMR + RFP)"),
]

def run_match(cand_label: str, cand_exe: Path, desc: str, games: int, concurrency: int) -> dict:
    match_tag = f"{cand_label}_vs_v335"
    match_out = OUT_DIR / match_tag
    match_out.mkdir(parents=True, exist_ok=True)

    cmd = [
        sys.executable,
        str(ROOT / "tests" / "_run_tournament_quick_core.py"),
        "--engine-a", str(cand_exe),
        "--label-a", cand_label,
        "--engine-b", str(BASELINE_EXE),
        "--label-b", "v335_release",
        "--games", str(games // 2),
        "--movetime", "100",
        "--concurrency", str(concurrency),
        "--results-dir", str(match_out),
        "--perf",
        "--no-pgn",
        "--no-epd",
        "--no-bin",
    ]

    print(f"\n{'='*75}")
    print(f" ROUND 9 MATCH: {cand_label} vs v335_release")
    print(f" Description: {desc}")
    print(f" Config: {games} games @ 100ms/move, Concurrency={concurrency}")
    print(f"{'='*75}\n", flush=True)

    t0 = time.time()
    res = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
    elapsed = time.time() - t0

    stdout = res.stdout
    (match_out / "stdout.log").write_text(stdout, encoding="utf-8")

    logs = sorted(match_out.glob("*.log"), key=os.path.getmtime)
    log_text = logs[-1].read_text(encoding="utf-8", errors="replace") if logs else stdout

    h2h_match = re.search(rf"{cand_label}\s+vs\s+v335_release:\s*([+-]?[\d\.]+)\s*.*?([\d\.]+)\s*Elo\s*\(V:(\d+)\s+E:(\d+)\s+D:(\d+)\)", log_text)
    perf_cand = re.search(rf"{cand_label}\s+\|\s+(\d+)\s+\|\s+(\d+)ms\s+\|\s+(\d+)\s+\|\s+([\d\.]+)", log_text)
    perf_opp  = re.search(rf"v335_release\s+\|\s+(\d+)\s+\|\s+(\d+)ms\s+\|\s+(\d+)\s+\|\s+([\d\.]+)", log_text)

    data = {
        "candidate": cand_label,
        "description": desc,
        "elapsed_s": round(elapsed, 1),
        "games": games,
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
        print(f"\n--> RESULT: {cand_label}: {elo_diff:+.1f} ± {elo_err:.1f} Elo ({score}/{total} = {pct:.1f}%) [+{wins} ={draws} -{losses}] in {elapsed:.1f}s")
    else:
        print(f"\n--> RESULT: Could not parse H2H line. See {match_out}/stdout.log")

    if perf_cand and perf_opp:
        data["cand_nps"] = int(perf_cand.group(3))
        data["cand_depth"] = float(perf_cand.group(4))
        data["opp_nps"] = int(perf_opp.group(3))
        data["opp_depth"] = float(perf_opp.group(4))
        print(f"    Perf: {cand_label} {data['cand_nps']:,} NPS, depth {data['cand_depth']} | v335 {data['opp_nps']:,} NPS, depth {data['opp_depth']}")

    return data

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--concurrency", type=int, default=10)
    parser.add_argument("--games", type=int, default=200)
    args = parser.parse_args()

    results = []
    print(f"\nStarting Round 9 Campaign: {len(CANDIDATES)} candidates, {args.games} games each, Concurrency={args.concurrency}")

    for label, exe_path, desc in CANDIDATES:
        res = run_match(label, exe_path, desc, args.games, args.concurrency)
        results.append(res)
        (OUT_DIR / "round9_results.json").write_text(json.dumps(results, indent=2), encoding="utf-8")

    print("\n" + "="*85)
    print(" ROUND 9 CAMPAIGN COMPLETED — SUMMARY TABLE:")
    print("="*85)
    print(f"{'Candidate':<28} | {'Elo vs v335':<16} | {'Score':<14} | {'V / E / D':<14} | {'Depth':<6}")
    print("-" * 85)
    for r in results:
        if "elo_diff" in r:
            elo_str = f"{r['elo_diff']:+.1f} ± {r['elo_err']:.1f}"
            score_str = f"{r['score']}/{r['total_games']} ({r['score_pct']}%)"
            ved_str = f"+{r['wins']} ={r['draws']} -{r['losses']}"
            depth_str = f"{r.get('cand_depth', 0.0):.1f}"
            print(f"{r['candidate']:<28} | {elo_str:<16} | {score_str:<14} | {ved_str:<14} | {depth_str:<6}")

if __name__ == "__main__":
    main()
