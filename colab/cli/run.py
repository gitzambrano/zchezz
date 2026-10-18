"""Run an official Colab command for one account."""

import sys as _sys
from pathlib import Path as _Path
_repo_root = _Path(__file__).resolve().parents[2]
if str(_repo_root) not in _sys.path:
    _sys.path.insert(0, str(_repo_root))

import argparse
from contextlib import nullcontext
import subprocess
import json

from colab.cli.settings import CONFIG, account_environment, command
from colab.control import account_lease

READ_COMMANDS = {"sessions", "status", "ls", "download", "log", "version", "help", "readme", "skill", "whoami", "url", "usage"}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--worker-id", type=int, choices=CONFIG["worker_ids"], default=CONFIG["worker_ids"][0])
    parser.add_argument("--show-config", action="store_true")
    parser.add_argument("arguments", nargs=argparse.REMAINDER)
    args = parser.parse_args()
    if args.show_config:
        print(json.dumps(CONFIG, default=str, indent=2))
        return 0
    arguments = args.arguments
    if arguments[:1] == ["--"]:
        arguments = arguments[1:]
    arguments = arguments or ["sessions"]
    from pathlib import Path
    if arguments[0] not in {"version", "help", "readme", "skill"} and not Path(account_environment(args.worker_id)["GOOGLE_APPLICATION_CREDENTIALS"]).is_file():
        print(f"Worker {args.worker_id}: authorize the account with python -m colab.cli.login --worker-ids {args.worker_id}.")
        return 1
    if arguments[0].startswith("-"):
        parser.error("Place the Colab command before its options. Global authentication settings are fixed per account.")
    lease = nullcontext() if arguments[0] in READ_COMMANDS else account_lease([args.worker_id], "CLI")
    with lease:
        return subprocess.call(command(args.worker_id, arguments), env=account_environment(args.worker_id))


if __name__ == "__main__":
    raise SystemExit(main())
