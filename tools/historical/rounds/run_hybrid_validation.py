"""
tools/run_hybrid_validation.py — Tournament runner for Hybrid Dual-NNUE Candidates.

Runs:
1. exp_hybrid_gold vs v334_main (400 games @ 100ms)
2. exp_hybrid_gold vs Stockfish 2900 (400 games @ 200ms)
3. exp_hybrid_gold vs exp16_dual_nnue_tuned (200 games @ 100ms)
4. exp_hybrid_safe vs v334_main (400 games @ 100ms)
5. exp_hybrid_safe vs Stockfish 2900 (400 games @ 200ms)
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
OUT_DIR = ROOT / "artifacts" / "hybrid_validation_campaign"
OUT_DIR.mkdir(parents=True, exist_ok=True)

BASELINE_EXE = ROOT / "engine" / "c" / "zchezz_v334" / "zchezz.exe"
STOCKFISH_EXE = ROOT / "engine" / "stockfish" / "stockfish.exe"
EXP16_EXE = ROOT / "experiments" / "round4_optimizations" / "exp16_dual_nnue_tuned_margins" / "zchezz.exe"
HYBRID_GOLD_EXE = ROOT / "experiments" / "hybrid_candidates" / "exp_hybrid_gold" / "zchezz.exe"
HYBRID_SAFE_EXE = ROOT / "experiments" / "hybrid_candidates" / "exp_hybrid_safe" / "zchezz.exe"

def run_match(cand_exe: Path, cand_label: str, opp_exe: Path, opp_label: str,
              games: int, movetime: int, concurrency: int,
              opp_options: str = "") -> dict:
    match_tag = f"{cand_label}_vs_{opp_label}"
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
    print(f" HYBRID VALIDATION MATCH: {cand_label} vs {opp_label}")
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
    parser = argparse.ArgumentParser()
    parser.add_argument("--concurrency", type=int, default=10)
    args = parser.parse_args()
    
    all_results = []
    
    MATCHES = [
        # 1. exp_hybrid_gold vs v334_main (400 games)
        (HYBRID_GOLD_EXE, "exp_hybrid_gold", BASELINE_EXE, "v334_main", 400, 100, ""),
        # 2. exp_hybrid_gold vs Stockfish 2900 (400 games)
        (HYBRID_GOLD_EXE, "exp_hybrid_gold", STOCKFISH_EXE, "Stockfish_2900", 400, 200, "UCI_LimitStrength=true,UCI_Elo=2900"),
        # 3. exp_hybrid_gold vs exp16_dual_nnue_tuned (200 games H2H direct showdown!)
        (HYBRID_GOLD_EXE, "exp_hybrid_gold", EXP16_EXE, "exp16_dual_nnue_tuned", 200, 100, ""),
        # 4. exp_hybrid_safe vs v334_main (400 games)
        (HYBRID_SAFE_EXE, "exp_hybrid_safe", BASELINE_EXE, "v334_main", 400, 100, ""),
        # 5. exp_hybrid_safe vs Stockfish 2900 (400 games)
        (HYBRID_SAFE_EXE, "exp_hybrid_safe", STOCKFISH_EXE, "Stockfish_2900", 400, 200, "UCI_LimitStrength=true,UCI_Elo=2900"),
    ]
    
    print(f"\nStarting Hybrid Validation: {len(MATCHES)} matches, Concurrency={args.concurrency}")
    for cand_exe, cand_lbl, opp_exe, opp_lbl, g, mt, opp_opts in MATCHES:
        res = run_match(cand_exe, cand_lbl, opp_exe, opp_lbl, g, mt, args.concurrency, opp_opts)
        all_results.append(res)
        (OUT_DIR / "hybrid_results.json").write_text(json.dumps(all_results, indent=2), encoding="utf-8")
        
    print("\n" + "="*85)
    print(" ALL HYBRID MATCHES COMPLETED!")
    print("="*85)

if __name__ == "__main__":
    main()
