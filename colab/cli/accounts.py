"""List account access or attach existing runtimes."""

import sys as _sys
from pathlib import Path as _Path
_repo_root = _Path(__file__).resolve().parents[2]
if str(_repo_root) not in _sys.path:
    _sys.path.insert(0, str(_repo_root))

import argparse
import json

from colab.config import WORKERS
from colab.cli.backend import attach, client, error_status
from colab.cli.settings import CONFIG


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--worker-ids", nargs="+", type=int, choices=CONFIG["worker_ids"], default=CONFIG["worker_ids"])
    parser.add_argument("--attach", action="store_true")
    parser.add_argument("--endpoint")
    parser.add_argument("--show-config", action="store_true")
    args = parser.parse_args()
    if args.show_config:
        print(json.dumps(CONFIG, default=str, indent=2))
        return 0
    failed = False
    for worker in args.worker_ids:
        record = {"worker_id": worker, "account": WORKERS[worker]["account"]}
        try:
            assignments = client(worker).list_assignments()
            if args.attach and assignments:
                record["endpoint"] = attach(worker, args.endpoint)
            record.update(status="ready", endpoints=[a.endpoint for a in assignments])
        except Exception as error:
            record.update(status=error_status(error), error_type=type(error).__name__)
            failed = True
        print(json.dumps(record), flush=True)
    return int(failed)


if __name__ == "__main__":
    raise SystemExit(main())
