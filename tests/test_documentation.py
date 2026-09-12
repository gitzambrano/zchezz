"""Guard maintained docs and source comments against stale engine defaults."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

MAINTAINED = [ROOT / "Readme.md", *sorted((ROOT / "docs").glob("*.md")), ROOT / "engine/build/termux.md"]


def test_key_docs_name_supported_profiles():
    for rel in ("AGENTS.md", "CLAUDE.md", "Readme.md", "docs/architecture.md", "docs/nnue.md", "docs/repository-layout.md"):
        text = (ROOT / rel).read_text(encoding="utf-8")
        assert "v325" in text, rel
        assert "v326" in text, rel
        assert "v500" in text, rel


def test_maintained_docs_do_not_present_removed_v4_as_current():
    forbidden = ("ENGINE=v403", "zchezz_v402/", "candidate/baseline pair is v403/v402", "default: `v402`")
    for path in MAINTAINED:
        text = path.read_text(encoding="utf-8")
        for needle in forbidden:
            assert needle not in text, f"{path.relative_to(ROOT)}: {needle}"


def test_nnu3_docs_distinguish_file_and_runtime_width():
    text = (ROOT / "docs/nnue.md").read_text(encoding="utf-8")
    assert "64" in text
    assert "50 live + 2 zero padding" in text
    assert "426,864" in text


def test_v500_nnue_source_comments_match_compact_architecture():
    text = (ROOT / "engine/c/zchezz_v500/nnue.c").read_text(encoding="utf-8")
    for stale in ("relu1[1024]", "[stm 512 | opp 512]", "L2: 1024 -> 32", "[2560][512]", "[32][1024]"):
        assert stale not in text, stale
    for current in ("2560 -> 48", "[stm 48 | opp 48] = 96", "96 -> 20"):
        assert current in text, current


def test_strength_docs_keep_nodes_separate_from_movetime():
    text = (ROOT / "docs/regression-testing.md").read_text(encoding="utf-8").lower()
    assert "go nodes" in text
    assert "not equivalent" in text
    assert "200 ms" in text


def test_native_launchers_default_to_v326():
    bat = (ROOT / "engine/build/build_native.bat").read_text(encoding="utf-8")
    termux = (ROOT / "engine/build/build_termux.sh").read_text(encoding="utf-8")
    assert "set ENGINE=v326" in bat
    assert 'VERSION="${1:-v326}"' in termux
