#!/usr/bin/env python3
"""Measure v3.25 search structure and screen stale-generation TT behavior.

Defaults are intentionally useful with no CLI arguments. The benchmark uses the
20 BENCH_FENS embedded in the engine. Fresh-process fixed-depth searches verify
that diagnostic instrumentation is semantically neutral. A second persistent
sequence sends ``ucinewgame`` between FENs to isolate stale-generation TT moves.
"""

from __future__ import annotations

import argparse
import json
import re
import statistics
import sys
from dataclasses import asdict, dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from helpers.uci_engine import UCIEngine  # noqa: E402

BASELINE = Path("engine/c/zchezz_v325/zchezz_baseline.exe")
DIAGNOSTIC = Path("engine/c/zchezz_v325/zchezz_diag.exe")
STALE_MISS = Path("engine/c/zchezz_v325/zchezz_stale_miss.exe")
SOURCE = Path("engine/c/zchezz_v325/main.c")
FRESH_DEPTH = 12
STALE_DEPTH = 11
HASH_MB = 64
OUTPUT = Path("artifacts/search-efficiency")

DIAG_PREFIX = "[SEARCH_DIAG] "


@dataclass
class SearchRecord:
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
    return [bytes(fen, "utf-8").decode("unicode_escape") for fen in fens]


def configure(uci: UCIEngine) -> None:
    lines = uci.handshake(timeout=20.0)
    option_names = set()
    for line in lines:
        match = re.match(r"option name (.+?)(?: type |$)", line)
        if match:
            option_names.add(match.group(1))
    for name, value in (("Threads", 1), ("Hash", HASH_MB), ("MultiPV", 1),
                        ("Ponder", False), ("OwnBook", False)):
        if name in option_names:
            uci.setoption(name, value)
    uci.send("isready")
    uci.read_until(r"^readyok$", timeout=20.0)


def parse_search(lines: list[str], engine: str, position: int) -> SearchRecord:
    best = next((line for line in reversed(lines) if line.startswith("bestmove ")), "")
    bestmove = best.split()[1] if len(best.split()) >= 2 else "?"
    info = next((line for line in reversed(lines) if line.startswith("info ") and " nodes " in line), "")
    nodes_match = re.search(r"\bnodes\s+(\d+)", info)
    if not nodes_match:
        raise RuntimeError(f"{engine} p{position}: final nodes missing: {info!r}")
    score_match = re.search(r"\bscore\s+(cp|mate)\s+(-?\d+)", info)
    score = f"{score_match.group(1)} {score_match.group(2)}" if score_match else None
    return SearchRecord(engine, position, int(nodes_match.group(1)), bestmove, score)


def parse_diag(stderr: tuple[str, ...]) -> dict[str, int]:
    line = next((line for line in reversed(stderr) if line.startswith(DIAG_PREFIX)), None)
    if line is None:
        raise RuntimeError("diagnostic engine produced no SEARCH_DIAG line")
    return {key: int(value) for key, value in re.findall(r"([a-zA-Z0-9_]+)=(\d+)", line)}


def one_fresh(exe: Path, name: str, fen: str, depth: int, position: int) -> tuple[SearchRecord, dict[str, int] | None]:
    uci = UCIEngine(exe.resolve(), cwd=exe.resolve().parent)
    with uci:
        configure(uci)
        lines = uci.search(f"position fen {fen}", f"go depth {depth}", timeout=120.0)
    record = parse_search(lines, name, position)
    diag = parse_diag(uci.stderr) if name == "diagnostic" else None
    if any("weights not loaded" in line.lower() for line in uci.stderr):
        raise RuntimeError(f"{name}: NNUE load failure")
    return record, diag


def fresh_parity(baseline: Path, diagnostic: Path, fens: list[str], depth: int) -> tuple[list[SearchRecord], dict[str, int]]:
    records: list[SearchRecord] = []
    totals: dict[str, int] = {}
    mismatches = 0
    for index, fen in enumerate(fens, 1):
        base, _ = one_fresh(baseline, "baseline", fen, depth, index)
        diag, counters = one_fresh(diagnostic, "diagnostic", fen, depth, index)
        records.extend((base, diag))
        assert counters is not None
        for key, value in counters.items():
            totals[key] = totals.get(key, 0) + value
        if (base.nodes, base.bestmove, base.score) != (diag.nodes, diag.bestmove, diag.score):
            mismatches += 1
            print(f"PARITY MISMATCH p{index}: base={base} diag={diag}")
    if mismatches:
        raise RuntimeError(f"diagnostic instrumentation changed {mismatches} fixed-depth searches")
    return records, totals


def persistent_ucinewgame(exe: Path, name: str, fens: list[str], depth: int) -> list[SearchRecord]:
    records: list[SearchRecord] = []
    with UCIEngine(exe.resolve(), cwd=exe.resolve().parent) as uci:
        configure(uci)
        for index, fen in enumerate(fens, 1):
            if index > 1:
                uci.send("ucinewgame")
                uci.send("isready")
                uci.read_until(r"^readyok$", timeout=20.0)
            lines = uci.search(f"position fen {fen}", f"go depth {depth}", timeout=120.0)
            records.append(parse_search(lines, name, index))
    return records


def ratio(num: int, den: int) -> float:
    return 100.0 * num / den if den else 0.0


def report(diag: dict[str, int], stale_base: list[SearchRecord], stale_miss: list[SearchRecord], depth: int) -> str:
    ab = diag.get("ab_nodes", 0)
    q = diag.get("q_nodes", 0)
    cut = diag.get("beta_cutoffs", 0)
    lmr = diag.get("lmr_applied", 0)
    pvs0 = diag.get("pvs_zero_windows", 0)
    base_nodes = sum(r.nodes for r in stale_base)
    miss_nodes = sum(r.nodes for r in stale_miss)
    result_diffs = sum(
        (a.bestmove, a.score) != (b.bestmove, b.score)
        for a, b in zip(stale_base, stale_miss)
    )
    avg_red = diag.get("lmr_reduction_sum", 0) / lmr if lmr else 0.0
    lines = [
        "# v3.26 search-efficiency diagnostic",
        "",
        f"Fresh fixed-depth instrumentation parity: **exact at depth {FRESH_DEPTH}** across 20 BENCH_FENS.",
        "",
        "## Tree composition",
        "",
        f"- alpha-beta nodes: **{ab:,}**",
        f"- qsearch nodes: **{q:,}** ({ratio(q, ab + q):.2f}% of counted search nodes)",
        f"- current-generation TT hits: **{diag.get('tt_current_hits', 0):,}**",
        f"- stale-generation TT hits: **{diag.get('tt_stale_hits', 0):,}** (fresh-process reference; expected near zero)",
        f"- direct TT score cutoffs: **{diag.get('tt_score_cutoffs', 0):,}**",
        "",
        "## Beta-cutoff ordering",
        "",
        f"- beta cutoffs: **{cut:,}**",
        f"- first legal move: **{diag.get('cutoff_rank_1', 0):,}** ({ratio(diag.get('cutoff_rank_1', 0), cut):.2f}%)",
        f"- rank 2: **{diag.get('cutoff_rank_2', 0):,}** ({ratio(diag.get('cutoff_rank_2', 0), cut):.2f}%)",
        f"- rank 3: **{diag.get('cutoff_rank_3', 0):,}** ({ratio(diag.get('cutoff_rank_3', 0), cut):.2f}%)",
        f"- ranks 4-7: **{diag.get('cutoff_rank_4_7', 0):,}** ({ratio(diag.get('cutoff_rank_4_7', 0), cut):.2f}%)",
        f"- rank 8+: **{diag.get('cutoff_rank_8p', 0):,}** ({ratio(diag.get('cutoff_rank_8p', 0), cut):.2f}%)",
        f"- TT/PV move beta cutoffs: **{diag.get('tt_move_cutoffs', 0):,}** ({ratio(diag.get('tt_move_cutoffs', 0), cut):.2f}%)",
        f"- capture beta cutoffs: **{diag.get('capture_cutoffs', 0):,}**; quiet beta cutoffs: **{diag.get('quiet_cutoffs', 0):,}**",
        "",
        "## LMR / PVS",
        "",
        f"- reduced searches: **{lmr:,}**, average reduction **{avg_red:.2f} plies**",
        f"- LMR fail-high/re-searches: **{diag.get('lmr_researches', 0):,}** ({ratio(diag.get('lmr_researches', 0), lmr):.2f}% of reduced searches)",
        f"- PVS zero-window searches: **{pvs0:,}**",
        f"- PVS full-window re-searches: **{diag.get('pvs_researches', 0):,}** ({ratio(diag.get('pvs_researches', 0), pvs0):.2f}% of zero-window searches)",
        f"- LMR reduction distribution: r1={diag.get('lmr_r1', 0):,}, r2={diag.get('lmr_r2', 0):,}, r3+={diag.get('lmr_r3p', 0):,}",
        "",
        "## Stale-generation TT experiment",
        "",
        f"Persistent process, `ucinewgame` between FENs, fixed depth **{depth}**:",
        f"- baseline move-only stale TT: **{base_nodes:,} nodes**",
        f"- stale generation treated as miss: **{miss_nodes:,} nodes**",
        f"- delta: **{(miss_nodes / base_nodes - 1.0) * 100.0:+.2f}%**",
        f"- bestmove/score differences: **{result_diffs}/20**",
        "",
        "The stale-generation comparison is structural screening, not Elo evidence. Promotion still requires the standard 200 ms H2H protocol.",
        "",
    ]
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline", type=Path, default=BASELINE)
    parser.add_argument("--diagnostic", type=Path, default=DIAGNOSTIC)
    parser.add_argument("--stale-miss", type=Path, default=STALE_MISS)
    parser.add_argument("--source", type=Path, default=SOURCE)
    parser.add_argument("--fresh-depth", type=int, default=FRESH_DEPTH)
    parser.add_argument("--stale-depth", type=int, default=STALE_DEPTH)
    parser.add_argument("--output", type=Path, default=OUTPUT)
    args = parser.parse_args()

    for path in (args.baseline, args.diagnostic, args.stale_miss, args.source):
        if not path.exists():
            raise FileNotFoundError(path)
    fens = load_fens(args.source)
    args.output.mkdir(parents=True, exist_ok=True)

    fresh_records, diag = fresh_parity(args.baseline, args.diagnostic, fens, args.fresh_depth)
    stale_base = persistent_ucinewgame(args.baseline, "baseline-stale", fens, args.stale_depth)
    stale_miss = persistent_ucinewgame(args.stale_miss, "stale-miss", fens, args.stale_depth)

    summary = report(diag, stale_base, stale_miss, args.stale_depth)
    payload = {
        "fresh_depth": args.fresh_depth,
        "stale_depth": args.stale_depth,
        "hash_mb": HASH_MB,
        "diagnostics": diag,
        "fresh_records": [asdict(r) for r in fresh_records],
        "stale_baseline": [asdict(r) for r in stale_base],
        "stale_miss": [asdict(r) for r in stale_miss],
    }
    (args.output / "metrics.json").write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    (args.output / "summary.md").write_text(summary + "\n", encoding="utf-8")
    print(summary)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
