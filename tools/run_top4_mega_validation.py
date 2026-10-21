"""
tools/run_top4_mega_validation.py — Mega Validation Campaign for Top 4 Candidates.

For each of the top 4 candidates:
1. 400 games H2H vs v334_main (200 openings x 2 colors reversed @ 100ms)
2. 400 games vs Stockfish 2900 (200 openings x 2 colors reversed @ 200ms)

Total per candidate: 800 games.
Total campaign: 3,200 games with 10 concurrent workers.
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
OUT_DIR = ROOT / "artifacts" / "mega_validation_campaign"
OUT_DIR.mkdir(parents=True, exist_ok=True)

BASELINE_EXE = ROOT / "engine" / "c" / "zchezz_v334" / "zchezz.exe"
STOCKFISH_EXE = ROOT / "engine" / "stockfish" / "stockfish.exe"

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
    print(f" MEGA VALIDATION MATCH: {cand_label} vs {opp_label}")
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

def run_mega_campaign(candidates: list[tuple[str, Path]], h2h_games: int = 400, sf_games: int = 400,
                      h2h_movetime: int = 100, sf_movetime: int = 200, concurrency: int = 10):
    all_results = []
    
    print(f"\n{'='*75}")
    print(f" STARTING MEGA VALIDATION CAMPAIGN FOR {len(candidates)} CANDIDATES")
    print(f" Total matches: {len(candidates) * 2} (H2H 400j @ {h2h_movetime}ms + Stockfish 2900 400j @ {sf_movetime}ms)")
    print(f" Total games:   {len(candidates) * (h2h_games + sf_games):,} games with {concurrency} workers")
    print(f"{'='*75}\n")
    
    for label, exe_path in candidates:
        if not exe_path.is_file():
            print(f"ERROR: Executable missing for {label}: {exe_path}")
            continue
            
        # 1. H2H vs v334_main
        res_h2h = run_match(exe_path, label, BASELINE_EXE, "v334_main",
                            games=h2h_games, movetime=h2h_movetime, concurrency=concurrency)
        all_results.append(res_h2h)
        (OUT_DIR / "mega_results.json").write_text(json.dumps(all_results, indent=2), encoding="utf-8")
        
        # 2. Benchmark vs Stockfish 2900
        res_sf = run_match(exe_path, label, STOCKFISH_EXE, "Stockfish_2900",
                           games=sf_games, movetime=sf_movetime, concurrency=concurrency,
                           opp_options="UCI_LimitStrength=true,UCI_Elo=2900")
        all_results.append(res_sf)
        (OUT_DIR / "mega_results.json").write_text(json.dumps(all_results, indent=2), encoding="utf-8")

    print("\n" + "="*85)
    print(" MEGA VALIDATION CAMPAIGN COMPLETED")
    print("="*85)

DEFAULT_TOP4 = [
    ("exp16_dual_nnue_tuned", ROOT / "experiments/round4_optimizations/exp16_dual_nnue_tuned_margins/zchezz.exe"),
    ("exp12_aux_fast_nnue",   ROOT / "experiments/round4_optimizations/exp12_aux_fast_nnue/zchezz.exe"),
    ("exp20_exp16_rfp_d4",    ROOT / "experiments/round5_combinations/exp20_exp16_rfp_d4/zchezz.exe"),
    ("exp19_exp16_hist_scale",ROOT / "experiments/round5_combinations/exp19_exp16_hist_scale/zchezz.exe"),
]

if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--h2h-games", type=int, default=400)
    p.add_argument("--sf-games", type=int, default=400)
    p.add_argument("--h2h-movetime", type=int, default=100)
    p.add_argument("--sf-movetime", type=int, default=200)
    p.add_argument("--concurrency", type=int, default=10)
    p.add_argument("--only", type=str, default="")
    args = p.parse_args()
    
    cands = DEFAULT_TOP4
    if args.only:
        cands = [c for c in DEFAULT_TOP4 if c[0] == args.only]
        
    run_mega_campaign(cands, h2h_games=args.h2h_games, sf_games=args.sf_games,
                      h2h_movetime=args.h2h_movetime, sf_movetime=args.sf_movetime,
                      concurrency=args.concurrency)
