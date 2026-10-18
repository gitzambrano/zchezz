import copy
import pytest

from colab.monitoring import evaluate, merge_report


def sample(size=10, endpoint="vm-a"):
    return {"status": "connected", "identity": endpoint, "busy": True,
            "artifacts": [{"path": "/content/drive/data/positions.jsonl", "size": size, "modified": "2026-10-18T00:00:00Z"}],
            "checkpoints": []}


def test_no_progress_eventually_becomes_stalled():
    first = evaluate(sample(), {}, now=100, stall_seconds=60)
    assert first["status"] == "observing"
    assert evaluate(sample(), first, now=161, stall_seconds=60)["status"] == "stalled"


def test_new_bytes_reset_stall_timer():
    first = evaluate(sample(), {}, now=100, stall_seconds=60)
    result = evaluate(sample(20), first, now=180, stall_seconds=60)
    assert result["status"] == "progressing"
    assert result["last_progress_at"] == 180


def test_runtime_replacement_starts_a_new_observation_window():
    old = evaluate(sample(), {}, now=100, stall_seconds=60)
    result = evaluate(sample(endpoint="vm-b"), old, now=1000, stall_seconds=60)
    assert result["status"] == "observing"


def test_an_error_does_not_erase_the_last_progress():
    old = evaluate(sample(), {}, now=100, stall_seconds=60)
    broken = evaluate({"status": "auth_required"}, old, now=200, stall_seconds=60)
    assert broken["status"] == "auth_required"
    assert broken["last_progress_at"] == 100


def test_no_artifacts_cannot_confirm_progress():
    value = sample()
    value["artifacts"] = []
    assert evaluate(value, {}, now=100, stall_seconds=60)["status"] == "progress_unknown"


def test_monitor_does_not_change_its_inputs():
    value = sample()
    previous = {"unrelated": True}
    expected = copy.deepcopy((value, previous))
    evaluate(value, previous, now=100, stall_seconds=60)
    assert (value, previous) == expected


def test_selected_workers_do_not_erase_other_workers():
    result = merge_report({"workers": {"2": {"status": "old"}}}, {"1": {"status": "new"}}, now=100, backend="cli")
    assert result["workers"]["2"]["status"] == "old"


def test_stall_threshold_must_be_positive():
    with pytest.raises(ValueError):
        evaluate(sample(), {}, now=100, stall_seconds=0)
