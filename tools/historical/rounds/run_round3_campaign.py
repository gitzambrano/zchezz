import argparse
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EXP_DIR = ROOT / "experiments" / "search_improvements_round3"
OUT_DIR = ROOT / "artifacts" / "search_round3"
OUT_DIR.mkdir(parents=True, exist_ok=True)

BASELINE_EXE = ROOT / "engine" / "c" / "zchezz_v334" / "zchezz.exe"

CANDIDATES = [
    ("exp1_lmp_tight", "Tighter Late Move Pruning at Low Depths (6, 12, 19, 28...)"),
    ("exp2_nmp_eval_scale", "Dynamic Proportional NMP Reduction ((eval-beta)/180)"),
    ("exp3_asp_widening", "Smooth Progressive Aspiration Window (+/-16, geometric widening)"),
    ("exp4_capture_lmr_dyn", "Dynamic Losing Capture LMR (depth>=6 reduce=2)"),
    ("exp5_history_bonus_scale", "Scaled History Gravity Bonus at Mid Depths"),
    ("exp6_rfp_tight_improving", "Asymmetric RFP with Fine-Grained Improving Margin (70*d)"),
    ("exp7_see_quiet_d6", "Quiet SEE Pruning Extended to Depth 6 (-40*d)"),
    ("exp8_counter_virtual_hist", "Countermove Virtual History Bonus (+768) in Continuous LMR"),
    ("exp9_iir_pv_relaxed", "Subtle IIR on Depth >= 4 when TT Move Missing"),
    ("exp10_history_pruning_deep", "History Pruning Extended to Depth 5 (-48*d)"),
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
    print(f" ROUND 3 MATCH: {name}")
    print(f" Description:   {desc}")
    print(f" Configuration: {games} games ({games//2} openings x 2 colors) @ {movetime}ms/move, Concurrency={concurrency}")
    print(f"{'='*75}\n", flush=True)
    
    t0 = time.time()
    res = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
    elapsed = time.time() - t0
    
    stdout = res.stdout
    (match_out / "stdout.log").write_text(stdout, encoding="utf-8")
    
    # Check generated log file
    logs = sorted(match_out.glob("*.log"), key=os.path.getmtime)
    log_text = logs[-1].read_text(encoding="utf-8", errors="replace") if logs else stdout
    
    # Parse results
    h2h_match = re.search(rf"{name}\s+vs\s+v334_main:\s*([+-]?[\d\.]+)\s*.*?([\d\.]+)\s*Elo\s*\(V:(\d+)\s+E:(\d+)\s+D:(\d+)\)", log_text)
    perf_cand = re.search(rf"{name}\s+\|\s+(\d+)\s+\|\s+(\d+)ms\s+\|\s+(\d+)\s+\|\s+([\d\.]+)", log_text)
    perf_base = re.search(r"v334_main\s+\|\s+(\d+)\s+\|\s+(\d+)ms\s+\|\s+(\d+)\s+\|\s+([\d\.]+)", log_text)
    
    data = {
        "name": name,
        "desc": desc,
        "elapsed_s": round(elapsed, 1),
        "returncode": res.returncode,
    }
    
    if h2h_match:
        elo = float(h2h_match.group(1))
        err = float(h2h_match.group(2))
        v = int(h2h_match.group(3))
        e = int(h2h_match.group(4))
        d = int(h2h_match.group(5))
        total = v + e + d
        pts = v + 0.5 * e
        pct = (pts / total * 100.0) if total else 0.0
        data.update({
            "elo": elo, "error": err,
            "wins": v, "draws": e, "losses": d,
            "points": pts, "total": total, "pct": round(pct, 2)
        })
    else:
        pts_match = re.search(rf"{name}\s+---\s+([\d\.]+)/(\d+)", log_text)
        if pts_match:
            pts = float(pts_match.group(1))
            total = int(pts_match.group(2))
            pct = pts / total * 100.0 if total else 0.0
            data.update({"points": pts, "total": total, "pct": round(pct, 2), "elo": 0.0, "error": 0.0})
        else:
            data.update({"elo": 0.0, "error": 0.0, "wins": 0, "draws": 0, "losses": 0, "points": 0, "total": 0, "pct": 0.0})
        
    if perf_cand:
        data.update({
            "nps": int(perf_cand.group(1)),
            "depth": float(perf_cand.group(4))
        })
    if perf_base:
        data.update({
            "base_nps": int(perf_base.group(1)),
            "base_depth": float(perf_base.group(4))
        })
        
    print(f"\n--> {name}: Score {data.get('points')}/{data.get('total')} ({data.get('pct')}%) | {data.get('elo'):+.1f}±{data.get('error')} Elo | Depth: {data.get('depth')} vs {data.get('base_depth')} | NPS: {data.get('nps'):,}", flush=True)
    return data

def main():
    parser = argparse.ArgumentParser(description="Run Round 3 Search Optimizations Campaign")
    parser.add_argument("--games", type=int, default=200, help="Total games per match (default: 200)")
    parser.add_argument("--movetime", type=int, default=100, help="Movetime ms (default: 100)")
    parser.add_argument("--concurrency", type=int, default=10, help="Concurrency workers (default: 10)")
    parser.add_argument("--candidate", type=str, default="", help="Run only specific candidate")
    args = parser.parse_args()
    
    cands_to_run = [c for c in CANDIDATES if not args.candidate or c[0] == args.candidate]
    all_results = []
    results_file = OUT_DIR / "campaign_results.json"
    if results_file.is_file():
        try:
            all_results = json.loads(results_file.read_text(encoding="utf-8"))
        except Exception:
            all_results = []
            
    print(f"Launching Round 3 Search Optimization Campaign:")
    print(f"  Total Candidates: {len(cands_to_run)}")
    print(f"  Match Format:     {args.games} games each @ {args.movetime}ms/move")
    print(f"  Opponent Engine:  v334_main ({BASELINE_EXE})")
    print(f"  Concurrency:      {args.concurrency} workers strictly\n", flush=True)
    
    for name, desc in cands_to_run:
        result = run_candidate(name, desc, args.games, args.movetime, args.concurrency)
        all_results = [r for r in all_results if r.get("name") != name]
        all_results.append(result)
        results_file.write_text(json.dumps(all_results, indent=2), encoding="utf-8")
        
    print("\n" + "="*85, flush=True)
    print(" ROUND 3 CAMPAIGN FINISHED — FINAL LEADERBOARD", flush=True)
    print("="*85, flush=True)
    print(f"{'Experiment':<28} | {'Score':<10} | {'Elo H2H':<15} | {'Depth':<12} | {'NPS':<10}", flush=True)
    print("-" * 85, flush=True)
    for r in sorted(all_results, key=lambda x: x.get("elo", -999), reverse=True):
        print(f"{r['name']:<28} | {r.get('points',0):.1f}/{r.get('total',0)} ({r.get('pct',0)}%) | {r.get('elo',0):+6.1f} ± {r.get('error',0):<5} | {r.get('depth',0):<5.1f} vs {r.get('base_depth',0):<4.1f} | {r.get('nps',0):,}", flush=True)
    print("="*85, flush=True)

if __name__ == "__main__":
    main()
