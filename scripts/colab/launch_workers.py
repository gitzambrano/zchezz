"""Launch and bootstrap Google Colab self-play workers headlessly via Playwright.

Updates notebook cells with the resilient self-cloning bootloader, connects
the runtime, and triggers execution while avoiding redundant restarts of active workers.
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

from config import WORKERS, BOOTLOADER_TEMPLATE
from browser_utils import (
    is_cdp_reachable,
    is_profile_in_use,
    dismiss_modals,
    connect_runtime_if_needed,
    get_notebook_dom_state,
    trigger_cell_execution,
    launch_stealth_context,
)

CONFIG: Dict[str, Any] = {
    "worker_ids": [1, 2, 3, 4, 5, 6, 7],
    "skip_if_running": True,
    "headless": True,
    "page_timeout_ms": 60000,
    "load_delay_seconds": 8,
    "wait_after_run_seconds": 15,
    "artifacts_dir": str(REPO_ROOT / "artifacts" / "colab"),
}


def create_artifacts_dir(dir_path: str) -> Path:
    p = Path(dir_path)
    p.mkdir(parents=True, exist_ok=True)
    return p


def launch_worker(
    worker: Dict[str, Any],
    skip_if_running: bool,
    headless: bool,
    timeout_ms: int,
    delay_s: int,
    wait_run_s: int,
    artifacts_dir: Path,
) -> Dict[str, Any]:
    from playwright.sync_api import sync_playwright

    wid = worker["worker_id"]
    name = worker["name"]
    profile = worker["profile_dir"]
    url = worker["notebook_url"]
    cdp_port = worker.get("cdp_port", 9000 + wid)
    keywords = worker.get("target_keywords", ["run_colab_worker.py", "selfplay_targeted_weakness", "zquoridor"])

    result: Dict[str, Any] = {
        "worker_id": wid,
        "name": name,
        "account": worker["account"],
        "action_taken": "none",
        "running": False,
        "pending": False,
        "error": None,
    }

    cdp_active = is_cdp_reachable(cdp_port)
    in_use, proc_pid = is_profile_in_use(profile)

    if in_use and not cdp_active:
        msg = f"Profile directory is actively locked by process PID {proc_pid}. Skipping launch to prevent corruption."
        print(f"  [WARN] {msg}")
        result["action_taken"] = "locked_by_external_process"
        result["error"] = msg
        return result

    try:
        with sync_playwright() as p:
            browser_to_close = None
            if cdp_active:
                print(f"  Attaching to live browser session via CDP on port {cdp_port}...")
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
                    extra_args=["--disable-gpu"],
                )
                page = ctx.pages[0] if ctx.pages else ctx.new_page()
                page.goto(url, wait_until="commit", timeout=timeout_ms)
                browser_to_close = ctx

            time.sleep(delay_s)

            # Step 1: Connect runtime if disconnected
            connect_runtime_if_needed(page)
            time.sleep(4)

            # Step 2: Check current status
            dom_state = get_notebook_dom_state(page, keywords)
            if skip_if_running and (dom_state["running"] or dom_state["pending"]):
                result["action_taken"] = "already_running_skipped"
                result["running"] = dom_state["running"]
                result["pending"] = dom_state["pending"]
                if not cdp_active and browser_to_close:
                    browser_to_close.close()
                return result

            # Step 3: Trigger cell execution
            ok = trigger_cell_execution(page, worker, BOOTLOADER_TEMPLATE, target_keywords=keywords)
            if not ok:
                result["error"] = "Failed to trigger execution"
                if not cdp_active and browser_to_close:
                    browser_to_close.close()
                return result

            result["action_taken"] = "cell_triggered"
            time.sleep(wait_run_s)
            dismiss_modals(page)

            # Step 4: Verify execution
            final_state = get_notebook_dom_state(page, keywords)
            result["running"] = final_state["running"]
            result["pending"] = final_state["pending"]

            # Save confirmation screenshot
            ss_path = artifacts_dir / f"colab_{wid}_launched.png"
            page.screenshot(path=str(ss_path))
            result["screenshot_path"] = str(ss_path)

            if not cdp_active and browser_to_close:
                browser_to_close.close()

    except Exception as exc:
        result["error"] = str(exc)

    return result


def main() -> None:
    parser = argparse.ArgumentParser(description="Launch Zquoridor Colab self-play workers headlessly.")
    parser.add_argument("--worker-ids", type=int, nargs="+", default=CONFIG["worker_ids"], help="Worker IDs (e.g. 3 4 5).")
    parser.add_argument("--force-restart", action="store_true", help="Force re-run even if already running.")
    parser.add_argument("--headed", action="store_true", help="Run browser in visible headed mode.")
    parser.add_argument("--show-config", action="store_true", help="Display effective configuration and exit.")
    args = parser.parse_args()

    effective_cfg = dict(CONFIG)
    effective_cfg["worker_ids"] = args.worker_ids
    if args.force_restart:
        effective_cfg["skip_if_running"] = False
    if args.headed:
        effective_cfg["headless"] = False

    if args.show_config:
        print("Effective Configuration:")
        for k, v in effective_cfg.items():
            print(f"  {k}: {v}")
        return

    artifacts_path = create_artifacts_dir(effective_cfg["artifacts_dir"])

    print("=" * 70)
    print("ZQUORIDOR COLAB WORKER LAUNCHER")
    print("=" * 70)
    print(f"Target workers: {effective_cfg['worker_ids']}")
    print(f"Skip if running: {effective_cfg['skip_if_running']}")
    print(f"Headless: {effective_cfg['headless']}")
    print("=" * 70)

    for wid in effective_cfg["worker_ids"]:
        if wid not in WORKERS:
            print(f"Skipping unknown worker: {wid}")
            continue
        w = WORKERS[wid]
        print(f"\nLaunching {w['name']} ({w['account']})...")
        res = launch_worker(
            worker=w,
            skip_if_running=effective_cfg["skip_if_running"],
            headless=effective_cfg["headless"],
            timeout_ms=effective_cfg["page_timeout_ms"],
            delay_s=effective_cfg["load_delay_seconds"],
            wait_run_s=effective_cfg["wait_after_run_seconds"],
            artifacts_dir=artifacts_path,
        )

        status_tag = "[RUNNING]" if res["running"] else ("[PENDING]" if res["pending"] else "[IDLE]")
        print(f"  Action taken: {res['action_taken']}")
        print(f"  State: {status_tag}")
        if res.get("error"):
            print(f"  Error: {res['error']}")
        if res.get("screenshot_path"):
            print(f"  Screenshot: {res['screenshot_path']}")

    print("\nLaunch sequence completed.")


if __name__ == "__main__":
    main()
