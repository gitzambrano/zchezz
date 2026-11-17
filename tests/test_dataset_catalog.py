"""Contract tests for dataset manifests and the generated catalog in docs/datasets.md.

The manifests are tracked, so these checks run without the (ignored) data files.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from train.labeling import manifest as mf  # noqa: E402

MANIFESTS = sorted((ROOT / "data").glob("*/manifest.json"))


def test_datasets_doc_covers_conventions():
    text = (ROOT / "docs" / "datasets.md").read_text(encoding="utf-8")
    for token in ("`cp`", "`result`", "`wdl`", "`target`", "320", "manifest.json",
                  "recorded", "owner", "inferred", mf.CATALOG_BEGIN, mf.CATALOG_END):
        assert token in text, f"docs/datasets.md lacks {token}"


@pytest.mark.parametrize("path", MANIFESTS, ids=lambda p: p.parent.name)
def test_tracked_manifest_is_valid(path):
    m = json.loads(path.read_text(encoding="utf-8"))
    mf.validate_manifest(m)
    assert m["name"] == path.parent.name
    assert m["positions_count"] > 0 and m["files_count"] > 0
    for field in mf.PROVENANCE_FIELDS:
        assert field in m["evidence"], f"{m['name']}: no evidence level for {field}"
    for field, lvl in m["evidence"].items():
        if m.get(field) in (None, "unknown"):
            assert lvl in ("unknown", "measured"), f"{m['name']}.{field}: empty value claims {lvl}"


def test_manifests_are_tracked():
    assert MANIFESTS, "expected tracked data/*/manifest.json files"


def test_catalog_matches_manifests():
    expected = mf.render_catalog([json.loads(p.read_text(encoding="utf-8")) for p in MANIFESTS])
    assert mf.catalog_in_doc() == expected.strip(), \
        "docs/datasets.md catalog is stale; run python train/labeling/manifest.py --catalog"


def _parquet(tmp: Path, name: str, rows):
    pa = pytest.importorskip("pyarrow")
    pq = pytest.importorskip("pyarrow.parquet")
    d = tmp / name
    d.mkdir()
    pq.write_table(pa.table({"fen": [r[0] for r in rows], "cp": [r[1] for r in rows],
                             "result": [r[2] for r in rows]}), d / "chunk_0000.parquet")
    return d


def test_refresh_keeps_stronger_evidence(tmp_path):
    fen = "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1"
    d = _parquet(tmp_path, "selfplay_cp_sf50k_res_filter_data20260101", [(fen, 10.0, 1.0), (fen, -5.0, None)])
    mf.write_manifest(d, provenance={"evaluator": "Stockfish 17", "played_by": "v335"}, evidence="recorded")
    m = mf.write_manifest(d)  # plain refresh must not downgrade recorded values
    m = json.loads(m.read_text(encoding="utf-8"))
    assert m["evaluator"] == "Stockfish 17" and m["evidence"]["evaluator"] == "recorded"
    assert m["played_by"] == "v335"
    assert m["eval_budget"] == "50k nodes" and m["evidence"]["eval_budget"] == "inferred"
    assert m["date"] == "2026-01-01"
    assert m["result_rate"] == 0.5
    assert m["result_distribution"] == {"white_wins": 1, "draws": 0, "black_wins": 0, "rows": 2}


def test_inference_never_invents_evaluator(tmp_path):
    fen = "8/8/8/8/8/8/8/K6k w - - 0 1"
    d = _parquet(tmp_path, "selfplay_v507_filter", [(fen, 0.0, 0.5)])
    m = mf.build_manifest(d, previous={})
    assert m["evaluator"] == "unknown" and m["evidence"]["evaluator"] == "unknown"
    assert m["engine_version"] == "v507" and m["evidence"]["engine_version"] == "inferred"


def test_bare_run_is_read_only(tmp_path):
    import subprocess
    before = {p: p.stat().st_mtime_ns for p in MANIFESTS}
    res = subprocess.run([sys.executable, str(ROOT / "train" / "labeling" / "manifest.py")],
                         cwd=str(ROOT), capture_output=True, text=True, timeout=60)
    assert res.returncode == 0, res.stderr
    assert before == {p: p.stat().st_mtime_ns for p in MANIFESTS}
