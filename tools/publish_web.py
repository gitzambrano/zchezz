#!/usr/bin/env python3
"""Validate and synchronize the default v335 WASM bundle with Pages index.html.

The browser E2E gate belongs to the caller and must pass before --mode sync.
This tool edits only index.html; it never commits, pushes, or changes profiles.
"""
from __future__ import annotations

import argparse
import hashlib
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "utils"))
from engine_profiles import DEFAULT_PROFILE  # noqa: E402

PUBLISHED = ROOT / "index.html"
BUNDLE = ROOT / "engine" / "c" / f"zchezz_{DEFAULT_PROFILE}" / "zchezz_bundle.html"


def validate_bundle(data: bytes) -> None:
    if len(data) < 100_000:
        raise ValueError("WASM bundle is missing or suspiciously small")
    # Both payloads are base64-encoded by the shared bundler.
    for marker in (b"_WASM_B64", b"_WEIGHTS_B64", b"ZchezzEngine", b"OPENING_BOOK"):
        if marker not in data:
            raise ValueError(f"WASM bundle lacks required marker {marker!r}")


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sync_page(bundle: Path, index: Path, *, write: bool) -> bool:
    payload = bundle.read_bytes()
    validate_bundle(payload)
    existing = index.read_bytes() if index.exists() else b""
    if existing == payload:
        print(f"PAGES_SYNC_OK sha256={digest(payload)} unchanged=1")
        return False
    if not write:
        raise ValueError(f"Pages index differs from {bundle}: current={digest(existing)} expected={digest(payload)}")
    # Atomic replacement in the same directory; only the versioned bundle is the source.
    index.parent.mkdir(parents=True, exist_ok=True)
    fd, tempname = tempfile.mkstemp(prefix=".pages-", suffix=".html", dir=index.parent)
    try:
        with os.fdopen(fd, "wb") as out:
            out.write(payload)
        os.replace(tempname, index)
    finally:
        if os.path.exists(tempname):
            os.unlink(tempname)
    print(f"PAGES_SYNC_OK sha256={digest(payload)} updated=1 destination={index}")
    return True


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--mode", required=True, choices=("check", "sync", "validate"))
    ap.add_argument("--bundle", type=Path, default=BUNDLE)
    ap.add_argument("--index", type=Path, default=PUBLISHED)
    args = ap.parse_args()
    try:
        if args.mode == "validate":
            data = args.bundle.read_bytes()
            validate_bundle(data)
            print(f"PAGES_BUNDLE_VALID sha256={digest(data)} bytes={len(data)}")
        else:
            sync_page(args.bundle, args.index, write=args.mode == "sync")
    except (OSError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
