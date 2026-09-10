"""Validate test-profile wiring without launching engines."""
from __future__ import annotations
import importlib.util,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
SPEC=importlib.util.spec_from_file_location("zchezz_run_tests",ROOT/"tests"/"run_tests.py"); assert SPEC and SPEC.loader
MODULE=importlib.util.module_from_spec(SPEC); sys.modules[SPEC.name]=MODULE; SPEC.loader.exec_module(MODULE)
def _steps(profile:str): return MODULE.profiles("v500","v325")[profile]
def _step(profile:str,name:str): return next(step for step in _steps(profile) if step.name==name)
def test_smoke_builds_before_black_box_tests():
    names=[s.name for s in _steps("smoke")]; assert names.index("native build")<names.index("perft smoke"); assert names.index("native build")<names.index("UCI smoke")
def test_smoke_perft_is_reduced_depth():
    c=_step("smoke","perft smoke").command; i=c.index("--max-depth"); assert c[i+1]==str(MODULE.SMOKE_PERFT_MAX_DEPTH)
def test_full_has_one_full_perft_and_no_web_checks():
    names=[s.name for s in _steps("full")]; assert names.count("perft full")==1; assert "browser static" not in names; assert "bundle" not in names
def test_web_builds_before_generated_artifact_checks():
    names=[s.name for s in _steps("web")]; assert names.index("bundle")<names.index("browser static"); assert names.index("bundle")<names.index("browser e2e")
def test_regression_uses_selected_candidate_and_baseline():
    c=_step("regression","quick H2H").command; text=" ".join(c); assert "zchezz_v500" in text and "zchezz_v325" in text; assert "--engine-a" in c and "--engine-b" in c and "--threads" in c
def test_release_executes_sanitized_binary_after_build():
    names=[s.name for s in _steps("release")]; assert names.index("ASan+UBSan build")<names.index("ASan+UBSan UCI smoke")
def test_native_profiles_use_platform_make_program(monkeypatch): monkeypatch.setattr(MODULE.os,"name","nt"); assert MODULE.make_program()=="mingw32-make"
def test_skip_is_explicit_for_missing_prerequisite():
    step=MODULE.Step("example",("noop",),when_file="missing.file",skip_reason="example prerequisite"); reason=MODULE.prerequisite_skip(step); assert reason and "missing file" in reason
