"""Guard the maintained documentation against stale engine-family defaults."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

MAINTAINED = [ROOT / "Readme.md", *sorted((ROOT / "docs").glob("*.md")), ROOT / "engine/build/termux.md"]


def test_key_docs_name_supported_profiles():
    for rel in ("AGENTS.md", "CLAUDE.md", "Readme.md", "docs/architecture.md", "docs/nnue.md", "docs/repository-layout.md"):
        text = (ROOT / rel).read_text(encoding="utf-8")
        assert "v325" in text, rel
        assert "v500" in text, rel


def test_maintained_docs_do_not_present_removed_v4_as_current():
    forbidden = ("ENGINE=v403", "zchezz_v402/", "candidate/baseline pair is v403/v402", "default: `v402`")
    for path in MAINTAINED:
        text = path.read_text(encoding="utf-8")
        for needle in forbidden:
            assert needle not in text, f"{path.relative_to(ROOT)}: {needle}"


def test_nnu3_docs_distinguish_file_and_runtime_width():
    text = (ROOT / "docs/nnue.md").read_text(encoding="utf-8")
    assert "H2 on disk" not in text or "64" in text
    assert "50 live + 2 zero padding" in text
    assert "426,864" in text


def test_strength_docs_keep_nodes_separate_from_movetime():
    text = (ROOT / "docs/regression-testing.md").read_text(encoding="utf-8").lower()
    assert "go nodes" in text
    assert "not equivalent" in text
    assert "200 ms" in text


def test_windows_native_launcher_defaults_to_v325():
    text = (ROOT / "engine/build/build_native.bat").read_text(encoding="utf-8")
    assert "set ENGINE=v325" in text
