import importlib
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]


def test_colab_layout_has_the_common_transport_and_runtime_directories():
    layout = json.loads((ROOT / "colab/layout.json").read_text(encoding="utf-8"))
    for directory in ("cli", "playwright", "playwright/diagnostics", "remote", "notebooks"):
        assert directory in layout["directories"]
        assert (ROOT / "colab" / directory).is_dir()


def test_compatibility_entry_points_have_one_canonical_implementation():
    layout = json.loads((ROOT / "colab/layout.json").read_text(encoding="utf-8"))
    for old, canonical in layout["compatibility_entry_points"].items():
        wrapper, target = ROOT / old, ROOT / canonical
        assert wrapper.is_file() and target.is_file()
        source = wrapper.read_text(encoding="utf-8")
        assert "redirect(" in source or 'exec bash "${SCRIPT_DIR}/remote/' in source
        assert len(source.splitlines()) < 20


def test_browser_diagnostics_do_not_remain_in_the_public_transport_root():
    root = ROOT / "colab/playwright"
    assert not list(root.glob("test_*.py"))
    assert not list(root.glob("scratch_*.py"))
    assert (root / "diagnostics/README.md").exists()


def test_repository_audit_has_a_non_mutating_inspection_mode():
    result = subprocess.run([sys.executable, "tools/audit_repository.py", "--show-config"],
                            cwd=ROOT, text=True, capture_output=True, timeout=10)
    assert result.returncode == 0, result.stderr
    assert "max_file_bytes" in result.stdout


def test_legacy_browser_imports_resolve_after_diagnostic_moves():
    legacy = importlib.import_module("colab.inspect_workers")
    assert Path(legacy.__file__).parent.name == "diagnostics"
