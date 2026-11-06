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
    "nnue_relu_reuse", "nnue_extcache32",
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

def make_openings(n: int) -> list[str]:
    """Deterministic varied legal FEN positions; 100+ paired openings instead of 10."""
    import chess
    import random
    rng = random.Random(20261104)
    seeds = [
        "e2e4 e7e5 g1f3 b8c6 f1b5 a7a6",
        "e2e4 e7e5 g1f3 b8c6 f1c4 f8c5",
        "e2e4 c7c5 g1f3 d7d6 d2d4 c5d4",
        "e2e4 c7c5 g1f3 b8c6 d2d4 c5d4",
        "e2e4 e7e6 d2d4 d7d5 b1c3 g8f6",
        "e2e4 c7c6 d2d4 d7d5 b1c3 d5e4",
        "d2d4 d7d5 c2c4 e7e6 b1c3 g8f6",
        "d2d4 d7d5 c2c4 c7c6 g1f3 g8f6",
        "d2d4 g8f6 c2c4 e7e6 g1f3 d7d5",
        "d2d4 g8f6 c2c4 g7g6 b1c3 f8g7",
        "c2c4 e7e5 b1c3 g8f6 g1f3 b8c6",
        "g1f3 d7d5 d2d4 g8f6 c2c4 e7e6",
        "e2e4 d7d6 d2d4 g8f6 b1c3 g7g6",
        "e2e4 e7e5 f2f4 e5f4 g1f3 g8f6",
        "d2d4 f7f5 c2c4 g8f6 b1c3 e7e6",
    ]
    openings = set(OPENINGS)
    count = 0
    while len(openings) < n and count < n * 30:
        count += 1
        b = chess.Board()
        for uci in rng.choice(seeds).split():
            mv = chess.Move.from_uci(uci)
            if mv not in b.legal_moves:
                raise RuntimeError(f"illegal curated opening move: {uci}")
            b.push(mv)
        for _ in range(rng.randrange(1, 8)):
            moves = list(b.legal_moves)
            if not moves:
                break
            b.push(rng.choice(moves))
        if not b.is_game_over():
            openings.add(" ".join(b.fen(en_passant="fen").split()[:4]))
    if len(openings) < n:
        raise RuntimeError(f"only generated {len(openings)} unique openings")
    return sorted(openings)


def replace_one(txt: str, before: str, after: str) -> str:
    count = txt.count(before)
    if count != 1:
        raise RuntimeError(f"expected exactly one patch anchor, saw {count}: {before[:90]!r}")
    return txt.replace(before, after, 1)

def patch_nnue_header(txt: str, variant: str) -> str:
    if variant == "nnue_extcache32":
        return replace_one(txt, "#define EXT_CACHE_SLOTS 16", "#define EXT_CACHE_SLOTS 32")
    if variant == "nnue_relu_reuse":
        return replace_one(txt,
            "    int16_t  cache_buf[EXT_CACHE_SLOTS][NN_L1_OUT] __attribute__((aligned(32)));",
            """    int16_t  cache_buf[EXT_CACHE_SLOTS][NN_L1_OUT] __attribute__((aligned(32)));
    /* One per-thread reusable L1 activation buffer: fast head -> full NNUE. */
    uint8_t fast_relu1[NN_L1_OUT] __attribute__((aligned(32)));
    uint64_t fast_relu_hash;
    int fast_relu_stm, fast_relu_ptr;
    uint8_t fast_relu_valid;""")
    raise ValueError(variant)


def patch_nnue(txt: str, variant: str) -> str:
    if variant == "nnue_extcache32":
        return txt
    if variant != "nnue_relu_reuse":
        raise ValueError(variant)

    txt = replace_one(txt,
        "    memset(na->cache_key, 0, sizeof(na->cache_key));",
        "    na->fast_relu_valid = 0;\n    memset(na->cache_key, 0, sizeof(na->cache_key));")
    txt = replace_one(txt,
        "void nnue_push_na(NnueAccum *na, const uint8_t *board, const NNMove *m) {\n    int src",
        "void nnue_push_na(NnueAccum *na, const uint8_t *board, const NNMove *m) {\n    na->fast_relu_valid = 0;\n    int src")
    txt = replace_one(txt,
        "void nnue_pop_na(NnueAccum *na) {\n    int cur",
        "void nnue_pop_na(NnueAccum *na) {\n    na->fast_relu_valid = 0;\n    int cur")

    bb_start = txt.index("int nnue_eval_bb(")
    bb_end = txt.index("#ifdef NNUE_TEST", bb_start)
    bb = txt[bb_start:bb_end]
    bb = replace_one(bb,
        "    int cw[6],cb[6];",
        """    uint8_t *relu1 = na->fast_relu1; /* aligned, per-thread, 256 bytes */
    int reused = na->fast_relu_valid && na->fast_relu_hash == board_hash &&
                 na->fast_relu_stm == stm && na->fast_relu_ptr == na->acc_ptr;
    na->fast_relu_valid = 0;
    if (!reused) {
    int cw[6],cb[6];""")
    bb = replace_one(bb,
        "    uint8_t relu1[NN_L1_OUT] __attribute__((aligned(32)));",
        "    /* Reuse the per-thread relu1 buffer from the fast head if still valid. */")
    bb = replace_one(bb,
        "#endif\n\n    /* Steps 3-6: identical to nnue_eval */",
        "#endif\n    } /* end uncached L1 activation computation */\n\n    /* Steps 3-6: identical to nnue_eval */")
    txt = txt[:bb_start] + bb + txt[bb_end:]

    fast_start = txt.index("int nnue_fast_eval_bb(")
    fast = txt[fast_start:]
    fast = replace_one(fast,
        "    uint8_t relu1[NN_L1_OUT] __attribute__((aligned(32)));",
        "    uint8_t *relu1 = na->fast_relu1; /* aligned, per-thread */")
    fast = replace_one(fast,
        "#endif\n    float cp = (float)dot * FAST_HEAD_INV_SCALE + FAST_HEAD_BIAS;",
        """#endif
    na->fast_relu_hash = board_hash;
    na->fast_relu_stm = stm;
    na->fast_relu_ptr = na->acc_ptr;
    na->fast_relu_valid = 1;
    float cp = (float)dot * FAST_HEAD_INV_SCALE + FAST_HEAD_BIAS;""")
    return txt[:fast_start] + fast


def build_engine(destination: Path, variant: str | None) -> Path:
    destination.mkdir(parents=True, exist_ok=True)
    for name in ("main.c", "board.c", "board.h", "search.c", "search.h",
                 "nnue.c", "nnue.h", "syzygy.c", "syzygy.h", "book.c",
                 "book.h", "poly_keys.h", "stdendian.h",
                 "fast_head_weights.h", "nnue_weights.bin", "tbconfig.h"):
        shutil.copy2(SOURCE / name, destination / name)
    if variant:
        head = destination / "nnue.h"
        head.write_text(patch_nnue_header(head.read_text(encoding="utf-8"), variant), encoding="utf-8")
        file = destination / "nnue.c"
        file.write_text(patch_nnue(file.read_text(encoding="utf-8"), variant), encoding="utf-8")
    exe = destination / "zchezz.exe"
    cmd = [
        "gcc", "-O3", "-ffast-math", "-march=native", "-std=c11", "-D_GNU_SOURCE",
        "-DNO_TABLEBASES", "-DNO_BOOK", "-I", str(destination), "-o", str(exe),
        *[str(destination / name) for name in
          ("main.c", "board.c", "search.c", "nnue.c", "syzygy.c", "book.c")],
        "-lm", "-pthread",
    ]
    print("BUILD", variant or "baseline", "flags=-O3 -ffast-math -march=native", flush=True)
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

def check_nnue_equivalence(baseline: Path, candidate: Path) -> None:
    """Fixed-depth UCI positions must have identical score and best move."""
    import chess
    import chess.engine
    positions = make_openings(24)
    with chess.engine.SimpleEngine.popen_uci(str(baseline), cwd=str(baseline.parent)) as a, chess.engine.SimpleEngine.popen_uci(str(candidate), cwd=str(candidate.parent)) as b:
        a.configure({"Threads": 1, "Hash": 16})
        b.configure({"Threads": 1, "Hash": 16})
        for i, fen4 in enumerate(positions):
            board = chess.Board(fen4 + " 0 1")
            try:
                info_a = a.analyse(board, chess.engine.Limit(depth=7), game=object())
                info_b = b.analyse(board, chess.engine.Limit(depth=7), game=object())
            except Exception as exc:
                raise RuntimeError(f"NNUE equivalence failed to analyze case {i}: {exc}") from exc
            a_key = (info_a["score"].pov(board.turn).score(mate_score=20000),
                     info_a["pv"][0].uci() if info_a.get("pv") else "")
            b_key = (info_b["score"].pov(board.turn).score(mate_score=20000),
                     info_b["pv"][0].uci() if info_b.get("pv") else "")
            if a_key != b_key:
                raise RuntimeError(f"NNUE_EVAL_MISMATCH case={i} fen={fen4} baseline={a_key} candidate={b_key}")
        print(f"NNUE_EQUIVALENCE_PASS={len(positions)} fixed-depth positions", flush=True)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--variant", choices=VARIANTS, required=True)
    ap.add_argument("--bench-depth", type=int, default=11)
    ap.add_argument("--games", type=int, default=6, help="paired openings (total games = 2x)")
    ap.add_argument("--movetime", type=int, default=200)
    ap.add_argument("--concurrency", type=int, default=2)
    ap.add_argument("--max-plies", type=int, default=240)
    ap.add_argument("--opening-count", type=int, default=160)
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
        print("HOST_ARCH=", subprocess.run(["uname", "-m"], capture_output=True, text=True).stdout.strip(), flush=True)
        print("COMPILER=", subprocess.run(["gcc", "--version"], capture_output=True, text=True).stdout.splitlines()[0], flush=True)
        if args.variant == "nnue_relu_reuse":
            check_nnue_equivalence(baseline, candidate)
        openings_dir = temp / "openings"
        openings_dir.mkdir()
        epd_openings = make_openings(args.opening_count)
        (openings_dir / "perf.epd").write_text("\n".join(epd_openings) + "\n")
        print(f"OPENINGS_COUNT={len(epd_openings)}; seeded and legal", flush=True)
        result_dir = temp / "results"
        cmd = [
            sys.executable, str(ROOT / "tests/run_tournament_quick.py"),
            "--profile", "v335",
            "--engine-a", str(baseline), "--label-a", "v335_baseline",
            "--engine-b", str(candidate), "--label-b", args.variant,
            "--games", str(args.games), "--movetime", str(args.movetime),
            "--concurrency", str(args.concurrency), "--threads", "1",
            "--max-plies", str(args.max_plies),
            "--openings", str(openings_dir), "--opening-file", "perf.epd",
            "--results-dir", str(result_dir),
            "--no-pgn", "--no-epd", "--no-bin", "--counter-every", "20",
            "--perf",
        ]
        print("SELFPLAY_CMD", " ".join(cmd), flush=True)
        # Stream test output into Actions logs (W/D/L and Elo parser native).
        subprocess.run(cmd, check=True, cwd=ROOT, timeout=10800)
        print("STUDY_COMPLETE=" + json.dumps(dict(variant=args.variant, games=2*args.games,
             movetime_ms=args.movetime, nps_change_pct=round(nps_change, 3))), flush=True)
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
