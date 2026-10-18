"""Serialize local actions across projects for each Google account."""
from contextlib import contextmanager, ExitStack
from contextlib import nullcontext
from pathlib import Path
import os

CONFIG = {"lock_root": Path.home() / ".config/colab-cli/control"}


@contextmanager
def file_lease(path):
    """Hold one nonblocking process lock until its context exits."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a+b") as stream:
        if stream.seek(0, 2) == 0:
            stream.write(b"0")
            stream.flush()
        stream.seek(0)
        try:
            if os.name == "nt":
                import msvcrt
                msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            raise RuntimeError(f"An active process owns the lock: {path}") from None
        try:
            yield
        finally:
            if os.name == "nt":
                stream.seek(0)
                msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(stream.fileno(), fcntl.LOCK_UN)


@contextmanager
def account_lease(worker_ids, backend):
    """Reject overlapping controllers until the account owner exits."""
    with ExitStack() as stack:
        for worker_id in sorted(set(worker_ids)):
            try:
                stack.enter_context(file_lease(Path(CONFIG["lock_root"]) / f"worker-{worker_id}.lock"))
            except RuntimeError:
                raise RuntimeError(f"Worker {worker_id} has an active controller. Stop its controller before {backend} actions.") from None
        yield


def invocation_lease(config, backend):
    """Select controller locks from explicit account arguments or defaults."""
    import sys
    from colab.config import WORKERS, resolve_worker_key
    arguments = sys.argv[1:]
    if "--show-config" in arguments or "--help" in arguments or "-h" in arguments:
        return nullcontext()
    selected = config.get("worker_ids", list(WORKERS))
    for flag in ("--worker-ids", "--workers", "--worker-id"):
        if flag in arguments:
            index = arguments.index(flag) + 1
            values = []
            for value in arguments[index:]:
                if value.startswith("-"):
                    break
                values.append(resolve_worker_key(value))
                if flag == "--worker-id":
                    break
            selected = values
            break
    return account_lease(selected, backend)
