"""Continuous watchdog and keep-alive monitor for Google Colab workers.

Supports both official CLI (default, lightweight single-process) and Playwright (browser fallback).
Monitors all seven Google accounts simultaneously with minimal local resource footprint.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys
from typing import Any, Dict, List

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from colab.config import WORKERS
from colab.cli.settings import CONFIG as CLI_CONFIG
from colab.monitoring import CONFIG as MONITOR_CONFIG

CONFIG: Dict[str, Any] = {
    "backend": "cli",
    "worker_ids": list(WORKERS),
    "interval": 60.0,
    "stall_seconds": 900.0,
    "max_cycles": 0,
    "recover": True,
    "output": CLI_CONFIG["output"] / "monitor.json",
    "recovery_spec": CLI_CONFIG["output"] / "recovery.json",
    "threads": 5,
}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--backend", choices=["cli", "playwright"], default=CONFIG["backend"],
                        help="Transport backend to use (default: cli)")
    parser.add_argument("--worker-ids", type=int, nargs="+", default=CONFIG["worker_ids"],
                        help=f"Worker IDs to monitor (default: all 7 workers {CONFIG['worker_ids']})")
    parser.add_argument("--interval", type=float, default=CONFIG["interval"],
                        help="Observation interval in seconds (default: 60)")
    parser.add_argument("--stall-seconds", type=float, default=CONFIG["stall_seconds"],
                        help="Stall detection threshold in seconds (default: 900)")
    parser.add_argument("--max-cycles", type=int, default=CONFIG["max_cycles"],
                        help="Maximum observation cycles before exit (0 = continuous)")
    parser.add_argument("--once", action="store_true",
                        help="Run a single observation cycle and exit")
    parser.add_argument("--no-recover", dest="recover", action="store_false",
                        help="Disable automatic job recovery on stall or drop")
    parser.add_argument("--headed", action="store_true",
                        help="Playwright only: Run browser in visible headed mode")
    parser.add_argument("--show-config", action="store_true",
                        help="Display effective configuration and exit")
    args = parser.parse_args()

    cfg = {
        "backend": args.backend,
        "worker_ids": args.worker_ids,
        "interval": args.interval,
        "stall_seconds": args.stall_seconds,
        "max_cycles": 1 if args.once else args.max_cycles,
        "recover": args.recover,
        "output": CONFIG["output"],
        "recovery_spec": CONFIG["recovery_spec"],
        "threads": CONFIG["threads"],
    }

    if args.show_config:
        print(json.dumps(cfg, default=str, indent=2))
        return

    print("=" * 70)
    print(f"COLAB WORKER WATCHDOG ({ROOT.name.upper()})")
    print("=" * 70)
    print(f"Backend: {cfg['backend']}")
    print(f"Monitored workers: {cfg['worker_ids']}")
    print(f"Observation interval: {cfg['interval']}s")
    print(f"Stall threshold: {cfg['stall_seconds']}s")
    print(f"Auto-recovery enabled: {cfg['recover']}")
    print(f"Continuous execution: {'No (single cycle)' if cfg['max_cycles'] == 1 else 'Yes (Ctrl+C to stop)'}")
    print("=" * 70)

    if cfg["backend"] == "playwright":
        from colab.playwright.watchdog_workers import main as pw_main
        sys.argv = [sys.argv[0], "--worker-ids"] + [str(w) for w in cfg["worker_ids"]]
        if args.headed:
            sys.argv.append("--headed")
        pw_main()
    else:
        # CLI backend: lightweight, single Python process
        from colab.cli.monitor import run as run_cli_monitor
        try:
            run_cli_monitor(cfg)
        except KeyboardInterrupt:
            print("\nWatchdog stopped by operator. Remote VMs and jobs remain active.")


if __name__ == "__main__":
    main()
