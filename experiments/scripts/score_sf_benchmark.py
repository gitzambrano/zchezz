#!/usr/bin/env python3
import re
from pathlib import Path

def parse_pgn_results(pgn_path: Path, engine_name: str):
    if not pgn_path.is_file():
        return None
    content = pgn_path.read_text(encoding="utf-8", errors="replace")
    matches = re.findall(
        r'\[White "(.*?)"\]\s*\n\[Black "(.*?)"\]\s*\n\[Result "(.*?)"\]',
        content
    )
    if not matches:
        return None

    w, d, l = 0, 0, 0
    for white, black, res in matches:
        if res == "1-0":
            if white == engine_name:
                w += 1
            else:
                l += 1
        elif res == "0-1":
            if white == engine_name:
                l += 1
            else:
                w += 1
        else:
            d += 1

    total = len(matches)
    score = w + 0.5 * d
    pct = (score / total) * 100 if total > 0 else 0
    return {
        "engine": engine_name,
        "total": total,
        "score": score,
        "pct": pct,
        "w": w,
        "d": d,
        "l": l,
    }

def main():
    root = Path(__file__).resolve().parents[1]
    bench_dir = root / "artifacts" / "benchmark_v331_vs_sf"
    if not bench_dir.is_dir():
        print("No benchmark directory found.")
        return

    print("=" * 70)
    print(" LIVE BENCHMARK MONITOR: v331_main & v331_exp vs Stockfish")
    print("=" * 70)

    for pgn_file in sorted(bench_dir.glob("*.pgn")):
        eng = "v331_main" if "main" in pgn_file.stem else "v331_exp"
        res = parse_pgn_results(pgn_file, eng)
        if res:
            print(f"File: {pgn_file.name}")
            print(f"  {res['engine']} vs {pgn_file.stem.split('_vs_')[-1]}: "
                  f"{res['score']:.1f}/{res['total']} ({res['pct']:.1f}%) | "
                  f"W:{res['w']} D:{res['d']} L:{res['l']}")
            print("-" * 70)

if __name__ == "__main__":
    main()
