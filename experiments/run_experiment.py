#!/usr/bin/env python3
"""Canonical declarative experiment runner for Zchezz.

Reads a declarative experiment specification (JSON), executes the match
via the canonical UCI tournament harness, calculates Elo metrics with
confidence intervals, and records standardized evidence under artifacts/experiments/<id>/.

Bare execution runs experiments/specs/default.json safely without required arguments.
"""
from __future__ import annotations

import argparse
import datetime
import json
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "utils"))
sys.path.insert(0, str(ROOT / "tests"))

from engine_profiles import DEFAULT_PROFILE, profile, stockfish_executable
from elo_calc import elo_difference


def find_engine_binary(prof_name_or_path: str) -> Path:
    """Resolve an engine executable from a profile name or explicit path."""
    p_path = Path(prof_name_or_path)
    if p_path.is_file():
        return p_path

    try:
        p = profile(prof_name_or_path)
        for name in ("zchezz.exe", "zchezz"):
            candidate = p.engine_dir / name
            if candidate.is_file():
                return candidate
        return p.engine_dir / "zchezz.exe"
    except KeyError:
        if p_path.exists():
            return p_path
        raise FileNotFoundError(f"Engine target '{prof_name_or_path}' not found as profile or binary path")


def load_spec(spec_identifier: str) -> Dict[str, Any]:
    """Load experiment specification from a file path or spec id."""
    candidate_path = Path(spec_identifier)
    if not candidate_path.is_file():
        candidate_path = ROOT / "experiments" / "specs" / f"{spec_identifier}.json"
    if not candidate_path.is_file():
        candidate_path = ROOT / "experiments" / "specs" / spec_identifier
    if not candidate_path.is_file():
        raise FileNotFoundError(f"Experiment specification not found: {spec_identifier}")

    with open(candidate_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    return data


def resolve_engine_target(engine_cfg: Dict[str, Any]) -> Tuple[Path, str, str]:
    """Resolve engine binary path, label, and options string from spec dict."""
    label = engine_cfg.get("label", "engine")
    options_dict = engine_cfg.get("options", {})
    options_str = ",".join(f"{k}={v}" for k, v in options_dict.items())

    if engine_cfg.get("target") == "stockfish":
        sf = stockfish_executable()
        if not sf or not Path(sf).is_file():
            raise FileNotFoundError(
                "Stockfish executable not found. Set ZCHEZZ_STOCKFISH or install under engine/stockfish/."
            )
        return Path(sf), label, options_str

    if "profile" in engine_cfg:
        binary = find_engine_binary(engine_cfg["profile"])
        return binary, label, options_str

    if "path" in engine_cfg:
        binary = find_engine_binary(engine_cfg["path"])
        return binary, label, options_str

    raise ValueError(f"Engine config must specify 'profile', 'path', or target='stockfish': {engine_cfg}")


def get_git_commit() -> str:
    """Return current git commit hash, or 'unknown'."""
    try:
        res = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=str(ROOT),
            capture_output=True,
            text=True,
            timeout=5,
        )
        if res.returncode == 0:
            return res.stdout.strip()
    except Exception:
        pass
    return "unknown"


def parse_pgn_results(pgn_path: Path, label_a: str, label_b: str) -> Tuple[int, int, int]:
    """Parse W/D/L for Engine A from a generated PGN file."""
    if not pgn_path.is_file():
        return 0, 0, 0

    wins = 0
    draws = 0
    losses = 0

    content = pgn_path.read_text(encoding="utf-8", errors="replace")
    games = content.split("[Event ")
    for g in games:
        if not g.strip():
            continue
        white_match = re.search(r'\[White "([^"]+)"\]', g)
        black_match = re.search(r'\[Black "([^"]+)"\]', g)
        result_match = re.search(r'\[Result "([^"]+)"\]', g)

        if not (white_match and black_match and result_match):
            continue

        white = white_match.group(1)
        black = black_match.group(1)
        res = result_match.group(1)

        is_a_white = (white == label_a)
        is_a_black = (black == label_a)

        if res == "1-0":
            if is_a_white:
                wins += 1
            elif is_a_black:
                losses += 1
        elif res == "0-1":
            if is_a_white:
                losses += 1
            elif is_a_black:
                wins += 1
        elif res in ("1/2-1/2", "0.5-0.5"):
            if is_a_white or is_a_black:
                draws += 1

    return wins, draws, losses


def run_experiment(
    spec: Dict[str, Any],
    *,
    dry_run: bool = False,
    results_root: Optional[Path] = None,
) -> Dict[str, Any]:
    """Execute an experiment specification and write standardized artifacts."""
    exp_id = spec.get("id", "experiment")
    protocol = spec.get("protocol", {})
    movetime_ms = protocol.get("movetime_ms", 200)
    threads = protocol.get("threads", 1)
    games = protocol.get("games", 10)
    concurrency = protocol.get("concurrency", 1)
    max_plies = protocol.get("max_plies", 400)
    color_swap = protocol.get("color_swap", True)

    exe_a, label_a, opts_a = resolve_engine_target(spec["engine_a"])
    exe_b, label_b, opts_b = resolve_engine_target(spec["engine_b"])

    if results_root is None:
        results_root = ROOT / "artifacts" / "experiments" / exp_id
    results_root.mkdir(parents=True, exist_ok=True)

    git_commit = get_git_commit()
    timestamp = datetime.datetime.now(datetime.timezone.utc).isoformat()

    print(f"\n{'='*72}")
    print(f" EXPERIMENT: {exp_id}")
    print(f" Description: {spec.get('description', '')}")
    print(f" Engine A (Candidate): {label_a} -> {exe_a}")
    print(f" Engine B (Opponent) : {label_b} -> {exe_b}")
    print(f" Protocol: {games*2 if color_swap else games} games, {movetime_ms}ms, Threads={threads}, Concurrency={concurrency}")
    print(f" Artifacts target: {results_root}")
    print(f"{'='*72}\n")

    if dry_run:
        print("Dry run requested. No games executed.")
        return {"id": exp_id, "status": "dry_run"}

    # Run tournament
    cmd = [
        sys.executable,
        str(ROOT / "tests" / "_run_tournament_quick_core.py"),
        "--engine-a", str(exe_a),
        "--label-a", label_a,
        "--engine-b", str(exe_b),
        "--label-b", label_b,
        "--movetime", str(movetime_ms),
        "--threads", str(threads),
        "--games", str(games),
        "--concurrency", str(concurrency),
        "--max-plies", str(max_plies),
        "--results-dir", str(results_root),
        "--pgn",
    ]
    if color_swap:
        cmd.append("--color-swap")
    else:
        cmd.append("--no-color-swap")
    if opts_b:
        cmd.extend(["--options-b", opts_b])

    run_res = subprocess.run(cmd, cwd=str(ROOT))
    if run_res.returncode != 0:
        print(f"Tournament execution exited with code {run_res.returncode}")

    # Inspect generated PGN
    pgn_files = list(results_root.glob("*.pgn"))
    pgn_file = pgn_files[0] if pgn_files else results_root / "games.pgn"
    wins, draws, losses = parse_pgn_results(pgn_file, label_a, label_b)
    total_games = wins + draws + losses

    score_pct = ((wins + 0.5 * draws) / total_games * 100.0) if total_games > 0 else 0.0
    elo_diff, ci_95, se = elo_difference(wins, draws, losses)

    summary = {
        "experiment_id": exp_id,
        "description": spec.get("description", ""),
        "timestamp": timestamp,
        "git_commit": git_commit,
        "protocol": {
            "movetime_ms": movetime_ms,
            "threads": threads,
            "games_requested": games,
            "color_swap": color_swap,
            "concurrency": concurrency,
            "max_plies": max_plies,
        },
        "engine_a": {
            "label": label_a,
            "binary": str(exe_a.relative_to(ROOT)) if exe_a.is_relative_to(ROOT) else str(exe_a),
            "options": opts_a,
        },
        "engine_b": {
            "label": label_b,
            "binary": str(exe_b.relative_to(ROOT)) if exe_b.is_relative_to(ROOT) else str(exe_b),
            "options": opts_b,
        },
        "results": {
            "games_played": total_games,
            "wins": wins,
            "draws": draws,
            "losses": losses,
            "score_pct": round(score_pct, 2),
            "elo_diff": round(elo_diff, 1) if abs(elo_diff) != float("inf") else str(elo_diff),
            "error_margin_95": round(ci_95, 1) if abs(ci_95) != float("inf") else str(ci_95),
            "standard_error": round(se, 2) if abs(se) != float("inf") else str(se),
        },
    }

    summary_path = results_root / "summary.json"
    summary_path.write_text(json.dumps(summary, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"\nSummary recorded at: {summary_path}")
    print(f"Result: {wins}W / {draws}D / {losses}L ({score_pct:.1f}%) | Elo: {elo_diff:+.1f} ± {ci_95:.1f}")
    return summary


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--spec",
        default="default",
        help="Experiment specification id or JSON file path (default: default)",
    )
    ap.add_argument(
        "--show-config",
        action="store_true",
        help="Print resolved configuration and exit non-destructively",
    )
    ap.add_argument("--movetime", type=int, default=None, help="Override movetime_ms")
    ap.add_argument("--games", type=int, default=None, help="Override games count")
    ap.add_argument("--concurrency", type=int, default=None, help="Override concurrency")
    ap.add_argument("--dry-run", action="store_true", help="Resolve and print steps without running")

    args = ap.parse_args()

    spec = load_spec(args.spec)
    if "protocol" not in spec:
        spec["protocol"] = {}

    if args.movetime is not None:
        spec["protocol"]["movetime_ms"] = args.movetime
    if args.games is not None:
        spec["protocol"]["games"] = args.games
    if args.concurrency is not None:
        spec["protocol"]["concurrency"] = args.concurrency

    if args.show_config:
        exe_a, label_a, opts_a = resolve_engine_target(spec["engine_a"])
        exe_b, label_b, opts_b = resolve_engine_target(spec["engine_b"])
        print("Resolved Experiment Specification:")
        print(f"  ID         : {spec.get('id')}")
        print(f"  Description: {spec.get('description')}")
        print(f"  Engine A   : {label_a} ({exe_a}) {opts_a}")
        print(f"  Engine B   : {label_b} ({exe_b}) {opts_b}")
        print(f"  Protocol   : {spec.get('protocol')}")
        return 0

    run_experiment(spec, dry_run=args.dry_run)
    return 0


if __name__ == "__main__":
    sys.exit(main())
