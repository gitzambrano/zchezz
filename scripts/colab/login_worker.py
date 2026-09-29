"""Interactive login helper for Google Colab worker profiles in Zchezz.

Opens a visible (headed) Chrome browser window with the worker's persistent profile,
allows the user to complete Google authentication / 2FA without rushing, detects when
the Colab notebook is successfully loaded, and optionally triggers the worker.
"""

import argparse
import sys
import time
from pathlib import Path
from typing import Dict, Any

CURRENT_DIR = Path(__file__).resolve().parent
REPO_ROOT = CURRENT_DIR.parent.parent
if str(CURRENT_DIR) not in sys.path:
    sys.path.insert(0, str(CURRENT_DIR))

from config import WORKERS, resolve_worker_key
from browser_utils import (
    is_cdp_reachable,
    is_profile_in_use,
    dismiss_modals,
    connect_runtime_if_needed,
    trigger_cell_execution,
)

CONFIG: Dict[str, Any] = {
    "worker_id": "v507",
    "timeout_seconds": 300,
    "trigger_after_login": True,
}


def login_and_wait(worker_key: str, timeout_s: int, trigger_after: bool) -> bool:
    from playwright.sync_api import sync_playwright

    w = WORKERS[worker_key]
    name = w["name"]
    profile = w["profile_dir"]
    url = w["notebook_url"]
    cdp_port = w["cdp_port"]

    print("=" * 70)
    print(f"INTERACTIVE LOGIN HELPER FOR {name.upper()}")
    print("=" * 70)
    print(f"Account:  {w['account']}")
    print(f"Profile:  {profile}")
    print(f"URL:      {url}")
    print(f"Timeout:  {timeout_s} seconds")
    print("=" * 70)

    cdp_active = is_cdp_reachable(cdp_port)
    in_use, proc_pid = is_profile_in_use(profile)

    if in_use and not cdp_active:
        print(f"[WARN] Profile is currently locked by PID {proc_pid}.")
        print("Please close any existing Chrome window using this profile first.")
        return False

    with sync_playwright() as p:
        print("\nOpening visible Chrome browser window on your desktop...")
        ctx = p.chromium.launch_persistent_context(
            user_data_dir=profile,
            headless=False,
            channel="chrome",
            args=[f"--remote-debugging-port={cdp_port}", "--no-sandbox"],
        )
        page = ctx.new_page()
        page.goto(url)

        print("\n--> Window is open. Please complete any Google login / 2FA prompts in the browser.")
        print("--> Waiting for notebook to load...")

        start_time = time.time()
        logged_in = False

        while time.time() - start_time < timeout_s:
            try:
                state = page.evaluate("""() => {
                    const curUrl = window.location.href || '';
                    const isGoogleLogin = curUrl.includes('accounts.google.com') || curUrl.includes('signin');
                    const hasConnectBtn = !!document.querySelector('colab-connect-button, #connect');
                    const cells = document.querySelectorAll('colab-cell');
                    return {
                        isGoogleLogin,
                        hasConnectBtn,
                        cellCount: cells.length,
                        url: curUrl
                    };
                }""")

                if not state["isGoogleLogin"] and (state["hasConnectBtn"] or state["cellCount"] > 0):
                    logged_in = True
                    print(f"\n[SUCCESS] Notebook loaded successfully ({state['cellCount']} cells detected)!")
                    break

            except Exception:
                pass

            time.sleep(2)
            elapsed = int(time.time() - start_time)
            print(f"  [{elapsed:03d}s / {timeout_s}s] Awaiting login completion...", end="\r", flush=True)

        if not logged_in:
            print(f"\n[TIMEOUT] Login was not completed within {timeout_s} seconds.")
            ctx.close()
            return False

        time.sleep(4)

        if trigger_after:
            print("\nTriggering runtime connection and self-play cell execution...")
            connect_runtime_if_needed(page)
            time.sleep(4)

            keywords = w.get("target_keywords", ["Remessa 2", worker_key, "selfplay"])
            ok = trigger_cell_execution(page, w, bootloader_template=None, target_keywords=keywords)
            print(f"  Cell trigger result: {'Success' if ok else 'Failed'}")
            time.sleep(5)
            dismiss_modals(page)

        print("\nSession saved. Closing browser...")
        ctx.close()
        print(f"[DONE] Profile {name} is now authenticated and ready for background operations.")
        return True


def main() -> None:
    parser = argparse.ArgumentParser(description="Interactive login helper for Colab workers.")
    parser.add_argument("--worker-id", default=CONFIG["worker_id"], help="Worker identifier (e.g. v507, v331).")
    parser.add_argument("--timeout", type=int, default=CONFIG["timeout_seconds"], help="Max wait seconds for user login.")
    parser.add_argument("--no-trigger", action="store_true", help="Do not trigger cell execution after login.")
    args = parser.parse_args()

    worker_key = resolve_worker_key(args.worker_id)
    trigger = not args.no_trigger
    login_and_wait(worker_key, args.timeout, trigger)


if __name__ == "__main__":
    main()
