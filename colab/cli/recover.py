"""Resume explicitly configured jobs after a checkpoint and process check."""

import sys as _sys
from pathlib import Path as _Path
_repo_root = _Path(__file__).resolve().parents[2]
if str(_repo_root) not in _sys.path:
    _sys.path.insert(0, str(_repo_root))

import argparse
import json
from pathlib import Path

from colab.cli.backend import client
from colab.cli.settings import CONFIG as CLI_CONFIG
from colab.control import account_lease

CONFIG = {"spec": CLI_CONFIG["output"] / "recovery.json", "max_attempts": 3, "cooldown_seconds": 900}


def validate_spec(spec):
    """Require an explicit command and a persistent checkpoint."""
    command = spec.get("command")
    checkpoint = spec.get("checkpoint_path", "")
    marker = spec.get("process_marker", "")
    if not isinstance(command, list) or not command or not all(isinstance(arg, str) and arg for arg in command):
        raise ValueError("The recovery command must be a nonempty list of arguments.")
    if not checkpoint.startswith("/content/drive/MyDrive/") or ".." in Path(checkpoint).parts:
        raise ValueError("The recovery checkpoint must be a file under /content/drive/MyDrive.")
    if not marker or "/" in marker or "\\" in marker or not any(Path(arg).name == marker for arg in command):
        raise ValueError("The process marker must identify an exact command argument.")
    if not spec.get("resumes_checkpoint", False):
        raise ValueError("The command must explicitly declare checkpoint resume support.")
    return spec


def recovery_allowed(record, spec, now):
    """Limit recovery to explicit policies and bounded retries."""
    return bool(spec and record.get("status") in ("stalled", "idle")
                and record.get("recovery_attempts", 0) < CONFIG["max_attempts"]
                and now - record.get("last_recovery_at", 0) >= CONFIG["cooldown_seconds"])


def recovery_code(spec, worker):
    """Build a remote check that never terminates an active process."""
    validate_spec(spec)
    return """import fcntl, json, os, pathlib, subprocess, time
spec = json.loads(SPEC_JSON)
lock = open('/tmp/colab-account-WORKER.lock', 'a+')
try:
    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
except BlockingIOError:
    print('COLAB_RECOVERY_LOCKED')
else:
    active = False
    for entry in pathlib.Path('/proc').iterdir():
        if not entry.name.isdigit():
            continue
        try:
            args = (entry / 'cmdline').read_bytes().split(b'\\0')
            if any(pathlib.PurePosixPath(os.fsdecode(arg)).name == spec['process_marker'] for arg in args):
                active = True
                break
        except (FileNotFoundError, PermissionError, ProcessLookupError):
            pass
    checkpoint = pathlib.Path(spec['checkpoint_path'])
    if active:
        print('COLAB_RECOVERY_ACTIVE')
    elif not checkpoint.is_file() or checkpoint.stat().st_size <= 0:
        print('COLAB_RECOVERY_NO_CHECKPOINT')
    elif not pathlib.Path(spec.get('cwd', '/content')).is_dir():
        print('COLAB_RECOVERY_MISSING_WORKDIR')
    else:
        log = open('/tmp/colab-recovery-WORKER.log', 'ab', buffering=0)
        child = subprocess.Popen(spec['command'], cwd=spec.get('cwd', '/content'), stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
        time.sleep(2)
        print('COLAB_RECOVERY_STARTED' if child.poll() is None else 'COLAB_RECOVERY_EXITED')
    fcntl.flock(lock, fcntl.LOCK_UN)
lock.close()
""".replace("WORKER", str(worker)).replace("SPEC_JSON", repr(json.dumps(spec)))


def recover(worker, spec):
    """Use a separate control kernel and preserve all notebook kernels."""
    from colab_cli.runtime import ColabRuntime
    with account_lease([worker], "CLI recovery"):
        assignments = client(worker).list_assignments()
        if len(assignments) != 1:
            return "no_unique_runtime"
        proxy = assignments[0].runtime_proxy_info
        runtime = ColabRuntime(proxy.url, proxy.token)
        messages = []
        try:
            outputs = runtime.execute_code(recovery_code(spec, worker), timeout=30,
                output_hook=lambda output: messages.append(str(output.get("text", ""))))
            messages.extend(str(output.get("text", "")) for output in (outputs or []) if isinstance(output, dict))
            text = "\n".join(messages)
            for result in ("STARTED", "ACTIVE", "NO_CHECKPOINT", "MISSING_WORKDIR", "EXITED", "LOCKED"):
                if "COLAB_RECOVERY_" + result in text:
                    return result.lower()
            return "unconfirmed"
        finally:
            runtime.stop(shutdown_kernel=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--spec", type=Path, default=CONFIG["spec"])
    parser.add_argument("--worker-ids", nargs="+", type=int, choices=CLI_CONFIG["worker_ids"], default=CLI_CONFIG["worker_ids"])
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--show-config", action="store_true")
    args = parser.parse_args()
    if args.show_config:
        print(json.dumps(CONFIG, default=str, indent=2))
        return
    if not args.spec.is_file():
        print("No recovery policy configured. Configure a resumable command before --apply.")
        return
    policies = json.loads(args.spec.read_text(encoding="utf-8"))
    for worker in args.worker_ids:
        spec = policies.get(str(worker))
        if spec:
            validate_spec(spec)
            result = recover(worker, spec) if args.apply else "configured"
            print(f"Worker {worker}: {result}")


if __name__ == "__main__":
    main()
