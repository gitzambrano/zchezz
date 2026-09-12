#!/usr/bin/env python3
"""Parity-gated diagnostic for false-negative gives_check hints."""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from helpers.uci_engine import UCIEngine  # noqa: E402

TARGETS = [
    # e4xd5 vacates the e-file and discovers Re1-e8+; d5 is >2 king-distance.
    ("pawn_from_square_discovery", "4k3/8/8/3n4/4P3/8/8/K3R3 w - - 0 1"),
    # d5xe6 e.p. removes the e5 pawn from Ba1-h8 diagonal; e6 is not on it.
    ("en_passant_discovery", "7k/8/8/3Pp3/8/8/8/B6K w - e6 0 1"),
]


def config(u: UCIEngine) -> None:
    lines = u.handshake(timeout=20)
    names = set()
    for line in lines:
        m = re.match(r"option name (.+?)(?: type |$)", line)
        if m:
            names.add(m.group(1))
    for name, value in [("Threads", 1), ("Hash", 64), ("MultiPV", 1),
                        ("Ponder", False), ("OwnBook", False)]:
        if name in names:
            u.setoption(name, value)
    u.send("isready")
    u.read_until(r"^readyok$", timeout=20)


def run(exe: Path, fen: str, depth: int):
    u = UCIEngine(exe.resolve(), cwd=exe.resolve().parent)
    with u:
        config(u)
        lines = u.search(f"position fen {fen}", f"go depth {depth}", timeout=120)
    info = next((x for x in reversed(lines) if x.startswith("info ") and " nodes " in x), "")
    nm = re.search(r"\bnodes\s+(\d+)", info)
    sm = re.search(r"\bscore\s+(cp|mate)\s+(-?\d+)", info)
    bm = next((x for x in reversed(lines) if x.startswith("bestmove ")), "").split()
    if not nm or len(bm) < 2:
        raise RuntimeError(f"bad UCI result for {fen}")
    diag = {"moves": 0, "unprobed": 0, "false_negative": 0,
            "pawn_false_negative": 0, "ep_false_negative": 0}
    for line in u.stderr:
        if line.startswith("[GCHECK_DIAG]"):
            diag = {k: int(v) for k, v in re.findall(r"(\w+)=(\d+)", line)}
    return {
        "nodes": int(nm.group(1)),
        "bestmove": bm[1],
        "score": f"{sm.group(1)} {sm.group(2)}" if sm else None,
        "diag": diag,
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--baseline", type=Path, required=True)
    ap.add_argument("--diagnostic", type=Path, required=True)
    ap.add_argument("--depth", type=int, default=6)
    ap.add_argument("--output", type=Path, required=True)
    args = ap.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)

    rows = []
    for name, fen in TARGETS:
        b = run(args.baseline, fen, args.depth)
        d = run(args.diagnostic, fen, args.depth)
        parity = (b["nodes"], b["bestmove"], b["score"]) == (d["nodes"], d["bestmove"], d["score"])
        if not parity:
            raise RuntimeError(f"diagnostic changed search decisions for {name}: {b} vs {d}")
        rows.append({"name": name, "fen": fen, "baseline": b, "diagnostic": d})

    pawn = rows[0]["diagnostic"]["diag"]
    ep = rows[1]["diagnostic"]["diag"]
    if pawn.get("pawn_false_negative", 0) < 1:
        raise RuntimeError(f"expected pawn-discovery false negative, got {pawn}")
    if ep.get("ep_false_negative", 0) < 1:
        raise RuntimeError(f"expected en-passant false negative, got {ep}")

    lines = [
        "# v3.27 gives-check diagnostic",
        "",
        f"Depth: **{args.depth}**. Baseline/diagnostic search parity is exact.",
        "",
        "| Position | nodes | bestmove | false negatives | pawn FN | EP FN |",
        "|---|---:|---|---:|---:|---:|",
    ]
    for row in rows:
        r = row["diagnostic"]
        dg = r["diag"]
        lines.append(
            f"| {row['name']} | {r['nodes']:,} | {r['bestmove']} | "
            f"{dg.get('false_negative', 0)} | {dg.get('pawn_false_negative', 0)} | "
            f"{dg.get('ep_false_negative', 0)} |"
        )
    report = "\n".join(lines) + "\n"
    print(report)
    (args.output / "summary.md").write_text(report, encoding="utf-8")
    (args.output / "metrics.json").write_text(json.dumps(rows, indent=2) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
