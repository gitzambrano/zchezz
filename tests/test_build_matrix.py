"""Deterministic contracts for the profile-driven shared build matrix."""
from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "engine" / "build" / "build_matrix.py"

sys.path.insert(0, str(ROOT / "utils"))
from engine_profiles import DEFAULT_PROFILE, PROFILES  # noqa: E402


def _matrix():
    spec = importlib.util.spec_from_file_location("zchezz_build_matrix", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_default_native_build_is_v335():
    result = subprocess.run(
        [sys.executable, str(SCRIPT), "--show-config"],
        cwd=ROOT, text=True, capture_output=True, check=True,
    )
    assert "scope=default" in result.stdout
    assert "target=native" in result.stdout
    assert f"profiles={DEFAULT_PROFILE}" in result.stdout


def test_active_builds_cover_each_lineage_once():
    names = _matrix().selected_profiles("active")
    assert names == ["v335", "v510", "v605"]
    assert {PROFILES[name].network_format for name in names} == {"NNU3", "NNU4", "NNU5"}


def test_supported_builds_use_canonical_registry():
    names = _matrix().selected_profiles("supported")
    assert set(names) == set(PROFILES)
    assert len(names) == len(set(names))
    assert _matrix().selected_profiles("default") == [DEFAULT_PROFILE]


def test_make_defaults_to_native_and_exposes_matrix_targets():
    mk = (ROOT / "engine/build/Makefile").read_text(encoding="utf-8")
    assert ".DEFAULT_GOAL := native" in mk
    assert "native-active:" in mk
    assert "native-supported:" in mk
    assert "bundle-active:" in mk
    local = (ROOT / "engine/c/zchezz_v335/Makefile").read_text(encoding="utf-8")
    assert "$(MAKE) -C ../../build ENGINE=v335" in local
    assert "tbprobe.c" not in local


def test_host_native_and_portable_makefiles_have_distinct_outputs():
    build = ROOT / "engine/build"
    native = (build / "Makefile.native").read_text(encoding="utf-8")
    portable = (build / "Makefile.portable").read_text(encoding="utf-8")
    shared = (build / "Makefile").read_text(encoding="utf-8")
    assert __import__("re").search(r"ARCH_FLAGS\s*\?=\s*-march=native", shared)
    assert "ARCH_FLAGS ?= -march=native" in native
    assert "ARCH_FLAGS :=" in portable
    assert "OUTPUT_SUFFIX := .portable" in portable
    assert "zchezz$(OUTPUT_SUFFIX).exe" in shared
    assert '"--output-suffix=$(OUTPUT_SUFFIX)"' in shared
    for mk, suffix, flag_expected in (("Makefile.native", "zchezz.exe", True), ("Makefile.portable", "zchezz.portable.exe", False)):
        run = subprocess.run(["make", "-C", str(build), "-f", mk, "-n", "-B", "native"],
                             text=True, capture_output=True, check=True)
        assert suffix in run.stdout
        assert ("-march=native" in run.stdout) is flag_expected
