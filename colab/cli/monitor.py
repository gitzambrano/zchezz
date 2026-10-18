"""Monitor runtime access and persisted artifacts without browser control."""

import sys as _sys
from pathlib import Path as _Path
_repo_root = _Path(__file__).resolve().parents[2]
if str(_repo_root) not in _sys.path:
    _sys.path.insert(0, str(_repo_root))

import argparse
from concurrent.futures import ThreadPoolExecutor
import time
from pathlib import PurePosixPath

from colab.config import WORKERS
from colab.cli.backend import client, contents, error_status, proxy_request
from colab.cli.settings import CONFIG as CLI_CONFIG
from colab.monitoring import CONFIG as MONITOR_CONFIG, display, evaluate, merge_report, read_report, write_report
from colab.control import file_lease

CONFIG = {**MONITOR_CONFIG, "worker_ids": list(WORKERS), "output": CLI_CONFIG["output"] / "monitor.json", "threads": 5}


def monitored_paths(worker):
    """Select account-specific artifact directories from shared settings."""
    if "monitor_paths" in WORKERS[worker]:
        return WORKERS[worker]["monitor_paths"]
    paths = [WORKERS[worker].get("drive_dir", "/content/drive/MyDrive/zquoridor_data/selfplay_contact_soup_858")]
    if worker in (1, 2):
        paths.insert(0, f"/content/drive/MyDrive/zquoridor_data/wall_drops_v401/worker_{worker}")
    paths.extend([
        "/content/drive/MyDrive/zquoridor_data/selfplay_contact_soup_858",
        "/content/drive/MyDrive/zchezz_data/selfplay_v331",
        "/content/drive/MyDrive/zchezz_data/selfplay_v507",
        "/content/drive/MyDrive/zchezz_data/selfplay_v331_r2",
        "/content/drive/MyDrive/zchezz_data/selfplay_v507_r2",
        "/content/drive/MyDrive/zchezz_checkpoints/v331",
        "/content/drive/MyDrive/zchezz_checkpoints/v507",
    ])
    return list(dict.fromkeys(paths))


def probe(worker):
    """Read kernel state and artifact metadata on each existing VM."""
    record = {"worker_id": worker, "account": WORKERS[worker]["account"], "status": "connected",
              "busy": False, "artifacts": [], "checkpoints": [], "path_errors": []}
    try:
        assignments = client(worker).list_assignments()
        if not assignments:
            record["status"] = "disconnected"
            return record
        record["identity"] = ",".join(sorted(a.endpoint for a in assignments))
        for assignment in assignments:
            kernels = proxy_request(assignment, "GET", "/api/kernels")
            record["busy"] |= any(k.get("execution_state") == "busy" for k in kernels)
            for path in monitored_paths(worker):
                try:
                    model = contents(assignment, path)
                except Exception as error:
                    status = getattr(getattr(error, "response", None), "status_code", None)
                    if status != 404:
                        record["path_errors"].append({"path": path, "status": error_status(error), "error_type": type(error).__name__})
                    continue
                entries = model.get("content") or []
                if model.get("type") != "directory":
                    entries = [model]
                for item in entries:
                    if item.get("type") != "file":
                        continue
                    name = item["name"]
                    if name.startswith("c") and "_shard_" in name and not name.startswith(f"c{worker}_"):
                        continue
                    artifact = {"endpoint": assignment.endpoint, "path": str(PurePosixPath(path) / name),
                                "size": item.get("size"), "modified": item.get("last_modified")}
                    record["artifacts"].append(artifact)
                    if name.endswith((".npz", ".pt", ".bin", ".meta")):
                        record["checkpoints"].append(artifact)
        record["artifacts"].sort(key=lambda item: (item["endpoint"], item["path"]))
        record["checkpoint_status"] = "present_unverified" if record["checkpoints"] else "missing"
        if record["path_errors"] and not record["artifacts"]:
            record["status"] = "artifacts_unreachable"
    except Exception as error:
        record.update(status=error_status(error), error_type=type(error).__name__)
    return record


def run(config):
    """Write separate CLI observations until the operator stops the monitor."""
    if config["interval"] <= 0 or config["stall_seconds"] <= 0:
        raise ValueError("Monitor intervals must be positive.")
    output = config["output"]
    with file_lease(output.with_suffix(".lock")):
        cycle = 0
        while True:
            previous = read_report(output)
            with ThreadPoolExecutor(max_workers=config["threads"]) as pool:
                snapshots = list(pool.map(probe, config["worker_ids"]))
            now = time.time()
            updates = {str(s["worker_id"]): evaluate(s, previous.get("workers", {}).get(str(s["worker_id"]), {}),
                       now=now, stall_seconds=config["stall_seconds"]) for s in snapshots}
            if config.get("recover"):
                from colab.cli.recover import CONFIG as RECOVERY_CONFIG, recovery_allowed, recover
                policy_path = config.get("recovery_spec", RECOVERY_CONFIG["spec"])
                policies = read_report(policy_path)
                for worker, record in updates.items():
                    spec = policies.get(worker)
                    if recovery_allowed(record, spec, now):
                        record["last_recovery_at"] = now
                        try:
                            record["recovery_result"] = recover(int(worker), spec)
                            if record["recovery_result"] in ("started", "exited", "unconfirmed"):
                                record["recovery_attempts"] = record.get("recovery_attempts", 0) + 1
                        except Exception as error:
                            record["recovery_result"] = type(error).__name__
                            record["recovery_attempts"] = record.get("recovery_attempts", 0) + 1
            report = merge_report(previous, updates, now=now, backend="cli")
            write_report(output, report)
            display(updates)
            cycle += 1
            if config["max_cycles"] and cycle >= config["max_cycles"]:
                return report
            time.sleep(config["interval"])


def main():
    from pathlib import Path
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--worker-ids", nargs="+", type=int, choices=list(WORKERS), default=CONFIG["worker_ids"])
    parser.add_argument("--interval", type=float, default=CONFIG["interval"])
    parser.add_argument("--stall-seconds", type=float, default=CONFIG["stall_seconds"])
    parser.add_argument("--max-cycles", type=int, default=CONFIG["max_cycles"])
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--output", type=Path, default=CONFIG["output"])
    parser.add_argument("--recover", action="store_true")
    parser.add_argument("--recovery-spec", type=Path, default=CLI_CONFIG["output"] / "recovery.json")
    parser.add_argument("--show-config", action="store_true")
    args = parser.parse_args()
    if args.show_config:
        import json
        print(json.dumps(CONFIG, default=str, indent=2))
        return
    config = {**CONFIG, **{key: value for key, value in vars(args).items() if key != "once"}}
    if args.once:
        config["max_cycles"] = 1
    try:
        run(config)
    except KeyboardInterrupt:
        print("Monitor stopped. Remote tasks remain active.")


if __name__ == "__main__":
    main()
