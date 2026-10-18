"""Evaluate progress without changes to remote tasks."""
import hashlib
import json
from pathlib import Path

CONFIG = {"interval": 60, "stall_seconds": 900, "max_cycles": 0}


def evaluate(snapshot, previous, *, now, stall_seconds):
    """Keep progress history across polling cycles and connection failures."""
    if stall_seconds <= 0:
        raise ValueError("The stall threshold must be positive.")
    result = {**previous, **snapshot, "checked_at": now}
    if snapshot["status"] != "connected":
        return result
    result.pop("error_type", None)
    progress = snapshot.get("progress", {})
    artifacts = snapshot.get("artifacts", [])
    identity = snapshot.get("identity")
    if not artifacts and not progress:
        result["status"] = "progress_unknown" if snapshot.get("busy") else "idle"
        return result
    fingerprint = hashlib.sha256(json.dumps([artifacts, progress], sort_keys=True).encode()).hexdigest()
    new_runtime = previous.get("identity") != identity or "fingerprint" not in previous
    changed = previous.get("fingerprint") != fingerprint
    last_progress = now if new_runtime or changed else previous.get("last_progress_at", now)
    result.update(fingerprint=fingerprint, last_progress_at=last_progress,
                  seconds_without_progress=max(0, now - last_progress))
    if snapshot.get("completed"):
        result["status"] = "completed"
    elif new_runtime:
        result["status"] = "observing"
    elif changed:
        result["status"] = "progressing"
    elif now - last_progress >= stall_seconds:
        result["status"] = "stalled"
    else:
        result["status"] = "observing"
    return result


def merge_report(previous, updates, *, now, backend):
    """Preserve records for workers outside the selected subset."""
    return {"backend": backend, "updated_at": now, "workers": {**previous.get("workers", {}), **updates}}


def read_report(path):
    """Load the last complete monitor report."""
    path = Path(path)
    return json.loads(path.read_text(encoding="utf-8")) if path.is_file() else {}


def write_report(path, report):
    """Replace the report only after the complete JSON is written."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(report, indent=2, ensure_ascii=True), encoding="utf-8")
    temporary.replace(path)


def display(records):
    """Print account state and the latest observed output."""
    for worker, record in records.items():
        files = record.get("artifacts", [])
        size = sum(int(f.get("size") or 0) for f in files)
        checkpoints = len(record.get("checkpoints", []))
        print(f"Worker {worker}: {record['status']} | files={len(files)} | bytes={size} | checkpoints={checkpoints} | {record.get('progress', {})}", flush=True)
