"""Protect cross-agent repository contracts."""
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def _body(path): return "\n".join(path.read_text(encoding="utf-8").splitlines()[1:]).strip()
def test_files_and_bodies_match():
    assert (ROOT/"AGENTS.md").is_file() and (ROOT/"CLAUDE.md").is_file()
    assert _body(ROOT/"AGENTS.md") == _body(ROOT/"CLAUDE.md")
def test_dual_family_contract_is_explicit():
    text=(ROOT/"AGENTS.md").read_text(encoding="utf-8")
    for token in ("`v325`","`v500`","engine/ACTIVE_ENGINE","GitHub Actions","latest.pt"): assert token in text
