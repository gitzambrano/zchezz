"""Safe, offline Pages publication contracts."""
from __future__ import annotations

from pathlib import Path

import pytest

from tools.publish_web import BUNDLE, PUBLISHED, sync_page, validate_bundle


def _fake_valid_bundle() -> bytes:
    return (b"_WASM_B64 _WEIGHTS_B64 ZchezzEngine OPENING_BOOK " + b"x" * 101_000)


def test_published_index_is_identical_to_last_committed_v335_bundle():
    assert BUNDLE.exists() and PUBLISHED.exists()
    assert PUBLISHED.read_bytes() == BUNDLE.read_bytes()


def test_atomic_sync_and_idempotence(tmp_path: Path):
    candidate = tmp_path / "bundle.html"
    index = tmp_path / "index.html"
    candidate.write_bytes(_fake_valid_bundle())
    assert sync_page(candidate, index, write=True)
    assert index.read_bytes() == candidate.read_bytes()
    assert sync_page(candidate, index, write=True) is False
    assert not list(tmp_path.glob(".pages-*.html"))


def test_check_does_not_mutate_or_approve_stale_index(tmp_path: Path):
    candidate = tmp_path / "bundle.html"
    index = tmp_path / "index.html"
    candidate.write_bytes(_fake_valid_bundle())
    index.write_bytes(b"old")
    with pytest.raises(ValueError, match="differs"):
        sync_page(candidate, index, write=False)
    assert index.read_bytes() == b"old"


def test_refuse_truncated_or_non_wasm_payload(tmp_path: Path):
    with pytest.raises(ValueError, match="small"):
        validate_bundle(b"<html>tiny</html>")
    with pytest.raises(ValueError, match="marker"):
        validate_bundle(b"x" * 101_000)
