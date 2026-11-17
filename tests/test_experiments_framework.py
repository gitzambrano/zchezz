"""Contract tests for the declarative experiment runner and its specs."""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
RUNNER = ROOT / "experiments" / "run_experiment.py"
SPECS = ROOT / "experiments" / "specs"
sys.path.insert(0, str(ROOT / "experiments"))

import run_experiment as rx  # noqa: E402


def _specs():
    return sorted(SPECS.glob("*.json"))


@pytest.mark.parametrize("path", _specs(), ids=lambda p: p.stem)
def test_spec_is_valid(path):
    spec = json.loads(path.read_text(encoding="utf-8"))
    assert spec["id"] == path.stem, "spec id must equal its file name"
    rx.validate_spec(spec)
    for member in rx.expand(spec):
        proto = rx.protocol_of(member)
        assert proto["movetime_ms"] > 0 or proto["nodes"] > 0
        assert proto["threads"] == 1, "benchmark contract: Threads=1"
        assert proto["concurrency"] == 1, "benchmark contract: one concurrent game"
        assert proto["color_swap"] is True, "benchmark contract: paired openings"


def test_default_spec_exists_and_targets_v335():
    spec = rx.load_spec("default")
    assert spec["engine_a"]["profile"] == "v335"


def test_candidate_patches_exist():
    for path in _specs():
        spec = json.loads(path.read_text(encoding="utf-8"))
        for side in ("engine_a", "engine_b"):
            cand = spec.get(side, {}).get("candidate")
            if cand and cand.get("patch"):
                assert (ROOT / cand["patch"]).is_file(), f"{path.name}: missing {cand['patch']}"


def test_unknown_protocol_key_rejected():
    spec = {"id": "x", "engine_a": {"profile": "v335", "label": "a"},
            "engine_b": {"profile": "v328", "label": "b"}, "protocol": {"movetim_ms": 5}}
    with pytest.raises(ValueError, match="unknown protocol"):
        rx.validate_spec(spec)


def test_pgn_parsing_pairs_and_colors(tmp_path):
    pgn = tmp_path / "g.pgn"
    games = [("A", "B", "1-0", 1), ("B", "A", "1-0", 1), ("A", "B", "1/2-1/2", 2), ("B", "A", "0-1", 2)]
    pgn.write_text("\n\n".join(
        f'[Event "T"]\n[Round "{i}"]\n[White "{w}"]\n[Black "{b}"]\n[Result "{r}"]\n[PairId "{p}"]\n\n1. e4 {r}'
        for i, (w, b, r, p) in enumerate(games, 1)) + "\n", encoding="utf-8")
    parsed = rx.parse_pgn(pgn, "A")
    assert (parsed["wins"], parsed["draws"], parsed["losses"]) == (2, 1, 1)
    assert sorted(parsed["pairs"]) == [(0.5, 1.0), (1.0, 0.0)]


@pytest.mark.parametrize("args", [["--show-config"], ["--list"],
                                  ["--spec", "triangular_active_lineages", "--dry-run"]])
def test_runner_is_non_destructive(args):
    res = subprocess.run([sys.executable, str(RUNNER), *args], cwd=str(ROOT),
                         capture_output=True, text=True, timeout=30)
    assert res.returncode == 0, res.stdout + res.stderr
    assert "v335" in res.stdout
