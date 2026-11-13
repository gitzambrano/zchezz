"""
tools/run_round11_screening.py — Screen Round 11 Clean Candidates vs v335.
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
OUT_DIR = ROOT / "artifacts" / "round11_screening"
OUT_DIR.mkdir(parents=True, exist_ok=True)

V335_EXE = ROOT / "engine" / "c" / "zchezz_v335" / "zchezz.exe"
CAND_DIR = ROOT / "experiments" / "round11_clean"

CANDIDATES = [
    ("cand4_pure_lmr", CAND_DIR / "cand4_pure_lmr" / "zchezz.exe", "v335 + Pure LMR History (ch / 768)"),
    ("cand5_clean_d4", CAND_DIR / "cand5_clean_d4" / "zchezz.exe", "v335 + Dual Fast Cutoff depth <= 4"),
    ("cand6_combo_clean", CAND_DIR / "cand6_combo_clean" / "zchezz.exe", "v335 + LMR History + Dual-NNUE Depth 4"),
]

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
    print(f" Config: {games} games @ {movetime}ms/move, Concurrency={concurrency}")
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
    print("=" * 80)
    print(" SCREENING ROUND 11 CLEAN CANDIDATES (100 games each vs v335)")
    print("=" * 80)

    results = []
    for label, exe, desc in CANDIDATES:
        res = run_match(exe, label, V335_EXE, "v335_release", games=100, movetime=100, concurrency=10)
        res["desc"] = desc
        results.append(res)

    results.sort(key=lambda x: x.get("elo_diff", -999.0), reverse=True)
    (OUT_DIR / "screening_results.json").write_text(json.dumps(results, indent=2), encoding="utf-8")

    print("\n" + "=" * 80)
    print(" SCREENING COMPLETE! RANKING:")
    for r in results:
        print(f"  {r['cand']:20s}: {r.get('elo_diff', 0):+.1f} ± {r.get('elo_err', 0):.1f} Elo ({r.get('score_pct', 0):.1f}%) | {r.get('desc')}")
    print("=" * 80)

if __name__ == "__main__":
    main()
