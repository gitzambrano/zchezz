"""Inspect Google Colab worker status headlessly via Playwright.

Checks runtime connection state, running cells, and recent self-play progress
for configured workers. Safe against browser profile collisions and attaches over CDP.
"""

import argparse
import sys
import time
from pathlib import Path
from typing import Dict, Any, List

# Ensure scripts root is in path
CURRENT_DIR = Path(__file__).resolve().parent
REPO_ROOT = CURRENT_DIR.parent.parent
if str(CURRENT_DIR) not in sys.path:
    sys.path.insert(0, str(CURRENT_DIR))

from config import WORKERS, resolve_worker_key
from browser_utils import (
    is_cdp_reachable,
    is_profile_in_use,
    get_notebook_dom_state,
    dismiss_modals,
    launch_stealth_context,
)

CONFIG: Dict[str, Any] = {
    "worker_ids": [1, 2, 3, 4, 5, 6, 7],
    "headless": True,
    "page_timeout_ms": 45000,
    "load_delay_seconds": 8,
}


def inspect_worker(worker: Dict[str, Any], headless: bool, timeout_ms: int, delay_s: int) -> Dict[str, Any]:
    from playwright.sync_api import sync_playwright

    name = worker["name"]
    profile = worker["profile_dir"]
    url = worker["notebook_url"]
    worker_id = worker["worker_id"]
    cdp_port = worker.get("cdp_port", 9000 + worker_id)
    keywords = worker.get("target_keywords", ["run_colab_worker.py", "selfplay_15m", "zquoridor"])

    result: Dict[str, Any] = {
        "worker_id": worker_id,
        "name": name,
        "account": worker["account"],
        "connected": False,
        "running": False,
        "pending": False,
        "status_text": "unknown",
        "output_preview": "",
        "error": None,
    }

    cdp_active = is_cdp_reachable(cdp_port)
    in_use, proc_pid = is_profile_in_use(profile)

    if in_use and not cdp_active:
        result["status_text"] = f"Managed by external process (PID {proc_pid})"
        result["connected"] = True
        result["running"] = True
        return result

    try:
        with sync_playwright() as p:
            browser_to_close = None
            if cdp_active:
                browser = p.chromium.connect_over_cdp(f"http://127.0.0.1:{cdp_port}")
                ctx = browser.contexts[0] if browser.contexts else browser.new_context()
                page = ctx.pages[0] if ctx.pages else ctx.new_page()
                browser_to_close = browser
            else:
                ctx = launch_stealth_context(
                    p,
                    profile_dir=profile,
                    headless=headless,
                    cdp_port=cdp_port,
                )
                page = ctx.new_page()
                page.goto(url, wait_until="commit", timeout=timeout_ms)
                browser_to_close = ctx

            try:
                time.sleep(delay_s)
                dismiss_modals(page)
                state = get_notebook_dom_state(page, keywords)

                result["connected"] = state["kConnected"] or ("RAM" in state["statusText"])
                result["status_text"] = state["statusText"]
                result["running"] = state["running"]
                result["pending"] = state["pending"]
                result["output_preview"] = state["outText"]
            finally:
                if not cdp_active and browser_to_close:
                    browser_to_close.close()
    except Exception as exc:
        result["error"] = str(exc)

    return result


def run_inspect(cfg: Dict[str, Any]) -> List[Dict[str, Any]]:
    print("=" * 70)
    print("ZQUORIDOR COLAB WORKER INSPECTION")
    print("=" * 70)

    results = []
    for wid in cfg["worker_ids"]:
        if wid not in WORKERS:
            print(f"Unknown worker ID {wid}, skipping.")
            continue
        w = WORKERS[wid]
        print(f"Inspecting {w['name']} (Worker #{wid}, Account: {w['account']})...")
        res = inspect_worker(w, cfg["headless"], cfg["page_timeout_ms"], cfg["load_delay_seconds"])
        results.append(res)

        if res["error"]:
            print(f"  [ERROR] {res['error']}")
        else:
            conn_status = "CONNECTED" if res["connected"] else f"DISCONNECTED ({res['status_text']})"
            run_status = "ACTIVE RUNNING" if res["running"] else ("PENDING" if res["pending"] else "IDLE")
            print(f"  Connection: {conn_status}")
            print(f"  Execution:  {run_status}")
            if res["output_preview"]:
                lines = [line.strip() for line in res["output_preview"].splitlines() if line.strip()]
                preview = " | ".join(lines[-3:]) if lines else "no lines"
                print(f"  Output:     {preview[:120]}...")
        print("-" * 70)

    return results


def main() -> None:
    parser = argparse.ArgumentParser(description="Inspect Colab workers status via Playwright.")
    parser.add_argument("--worker-ids", type=int, nargs="+", default=CONFIG["worker_ids"], help="Worker IDs to inspect")
    parser.add_argument("--headed", action="store_true", help="Run browser in visible mode")
    parser.add_argument("--timeout-ms", type=int, default=CONFIG["page_timeout_ms"], help="Page navigation timeout in ms")
    args = parser.parse_args()

    cfg = dict(CONFIG)
    cfg["worker_ids"] = args.worker_ids
    if args.headed:
        cfg["headless"] = False
    cfg["page_timeout_ms"] = args.timeout_ms

    run_inspect(cfg)


if __name__ == "__main__":
    main()
