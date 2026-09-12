"""Executable repository conventions that must stay small and explicit."""
from __future__ import annotations
import re,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]; sys.path.insert(0,str(ROOT/"utils"))
from engine_profiles import DEFAULT_PROFILE,PROFILES

def test_supported_profiles_and_default():
    assert DEFAULT_PROFILE=="v326"; assert set(PROFILES)=={"v325","v326","v500"}; assert (ROOT/"engine/ACTIVE_ENGINE").read_text(encoding="utf-8").strip()=="v326"
    for p in PROFILES.values(): assert p.engine_dir.is_dir() and p.weights.is_file()
def test_no_v4_engine_tree(): assert not list((ROOT/"engine/c").glob("zchezz_v4*"))
def test_makefile_defaults_are_safe():
    text=(ROOT/"engine/build/Makefile").read_text(encoding="utf-8"); assert re.search(r"^ENGINE\s*\?=\s*v326\b",text,re.M); assert re.search(r"^TOOLS_ENGINE\s*\?=\s*v500\b",text,re.M); assert "-DNO_TABLEBASES" in text
def test_actions_are_minimal_read_only():
    wf=ROOT/".github/workflows"; files=sorted(p.name for p in wf.glob("*.yml"))+sorted(p.name for p in wf.glob("*.yaml")); assert files==["ci.yml"]
    text=(wf/"ci.yml").read_text(encoding="utf-8").lower(); assert "contents: read" in text; assert len(text.splitlines())<35
    for bad in ("git push","git commit","create branch","delete branch","upload-artifact","playwright","emsdk","contents: write"): assert bad not in text
def test_cli_helper_is_small_optional_override_only():
    text=(ROOT/"utils/cliconf.py").read_text(encoding="utf-8"); assert len(text.splitlines())<120; assert "--show-config" in text; assert "subprocess" not in text
def test_public_runners_are_thin_and_default_profile_driven():
    for rel in ("tests/run_tests.py","tests/run_selfplay.py","tests/run_tournament.py","tests/run_tournament_quick.py","tests/benchmark.py","train/run.py","train/export.py"):
        text=(ROOT/rel).read_text(encoding="utf-8"); assert len(text.splitlines())<80,rel
    assert "DEFAULT_PROFILE" in (ROOT/"tests/run_selfplay.py").read_text(encoding="utf-8")
