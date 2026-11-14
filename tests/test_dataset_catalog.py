"""Tests for dataset catalog documentation and manifest integrity."""
from __future__ import annotations

import json
from pathlib import Path
import pytest

ROOT = Path(__file__).resolve().parents[1]


def test_datasets_documentation_exists_and_covers_conventions():
    doc_path = ROOT / "docs" / "datasets.md"
    assert doc_path.is_file(), "docs/datasets.md must exist and be tracked"
    text = doc_path.read_text(encoding="utf-8")
    assert "white_relative" in text.lower() or "white-relative" in text.lower()
    for token in ("`cp`", "`result`", "`wdl`", "`target`", "320", "manifest.json"):
        assert token in text, f"Missing token in docs/datasets.md: {token}"


def test_manifest_module_contract():
    import sys
    sys.path.insert(0, str(ROOT))
    from train.labeling.manifest import (
        SCHEMA_VERSION,
        build_manifest,
        validate_manifest,
        scan_dataset_files,
    )
    assert SCHEMA_VERSION == 1
    sample_manifest = {
        "schema_version": 1,
        "name": "test_dataset",
        "format": "parquet",
        "point_of_view": "white_relative",
        "positions_count": 100,
        "columns": ["fen", "cp", "result"],
        "has_cp": True,
        "has_result": True,
    }
    assert validate_manifest(sample_manifest) is True

    with pytest.raises(ValueError, match="white_relative"):
        bad = dict(sample_manifest, point_of_view="black_relative")
        validate_manifest(bad)


def test_all_local_datasets_have_valid_manifest_and_are_documented():
    import sys
    sys.path.insert(0, str(ROOT))
    from train.labeling.manifest import validate_manifest

    data_dir = ROOT / "data"
    if not data_dir.is_dir():
        pytest.skip("data directory not present locally")

    doc_text = (ROOT / "docs" / "datasets.md").read_text(encoding="utf-8")
    dataset_dirs = [d for d in data_dir.iterdir() if d.is_dir()]
    assert len(dataset_dirs) > 0, "Expected at least one local dataset in data/"

    for d in dataset_dirs:
        manifest_file = d / "manifest.json"
        assert manifest_file.is_file(), f"Dataset directory {d.name} missing manifest.json"
        data = json.loads(manifest_file.read_text(encoding="utf-8"))
        validate_manifest(data)
        assert data["name"] == d.name
        assert data["point_of_view"] == "white_relative"
        assert "played_by" in data
        assert "stage" in data
        assert data["positions_count"] > 0
        assert data["files_count"] > 0
        assert d.name in doc_text, f"Dataset {d.name} not documented in docs/datasets.md"
