from pathlib import Path
import os
import subprocess
import sys

from colab.config import WORKERS
from colab.cli.settings import CONFIG, account_environment, command, session_file
from colab.playwright.monitor import progress_from_text


def test_seven_distinct_accounts_have_notebooks_and_profiles():
    assert list(WORKERS) == list(range(1, 8))
    assert len({w["account"] for w in WORKERS.values()}) == 7
    assert all(w["notebook_url"].startswith("https://colab.research.google.com/drive/") for w in WORKERS.values())


def test_account_environments_do_not_modify_parent_credentials():
    previous = os.environ.get("GOOGLE_APPLICATION_CREDENTIALS")
    first, second = account_environment(1), account_environment(2)
    assert first["GOOGLE_APPLICATION_CREDENTIALS"] != second["GOOGLE_APPLICATION_CREDENTIALS"]
    assert os.environ.get("GOOGLE_APPLICATION_CREDENTIALS") == previous


def test_session_state_is_separate_for_each_account(monkeypatch, tmp_path):
    monkeypatch.setitem(CONFIG, "session_root", tmp_path)
    assert session_file(1) != session_file(2)


def test_playwright_progress_uses_the_latest_observation():
    text = "Generated 20/40 positions\nGenerated 30/40 positions\n"
    assert progress_from_text(text)["current"] == 30
    assert progress_from_text("progresso: 3/250 partidas | 60 posicoes")["current"] == 3
    assert progress_from_text("Epoch 4/100 loss=0.1")["current"] == 4
    assert progress_from_text("[selfplay] games 45/3000 positions 2387")["current"] == 45


def test_public_inspection_modes_do_not_require_cli_dependencies():
    root = Path(__file__).resolve().parents[1]
    for module in ("accounts", "run", "login", "monitor", "recover"):
        result = subprocess.run([sys.executable, "-m", f"colab.cli.{module}", "--show-config"],
                                cwd=root, capture_output=True, text=True, timeout=10)
        assert result.returncode == 0, result.stderr
