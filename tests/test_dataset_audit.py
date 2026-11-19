"""Contract tests for train/labeling/audit_datasets.py.

The audit must pass White-relative data and fail data whose cp is relative to
the side to move, for parquet and for .bin shards. These tests build small
synthetic files, so they run without the ignored data/ directory.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "train" / "labeling"))

import audit_datasets as audit  # noqa: E402

# (fen, White-relative cp, White result) — decisive material, both sides to move
ROWS = [
    ("3qk3/8/8/8/8/8/8/4K3 b - - 0 1", -900.0, 0.0),
    ("3qk3/8/8/8/8/8/8/4K3 w - - 0 1", -900.0, 0.0),
    ("4k3/8/8/8/8/8/8/3QK3 b - - 0 1", 900.0, 1.0),
    ("4k3/8/8/8/8/8/8/3QK3 w - - 0 1", 900.0, 1.0),
] * 100


def _parquet(path: Path, rows, stm_relative=False):
    pa = pytest.importorskip("pyarrow")
    pq = pytest.importorskip("pyarrow.parquet")
    cps = [(-c if (stm_relative and f.split()[1] == "b") else c) for f, c, _ in rows]
    pq.write_table(pa.table({"fen": [r[0] for r in rows], "cp": cps, "result": [r[2] for r in rows]}), path)
    return str(path)


def test_white_relative_parquet_passes(tmp_path):
    r = audit.audit_file(_parquet(tmp_path / "ok.parquet", ROWS))
    assert r["problems"] == []


def test_side_to_move_parquet_fails(tmp_path):
    r = audit.audit_file(_parquet(tmp_path / "bad.parquet", ROWS, stm_relative=True))
    assert any("black to move" in p for p in r["problems"])


def test_chess960_and_epd_fens_are_valid(tmp_path):
    rows = [("2nbkr1q/p2p2pp/2pnb3/4rp2/P3P3/1P1P2P1/2N3QP/1RNBKRB1 w FBf -", 10.0, 0.5)]
    r = audit.audit_file(_parquet(tmp_path / "c960.parquet", rows))
    assert r["fen_invalid"] == 0 and r["problems"] == []


def test_missing_cp_with_result_is_a_warning(tmp_path):
    pa = pytest.importorskip("pyarrow")
    pq = pytest.importorskip("pyarrow.parquet")
    p = tmp_path / "rescue.parquet"
    pq.write_table(pa.table({"fen": [r[0] for r in ROWS], "cp": pa.array([None] * len(ROWS), pa.float64()),
                             "result": [r[2] for r in ROWS]}), p)
    r = audit.audit_file(str(p))
    assert r["problems"] == [] and r["warnings"]


def _bin(path: Path, stm_relative_bug: bool):
    """Write a ``.bin`` shard from ROWS through the real ``.bin`` writer.

    ``core.build_bin_records`` expects a White-relative score. With
    ``stm_relative_bug=True`` the score of Black-to-move rows is negated first,
    which reproduces the old UCI runner error, so the audit must reject the file.
    """
    np = pytest.importorskip("numpy")
    chess = pytest.importorskip("chess")
    sys.path.insert(0, str(ROOT / "tests"))
    import _run_selfplay_core as core
    states = []
    for fen, cp_white, _ in ROWS:
        b = chess.Board(fen)
        score = -cp_white if (stm_relative_bug and b.turn == chess.BLACK) else cp_white
        states.append({"fen": fen, "score": int(score), "move": next(iter(b.legal_moves))})
    recs = [core.build_bin_records([s], "white" if res == 1.0 else "black")
            for s, (_, _, res) in zip(states, ROWS)]
    path.write_bytes(b"".join(recs))
    return str(path)


def test_bin_white_relative_passes_and_inverted_fails(tmp_path):
    ok = audit.audit_file(_bin(tmp_path / "ok.bin", False))
    bad = audit.audit_file(_bin(tmp_path / "bad.bin", True))
    assert ok["problems"] == []
    assert any("black to move" in p for p in bad["problems"])


def test_show_config_is_non_destructive():
    res = subprocess.run([sys.executable, str(ROOT / "train" / "labeling" / "audit_datasets.py"), "--show-config"],
                         cwd=str(ROOT), capture_output=True, text=True, timeout=60)
    assert res.returncode == 0, res.stderr
    assert "material_agree_min" in res.stdout
