#!/usr/bin/env python3
"""Fresh-process fixed-depth structural comparison for one v3.27 candidate."""
from __future__ import annotations

import argparse
import json
import re
import statistics
import sys
import time
from dataclasses import asdict, dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from helpers.uci_engine import UCIEngine  # noqa: E402

BASELINE = Path("engine/c/zchezz_v326/zchezz_baseline.exe")
CANDIDATE = Path("engine/c/zchezz_v326/zchezz_candidate.exe")
SOURCE = Path("engine/c/zchezz_v326/main.c")
DEPTHS = (8, 10, 12)
HASH_MB = 64
OUTPUT = Path("artifacts/v327-candidate-structure")


@dataclass
class Result:
    engine: str
    depth: int
    position: int
    nodes: int
    bestmove: str
    score: str | None
    elapsed_ms: float


def bench_fens(path: Path) -> list[str]:
    src = path.read_text(encoding="utf-8")
    match = re.search(r"BENCH_FENS\s*\[\s*\]\s*=\s*\{(.*?)\};", src, re.S)
    if not match:
        raise RuntimeError("BENCH_FENS not found")
    items = re.findall(r'"([^"\\]*(?:\\.[^"\\]*)*)"', match.group(1))
    if len(items) != 20:
        raise RuntimeError(f"expected 20 BENCH_FENS, got {len(items)}")
    return items


def configure(engine: UCIEngine) -> None:
    lines = engine.handshake(timeout=20)
    names: set[str] = set()
    for line in lines:
        m = re.match(r"option name (.+?)(?: type |$)", line)
        if m:
            names.add(m.group(1))
    for name, value in (("Threads", 1), ("Hash", HASH_MB), ("MultiPV", 1), ("Ponder", False), ("OwnBook", False)):
        if name in names:
            engine.setoption(name, value)
    engine.send("isready")
    engine.read_until(r"^readyok$", timeout=20)


def run_one(exe: Path, name: str, fen: str, depth: int, pos: int) -> Result:
    engine = UCIEngine(exe.resolve(), cwd=exe.resolve().parent)
    with engine:
        configure(engine)
        started = time.monotonic()
        lines = engine.search(f"position fen {fen}", f"go depth {depth}", timeout=120)
        elapsed_ms = (time.monotonic() - started) * 1000.0
    if any("weights not loaded" in line.lower() for line in engine.stderr):
        raise RuntimeError(f"{name}: NNUE load failure")
    info = next((line for line in reversed(lines) if line.startswith("info ") and " nodes " in line), "")
    nodes_match = re.search(r"\bnodes\s+(\d+)", info)
    score_match = re.search(r"\bscore\s+(cp|mate)\s+(-?\d+)", info)
    best = next((line for line in reversed(lines) if line.startswith("bestmove ")), "").split()
    if not nodes_match or len(best) < 2:
        raise RuntimeError(f"bad result {name} d{depth} p{pos}")
    score = f"{score_match.group(1)} {score_match.group(2)}" if score_match else None
    return Result(name, depth, pos, int(nodes_match.group(1)), best[1], score, elapsed_ms)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--baseline", type=Path, default=BASELINE)
    ap.add_argument("--candidate", type=Path, default=CANDIDATE)
    ap.add_argument("--source", type=Path, default=SOURCE)
    ap.add_argument("--output", type=Path, default=OUTPUT)
    args = ap.parse_args()

    fens = bench_fens(args.source)
    args.output.mkdir(parents=True, exist_ok=True)
    records: list[Result] = []
    summary: dict[str, dict[str, float | int]] = {}

    for depth in DEPTHS:
        baseline: list[Result] = []
        candidate: list[Result] = []
        for pos, fen in enumerate(fens, 1):
            rb = run_one(args.baseline, "baseline", fen, depth, pos)
            rc = run_one(args.candidate, "candidate", fen, depth, pos)
            baseline.append(rb)
            candidate.append(rc)
            records.extend((rb, rc))
        bn = sum(x.nodes for x in baseline)
        cn = sum(x.nodes for x in candidate)
        bt = sum(x.elapsed_ms for x in baseline)
        ct = sum(x.elapsed_ms for x in candidate)
        diffs = sum((x.bestmove, x.score) != (y.bestmove, y.score) for x, y in zip(baseline, candidate))
        summary[str(depth)] = {
            "baseline_nodes": bn,
            "candidate_nodes": cn,
            "node_delta_pct": (cn / bn - 1.0) * 100.0,
            "baseline_elapsed_ms": bt,
            "candidate_elapsed_ms": ct,
            "elapsed_delta_pct": (ct / bt - 1.0) * 100.0,
            "result_diffs": diffs,
            "median_baseline_nodes": statistics.median(x.nodes for x in baseline),
            "median_candidate_nodes": statistics.median(x.nodes for x in candidate),
        }

    lines = [
        "# v3.27 candidate structural screen",
        "",
        "Baseline is promoted v3.26. Fresh process per FEN; Threads 1; Hash 64 MB; 20 BENCH_FENS.",
        "",
        "| Depth | Baseline nodes | Candidate nodes | Node delta | Wall-time delta | bestmove/score diffs |",
        "|---:|---:|---:|---:|---:|---:|",
    ]
    for depth in DEPTHS:
        item = summary[str(depth)]
        lines.append(
            f"| {depth} | {int(item['baseline_nodes']):,} | {int(item['candidate_nodes']):,} | "
            f"{item['node_delta_pct']:+.2f}% | {item['elapsed_delta_pct']:+.2f}% | {item['result_diffs']}/20 |"
        )
    lines += ["", "Fixed-depth node reduction is a structural screen only; strength requires the 200 ms H2H protocol.", ""]
    report = "\n".join(lines)
    print(report)
    (args.output / "summary.md").write_text(report, encoding="utf-8")
    (args.output / "metrics.json").write_text(
        json.dumps({"summary": summary, "records": [asdict(x) for x in records]}, indent=2) + "\n",
        encoding="utf-8",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
