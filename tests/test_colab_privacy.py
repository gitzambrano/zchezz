import json
from pathlib import Path
import runpy
import subprocess

from colab.private import apply_accounts
from colab.privacy_check import private_identifiers, scan


def test_private_account_overrides_do_not_change_workload_settings(monkeypatch, tmp_path):
    path = tmp_path / "accounts.local.json"
    path.write_text(json.dumps({"projects": {"example": {"1": {
        "account": "operator@example.invalid", "profile_dir": "/private/profile",
        "extra_args": "unapproved override"}}}}))
    monkeypatch.setenv("COLAB_ACCOUNTS_FILE", str(path))
    workers = {1: {"account": "placeholder@example.invalid", "extra_args": "original"}}
    apply_accounts(workers, "example")
    assert workers[1]["account"] == "operator@example.invalid"
    assert workers[1]["extra_args"] == "original"


def test_public_registry_contains_only_placeholder_identities(monkeypatch, tmp_path):
    monkeypatch.setenv("COLAB_ACCOUNTS_FILE", str(tmp_path / "missing.json"))
    root = Path(__file__).resolve().parents[1]
    workers = runpy.run_path(str(root / "colab/config.py"))["WORKERS"]
    assert len(workers) == 7
    assert all(w["account"].endswith("@example.invalid") for w in workers.values())
    assert all("NOTEBOOK_ID_" in w["notebook_url"] for w in workers.values())


def test_sensitive_file_classes_are_ignored_even_before_creation():
    root = Path(__file__).resolve().parents[1]
    paths = ["colab/accounts.local.json", "colab/cli/credentials.json", "colab/cli/token.json",
             "colab/cli/sessions.json", "colab/cli/pending.json", "colab/cli/authorization-code.txt",
             "colab/playwright/profiles/account/Default/Cookies", "colab/playwright/launch_colab_1.bat",
             "colab/playwright/trace.har", "colab/playwright/trace.trace.zip", "colab/private/accounts.json",
             "colab/playwright/screenshots/auth.png", ".env", "artifacts/colab/cli/monitor.json"]
    result = subprocess.run(["git", "check-ignore", "--no-index", "--stdin", "-z"], cwd=root,
                            input=("\0".join(paths) + "\0").encode(), capture_output=True, check=False)
    assert set(result.stdout.decode().split("\0")) - {""} == set(paths)


def test_privacy_findings_never_include_the_private_value(tmp_path):
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    value = "operator-private-marker@example.invalid"
    (tmp_path / "config.txt").write_text(value)
    result = scan(tmp_path, {value})
    assert result == [{"file": "config.txt", "categories": ["private_identifier"]}]
    assert value not in json.dumps(result)


def test_private_resource_and_notebook_ids_are_checked():
    data = {"resources": {"sample": "private-resource-value"}, "projects": {"example": {
        "1": {"notebook_url": "https://colab.research.google.com/drive/private-notebook-value"}}}}
    identifiers = private_identifiers(data)
    assert "private-resource-value" in identifiers
    assert "private-notebook-value" in identifiers
