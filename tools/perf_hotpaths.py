#!/usr/bin/env python3
"""Isolated v335 hot-path A/B study runner; never changes tracked engine files.

One independent candidate per invocation. Uses existing perft and UCI H2H
runners. GitHub-hosted NPS is diagnostic, not promotion evidence.
"""
from __future__ import annotations

import argparse
import json
import re
import shutil
import statistics
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "engine/c/zchezz_v335"
VARIANTS = (
    "lmr_piece", "qs_order", "qs_evasion_tt",
    "fasthead_off", "probcut_off", "prefetch_off",
)
OPENINGS = (
    "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq -",
    "rnbqkbnr/pp1ppppp/8/2p5/4P3/8/PPPP1PPP/RNBQKBNR w KQkq c6",
    "rnbqkbnr/pppp1ppp/4p3/8/4P3/8/PPPP1PPP/RNBQKBNR w KQkq -",
    "rnbqkbnr/ppp1pppp/8/3p4/2PP4/8/PP2PPPP/RNBQKBNR b KQkq c3",
    "r1bqkbnr/pppp1ppp/2n5/1B2p3/4P3/5N2/PPPP1PPP/RNBQK2R b KQkq -",
    "r1bqkbnr/pppp1ppp/2n5/4p3/2B1P3/5N2/PPPP1PPP/RNBQK2R b KQkq -",
    "r1bq1rk1/pp2ppbp/2np1np1/8/3NP3/2N1BP2/PPPQ2PP/R3KB1R w KQ -",
    "r1bq1rk1/ppp1ppbp/2np1np1/8/2PPP3/2N2N2/PP2BPPP/R1BQ1RK1 b - -",
    "r2q1rk1/1pp2ppp/p1np1n2/2b1p1B1/2B1P1b1/P1NP1N2/1PP1QPPP/R4RK1 w - -",
    "r3r1k1/pp2bppp/1qn2n2/3p4/3P4/1BN1PN2/PP3PPP/R2QR1K1 w - -",
)

def replace_one(txt: str, before: str, after: str) -> str:
    count = txt.count(before)
    if count != 1:
        raise RuntimeError(f"expected exactly one patch anchor, saw {count}: {before[:90]!r}")
    return txt.replace(before, after, 1)

def patch_search(txt: str, variant: str) -> str:
    if variant == "lmr_piece":
        return replace_one(txt, "uint8_t p_lmr = b->b[mfr];", "uint8_t p_lmr = b->b[mto];")
    if variant == "qs_order":
        return replace_one(txt,
            "sort_moves(ss, moves, n, b, ply, NULL, ok_sq, -1, -1, -1);",
            "sort_moves(ss, moves, n, b, ply, (qs_tt_move.from || qs_tt_move.to) ? &qs_tt_move : NULL, ok_sq, -1, -1, -1);")
    if variant == "qs_evasion_tt":
        start = txt.index("static int qsearch(")
        end = txt.index("/* ── Alpha-Beta", start)
        part = txt[start:end]
        part = replace_one(part,
            "int best = -99999, legal = 0;",
            "int best = -99999, legal = 0;\n        int original_alpha_qs = alpha;")
        part = replace_one(part,
            "if (alpha >= beta) {\n                return beta;\n            }",
            "if (alpha >= beta) {\n                if (!ss->time_up) tt_store(b->hash, sc, 0, TT_LOWER, &best_move_qs, ply, TT_EVAL_NONE);\n                return beta;\n            }")
        part = replace_one(part,
            "/* Store result for check evasion — only cutoffs worth storing */\n        return best;",
            "/* Cache exact/upper bounds for full, non-aborted check evasion searches. */\n        if (!ss->time_up && (best_move_qs.from || best_move_qs.to))\n            tt_store(b->hash, best, 0, best > original_alpha_qs ? TT_EXACT : TT_UPPER,\n                     &best_move_qs, ply, TT_EVAL_NONE);\n        return best;")
        return txt[:start] + part + txt[end:]
    if variant == "fasthead_off":
        txt = replace_one(txt, "if (fast_val >= beta + 200) return beta;", "if (0 && fast_val >= beta + 200) return beta;")
        txt = replace_one(txt, "if (fast_val - (depth * 90) >= beta + 110) return beta;",
                          "if (0 && fast_val - (depth * 90) >= beta + 110) return beta;")
        # Disable computation, not only the cutoff.
        txt = replace_one(txt, "int fast_val = eval_stm_fast(b);", "int fast_val = 0; /* ablation: no fast evaluation */")
        txt = replace_one(txt, "int fast_val = eval_stm_fast(b);", "int fast_val = 0; /* ablation: no fast evaluation */")
        return txt
    if variant == "probcut_off":
        return replace_one(txt,
            "if (!in_check && !is_pv && depth >= 5 && beta < 18000 && ply > 0) {",
            "if (0 && !in_check && !is_pv && depth >= 5 && beta < 18000 && ply > 0) {")
    if variant == "prefetch_off":
        if txt.count("tt_prefetch(b->hash);") < 3:
            raise RuntimeError("unexpected prefetch call count")
        return txt.replace("tt_prefetch(b->hash);", "/* experiment: TT prefetch disabled */")
    raise ValueError(variant)

def build_engine(destination: Path, variant: str | None) -> Path:
    destination.mkdir(parents=True, exist_ok=True)
    for name in ("main.c", "board.c", "board.h", "search.c", "search.h",
                 "nnue.c", "nnue.h", "syzygy.c", "syzygy.h", "book.c",
                 "book.h", "poly_keys.h", "stdendian.h",
                 "fast_head_weights.h", "nnue_weights.bin", "tbconfig.h"):
        shutil.copy2(SOURCE / name, destination / name)
    if variant:
        file = destination / "search.c"
        file.write_text(patch_search(file.read_text(encoding="utf-8"), variant), encoding="utf-8")
    exe = destination / "zchezz.exe"
    cmd = [
        "gcc", "-O3", "-ffast-math", "-mavx2", "-std=c11", "-D_GNU_SOURCE",
        "-DNO_TABLEBASES", "-DNO_BOOK", "-I", str(destination), "-o", str(exe),
        *[str(destination / name) for name in
          ("main.c", "board.c", "search.c", "nnue.c", "syzygy.c", "book.c")],
        "-lm", "-pthread",
    ]
    print("BUILD", variant or "baseline", flush=True)
    subprocess.run(cmd, check=True, timeout=180)
    return exe

def bench(exe: Path, depth: int) -> dict:
    run = subprocess.run([str(exe)], cwd=exe.parent,
                         input=f"uci\nisready\nbench {depth}\nquit\n",
                         text=True, capture_output=True, timeout=180)
    txt = run.stdout + "\n" + run.stderr
    if run.returncode:
        raise RuntimeError(f"bench failed: {exe}\n{txt[-3000:]}")
    def field(label):
        match = re.search(rf"^{re.escape(label)}\s*:\s*(\d+)", txt, re.M)
        if not match:
            raise RuntimeError(f"missing {label}: {txt[-3000:]}")
        return int(match.group(1))
    return dict(nodes=field("Total nodes"), elapsed_ms=field("Elapsed"),
                nps=field("Nodes/sec"))

def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--variant", choices=VARIANTS, required=True)
    ap.add_argument("--bench-depth", type=int, default=11)
    ap.add_argument("--games", type=int, default=6, help="paired openings (total games = 2x)")
    ap.add_argument("--movetime", type=int, default=200)
    args = ap.parse_args()
    with tempfile.TemporaryDirectory(prefix="zchezz_perf_") as tmp:
        temp = Path(tmp)
        baseline = build_engine(temp / "baseline", None)
        candidate = build_engine(temp / args.variant, args.variant)
        print("PERFT candidate, depth<=3", flush=True)
        subprocess.run([sys.executable, str(ROOT / "tests/test_perft.py"),
                        "--exe", str(candidate), "--max-depth", "3", "--stop-on-fail", "true"],
                       cwd=ROOT, check=True, timeout=180)
        # Alternate A/B/A to expose CPU drift on hosted runners.
        readings = [
            ("baseline", bench(baseline, args.bench_depth)),
            ("candidate", bench(candidate, args.bench_depth)),
            ("baseline", bench(baseline, args.bench_depth)),
        ]
        base_nps = statistics.median(x["nps"] for role, x in readings if role == "baseline")
        cand_nps = readings[1][1]["nps"]
        nps_change = 100.0 * (cand_nps / base_nps - 1.0)
        print("NPS_RESULT=" + json.dumps(dict(variant=args.variant, reads=readings,
              baseline_nps=base_nps, candidate_nps=cand_nps,
              change_pct=round(nps_change, 3))), flush=True)
        openings_dir = temp / "openings"
        openings_dir.mkdir()
        (openings_dir / "perf.epd").write_text("\n".join(OPENINGS) + "\n")
        result_dir = temp / "results"
        cmd = [
            sys.executable, str(ROOT / "tests/run_tournament_quick.py"),
            "--profile", "v335",
            "--engine-a", str(baseline), "--label-a", "v335_baseline",
            "--engine-b", str(candidate), "--label-b", args.variant,
            "--games", str(args.games), "--movetime", str(args.movetime),
            "--concurrency", "1", "--threads", "1", "--max-plies", "160",
            "--openings", str(openings_dir), "--opening-file", "perf.epd",
            "--results-dir", str(result_dir),
            "--no-pgn", "--no-epd", "--no-bin", "--counter-every", "2",
            "--perf",
        ]
        print("SELFPLAY_CMD", " ".join(cmd), flush=True)
        # Stream test output into Actions logs (W/D/L and Elo parser native).
        subprocess.run(cmd, check=True, cwd=ROOT, timeout=1080)
        print("STUDY_COMPLETE=" + json.dumps(dict(variant=args.variant, games=2*args.games,
             movetime_ms=args.movetime, nps_change_pct=round(nps_change, 3))), flush=True)
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
