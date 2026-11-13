"""Tests for the declarative experiments framework and specs."""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
import pytest

ROOT = Path(__file__).resolve().parents[1]


def test_experiment_specs_schema():
    specs_dir = ROOT / "experiments" / "specs"
    assert specs_dir.is_dir(), "experiments/specs directory must exist"

    spec_files = list(specs_dir.glob("*.json"))
    assert len(spec_files) >= 3, "Expected at least 3 declarative experiment specs"

    default_spec = specs_dir / "default.json"
    assert default_spec.is_file(), "experiments/specs/default.json must exist"

    for spec_file in spec_files:
        data = json.loads(spec_file.read_text(encoding="utf-8"))
        for req in ("id", "engine_a", "engine_b", "protocol"):
            assert req in data, f"{spec_file.name} missing required key '{req}'"
        proto = data["protocol"]
        assert "movetime_ms" in proto or "nodes" in proto, f"{spec_file.name} protocol must define time control"


def test_run_experiment_show_config():
    runner = ROOT / "experiments" / "run_experiment.py"
    assert runner.is_file()
    res = subprocess.run(
        [sys.executable, str(runner), "--show-config"],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert res.returncode == 0
    assert "Resolved Experiment Specification:" in res.stdout
    assert "v335" in res.stdout


def test_triangular_tournament_show_config():
    triangular = ROOT / "experiments" / "run_triangular_tournament.py"
    assert triangular.is_file()
    res = subprocess.run(
        [sys.executable, str(triangular), "--show-config"],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert res.returncode == 0
    assert "v605" in res.stdout
    assert "v510" in res.stdout
    assert "v335" in res.stdout
