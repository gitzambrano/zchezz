import ast
import pytest

from colab.cli.recover import recovery_allowed, recovery_code, validate_spec
from colab.control import CONFIG as LOCK_CONFIG, account_lease


def spec():
    return {"command": ["python", "/content/project/resume.py"],
            "process_marker": "resume.py", "checkpoint_path": "/content/drive/MyDrive/data/latest.pt",
            "resumes_checkpoint": True}


def test_recovery_rejects_an_ephemeral_checkpoint():
    value = spec()
    value["checkpoint_path"] = "/tmp/latest.pt"
    with pytest.raises(ValueError):
        validate_spec(value)


def test_recovery_requires_explicit_resume_support():
    value = spec()
    del value["resumes_checkpoint"]
    with pytest.raises(ValueError):
        validate_spec(value)


def test_recovery_does_not_allocate_after_a_disconnect():
    assert not recovery_allowed({"status": "disconnected"}, spec(), 2000)


def test_progressing_jobs_never_trigger_recovery():
    assert not recovery_allowed({"status": "progressing"}, spec(), 2000)


def test_recovery_obeys_the_attempt_limit_and_cooldown():
    assert not recovery_allowed({"status": "stalled", "recovery_attempts": 3}, spec(), 2000)
    assert not recovery_allowed({"status": "stalled", "last_recovery_at": 1900}, spec(), 2000)
    assert recovery_allowed({"status": "stalled"}, spec(), 2000)


def test_command_arguments_cannot_inject_generated_source():
    value = spec()
    value["command"].append("x'\nraise RuntimeError('bad')\n#WORKER")
    source = recovery_code(value, 2)
    ast.parse(source)
    assert "COLAB_RECOVERY_ACTIVE" in source
    assert "SIGTERM" not in source


def test_account_lease_rejects_overlapping_controllers(monkeypatch, tmp_path):
    monkeypatch.setitem(LOCK_CONFIG, "lock_root", tmp_path)
    with account_lease([1], "cli"):
        with pytest.raises(RuntimeError, match="active controller"):
            with account_lease([1], "playwright"):
                pass
        with account_lease([2], "playwright"):
            pass
    with account_lease([1], "cli"):
        pass
