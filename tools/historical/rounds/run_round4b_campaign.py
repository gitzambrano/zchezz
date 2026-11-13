"""
tools/run_round4b_campaign.py — Tournament runner for Round 4b (Dual-NNUE 2M Head Candidates).

Runs 200 H2H games @ 100ms per candidate vs v334_main with 10 concurrency.
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
EXP_DIR = ROOT / "experiments" / "round4_optimizations"
OUT_DIR = ROOT / "artifacts" / "round4b_campaign"
OUT_DIR.mkdir(parents=True, exist_ok=True)

BASELINE_EXE = ROOT / "engine" / "c" / "zchezz_v334" / "zchezz.exe"

CANDIDATES = [
    ("exp12b_aux_fast_2m", "Dual-NNUE 2M Head: 2,000,000 positions trained (99.17% corr with NNU3)"),
    ("exp15_dual_nnue_plus_see_d6", "Dual-NNUE (2M) + Quiet SEE Pruning d6 (-40*d)"),
    ("exp16_dual_nnue_tuned_margins", "Dual-NNUE (2M) with Tighter Cutoff Margins (QS +160cp, RFP +100cp)"),
    ("exp17_dual_nnue_plus_r3_best", "Dual-NNUE (2M) + Quiet SEE Pruning d6 + Scaled History Bonus"),
]

def run_candidate(name: str, desc: str, games: int, movetime: int, concurrency: int) -> dict:
    cand_exe = EXP_DIR / name / "zchezz.exe"
    if not cand_exe.is_file():
        return {"name": name, "desc": desc, "error": f"binary missing: {cand_exe}"}
    
    match_out = OUT_DIR / f"{name}_vs_v334"
    match_out.mkdir(parents=True, exist_ok=True)
    
    cmd = [
        sys.executable,
        str(ROOT / "tests" / "_run_tournament_quick_core.py"),
        "--engine-a", str(cand_exe),
        "--label-a", name,
        "--engine-b", str(BASELINE_EXE),
        "--label-b", "v334_main",
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
    print(f" ROUND 4b MATCH: {name}")
    print(f" Description:    {desc}")
    print(f" Configuration:  {games} games ({games//2} openings x 2 colors) @ {movetime}ms/move, Concurrency={concurrency}")
    print(f"{'='*75}\n", flush=True)
    
    t0 = time.time()
    res = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
    elapsed = time.time() - t0
    
    stdout = res.stdout
    (match_out / "stdout.log").write_text(stdout, encoding="utf-8")
    
    logs = sorted(match_out.glob("*.log"), key=os.path.getmtime)
    log_text = logs[-1].read_text(encoding="utf-8", errors="replace") if logs else stdout
    
    h2h_match = re.search(rf"{name}\s+vs\s+v334_main:\s*([+-]?[\d\.]+)\s*.*?([\d\.]+)\s*Elo\s*\(V:(\d+)\s+E:(\d+)\s+D:(\d+)\)", log_text)
    perf_cand = re.search(rf"{name}\s+\|\s+(\d+)\s+\|\s+(\d+)ms\s+\|\s+(\d+)\s+\|\s+([\d\.]+)", log_text)
    perf_base = re.search(r"v334_main\s+\|\s+(\d+)\s+\|\s+(\d+)ms\s+\|\s+(\d+)\s+\|\s+([\d\.]+)", log_text)
    
    data = {
        "name": name,
        "desc": desc,
        "elapsed_s": round(elapsed, 1),
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
        print(f"\n--> RESULT: {name} vs v334_main: {elo_diff:+.1f} ± {elo_err:.1f} Elo ({score}/{total} = {pct:.1f}%) [+{wins} ={draws} -{losses}] in {elapsed:.1f}s")
    else:
        data["raw_log"] = log_text[-1000:]
        print(f"\n--> RESULT: Could not parse H2H line for {name}. See {match_out}/stdout.log")

    if perf_cand and perf_base:
        data["cand_nps"] = int(perf_cand.group(3))
        data["cand_depth"] = float(perf_cand.group(4))
        data["base_nps"] = int(perf_base.group(3))
        data["base_depth"] = float(perf_base.group(4))
        print(f"    Perf: {name} {data['cand_nps']:,} NPS, depth {data['cand_depth']} | v334 {data['base_nps']:,} NPS, depth {data['base_depth']}")

    return data

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--games", type=int, default=200)
    parser.add_argument("--movetime", type=int, default=100)
    parser.add_argument("--concurrency", type=int, default=10)
    parser.add_argument("--only", type=str, default="")
    args = parser.parse_args()
    
    cands_to_run = CANDIDATES
    if args.only:
        cands_to_run = [c for c in CANDIDATES if c[0] == args.only]
        
    print(f"Starting Round 4b Campaign: {len(cands_to_run)} matches, {args.games} games each @ {args.movetime}ms/move, Concurrency={args.concurrency}")
    
    results = []
    t_start = time.time()
    for name, desc in cands_to_run:
        res = run_candidate(name, desc, args.games, args.movetime, args.concurrency)
        results.append(res)
        (OUT_DIR / "campaign_results.json").write_text(json.dumps(results, indent=2), encoding="utf-8")
        
    t_tot = time.time() - t_start
    print(f"\n{'='*75}")
    print(f" ALL ROUND 4b MATCHES FINISHED in {t_tot/60:.1f} minutes")
    print(f"{'='*75}\n")
    
    ranked = sorted([r for r in results if "elo_diff" in r], key=lambda x: x["elo_diff"], reverse=True)
    print(f"{'Rank':<5} | {'Candidate':<30} | {'Elo Diff':<16} | {'Score':<14} | {'Cand NPS':<10} | {'Cand D':<6}")
    print("-" * 90)
    for i, r in enumerate(ranked, 1):
        elo_str = f"{r['elo_diff']:+.1f} ± {r['elo_err']:.1f}"
        sc_str = f"{r['score']}/{r['total_games']} ({r['score_pct']}%)"
        nps_str = f"{r.get('cand_nps', 0):,}"
        d_str = f"{r.get('cand_depth', 0.0):.1f}"
        print(f"{i:<5} | {r['name']:<30} | {elo_str:<16} | {sc_str:<14} | {nps_str:<10} | {d_str:<6}")

if __name__ == "__main__":
    main()
