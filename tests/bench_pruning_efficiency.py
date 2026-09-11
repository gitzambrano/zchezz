#!/usr/bin/env python3
"""Aggregate pruning/qsearch counters over the 20 embedded benchmark FENs.

Baseline and diagnostic executables are run in fresh processes at fixed depth.
The diagnostic result is accepted only when nodes, score and bestmove match the
baseline exactly for every position.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import asdict, dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from helpers.uci_engine import UCIEngine  # noqa: E402

BASELINE = Path("engine/c/zchezz_v325/zchezz_baseline.exe")
DIAGNOSTIC = Path("engine/c/zchezz_v325/zchezz_prune_diag.exe")
SOURCE = Path("engine/c/zchezz_v325/main.c")
DEPTH = 12
HASH_MB = 64
OUTPUT = Path("artifacts/pruning-efficiency")
PREFIX = "[PRUNE_DIAG] "


@dataclass
class Record:
    engine: str
    position: int
    nodes: int
    bestmove: str
    score: str | None


def load_fens(path: Path) -> list[str]:
    text = path.read_text(encoding="utf-8")
    match = re.search(r"BENCH_FENS\s*\[\s*\]\s*=\s*\{(.*?)\};", text, re.S)
    if not match:
        raise RuntimeError("BENCH_FENS not found")
    fens = re.findall(r'"([^"\\]*(?:\\.[^"\\]*)*)"', match.group(1))
    if len(fens) != 20:
        raise RuntimeError(f"expected 20 BENCH_FENS, found {len(fens)}")
    return fens


def configure(uci: UCIEngine) -> None:
    lines = uci.handshake(timeout=20.0)
    names: set[str] = set()
    for line in lines:
        m = re.match(r"option name (.+?)(?: type |$)", line)
        if m:
            names.add(m.group(1))
    for name, value in (("Threads", 1), ("Hash", HASH_MB), ("MultiPV", 1),
                        ("Ponder", False), ("OwnBook", False)):
        if name in names:
            uci.setoption(name, value)
    uci.send("isready")
    uci.read_until(r"^readyok$", timeout=20.0)


def parse_result(lines: list[str], engine: str, pos: int) -> Record:
    best_line = next((x for x in reversed(lines) if x.startswith("bestmove ")), "")
    bestmove = best_line.split()[1] if len(best_line.split()) >= 2 else "?"
    info = next((x for x in reversed(lines) if x.startswith("info ") and " nodes " in x), "")
    nm = re.search(r"\bnodes\s+(\d+)", info)
    if not nm:
        raise RuntimeError(f"{engine} p{pos}: no nodes in final info")
    sm = re.search(r"\bscore\s+(cp|mate)\s+(-?\d+)", info)
    score = f"{sm.group(1)} {sm.group(2)}" if sm else None
    return Record(engine, pos, int(nm.group(1)), bestmove, score)


def one(exe: Path, name: str, fen: str, depth: int, pos: int) -> tuple[Record, dict[str, int] | None]:
    uci = UCIEngine(exe.resolve(), cwd=exe.resolve().parent)
    with uci:
        configure(uci)
        lines = uci.search(f"position fen {fen}", f"go depth {depth}", timeout=120.0)
    if any("weights not loaded" in x.lower() for x in uci.stderr):
        raise RuntimeError(f"{name}: NNUE load failure")
    counters = None
    if name == "diagnostic":
        line = next((x for x in reversed(uci.stderr) if x.startswith(PREFIX)), None)
        if line is None:
            raise RuntimeError(f"diagnostic p{pos}: no PRUNE_DIAG line")
        counters = {k: int(v) for k, v in re.findall(r"([a-zA-Z0-9_]+)=(\d+)", line)}
    return parse_result(lines, name, pos), counters


def pct(n: int, d: int) -> float:
    return 100.0 * n / d if d else 0.0


def make_report(c: dict[str, int]) -> str:
    main_gen = c.get("main_caps_generated", 0) + c.get("main_quiets_generated", 0)
    main_searched = c.get("main_caps_searched", 0) + c.get("main_quiets_searched", 0)
    qgen = c.get("q_caps_generated", 0)
    qsearch = c.get("q_caps_searched", 0)
    return "\n".join([
        "# v3.26 pruning-effectiveness diagnostic",
        "",
        f"Exact baseline/diagnostic parity at fixed depth **{DEPTH}** across 20 BENCH_FENS.",
        "",
        "## Forward-pruning node exits",
        "",
        f"- Razoring: {c.get('razor_cutoffs', 0):,} / {c.get('razor_attempts', 0):,} attempts ({pct(c.get('razor_cutoffs',0), c.get('razor_attempts',0)):.2f}%)",
        f"- Reverse futility: {c.get('rfp_cutoffs', 0):,} / {c.get('rfp_attempts', 0):,} ({pct(c.get('rfp_cutoffs',0), c.get('rfp_attempts',0)):.2f}%)",
        f"- Null move: {c.get('nmp_cutoffs', 0):,} / {c.get('nmp_attempts', 0):,} ({pct(c.get('nmp_cutoffs',0), c.get('nmp_attempts',0)):.2f}%)",
        f"- ProbCut: {c.get('probcut_cutoffs', 0):,} cutoffs / {c.get('probcut_attempts', 0):,} eligible nodes; {c.get('probcut_moves',0):,} captures tested, {c.get('probcut_qhits',0):,} qsearch verifies",
        f"- IIR applications: {c.get('iir_applied', 0):,}",
        f"- Singular: {c.get('singular_extensions',0):,} extensions and {c.get('singular_multicuts',0):,} multi-cuts / {c.get('singular_attempts',0):,} attempts",
        "",
        "## Move-loop selectivity",
        "",
        f"- generated main-search moves (captures+quiets): {main_gen:,}",
        f"- actually searched captures+quiets: {main_searched:,} ({pct(main_searched, main_gen):.2f}% of generated; legality/TT duplicates also account for part of the difference)",
        f"- LMP pruned quiets: {c.get('lmp_pruned',0):,}",
        f"- history-pruned quiets: {c.get('history_pruned',0):,}",
        f"- quiet SEE-pruned: {c.get('quiet_see_pruned',0):,}",
        f"- quiet futility-pruned after make: {c.get('quiet_futility_pruned',0):,}",
        f"- capture SEE-pruned: {c.get('capture_see_pruned',0):,}",
        "",
        "## Quiescence selectivity",
        "",
        f"- stand-pat cutoffs: {c.get('q_standpat_cutoffs',0):,}",
        f"- whole-node delta cutoffs: {c.get('q_whole_delta_cutoffs',0):,}",
        f"- captures/promotions generated: {qgen:,}",
        f"- SEE-pruned before search: {c.get('q_see_pruned',0):,}",
        f"- per-move delta-pruned: {c.get('q_delta_pruned',0):,}",
        f"- captures actually searched: {qsearch:,} ({pct(qsearch, qgen):.2f}% of generated)",
        f"- searched capture beta cutoffs: {c.get('q_capture_cutoffs',0):,}",
        "",
    ])


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--baseline", type=Path, default=BASELINE)
    ap.add_argument("--diagnostic", type=Path, default=DIAGNOSTIC)
    ap.add_argument("--source", type=Path, default=SOURCE)
    ap.add_argument("--depth", type=int, default=DEPTH)
    ap.add_argument("--output", type=Path, default=OUTPUT)
    args = ap.parse_args()
    for p in (args.baseline, args.diagnostic, args.source):
        if not p.exists():
            raise FileNotFoundError(p)
    args.output.mkdir(parents=True, exist_ok=True)
    totals: dict[str, int] = {}
    records: list[Record] = []
    for idx, fen in enumerate(load_fens(args.source), 1):
        b, _ = one(args.baseline, "baseline", fen, args.depth, idx)
        d, metrics = one(args.diagnostic, "diagnostic", fen, args.depth, idx)
        records.extend((b, d))
        if (b.nodes, b.bestmove, b.score) != (d.nodes, d.bestmove, d.score):
            raise RuntimeError(f"parity mismatch p{idx}: baseline={b}, diagnostic={d}")
        assert metrics is not None
        for k, v in metrics.items():
            totals[k] = totals.get(k, 0) + v
    report = make_report(totals)
    payload = {"depth": args.depth, "hash_mb": HASH_MB, "metrics": totals,
               "records": [asdict(r) for r in records]}
    (args.output / "metrics.json").write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    (args.output / "summary.md").write_text(report + "\n", encoding="utf-8")
    print(report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
