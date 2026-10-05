"""Interactive login helper for Google Colab worker profiles in Zquoridor.

Opens a native Google Chrome browser window with the worker's persistent profile,
allows the user to complete Google authentication and two-factor verification without
triggering automated browser security blocks, detects when the session is valid,
and optionally triggers the self-play worker.
"""

import argparse
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Dict, Any

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
    trigger_cell_execution,
    launch_stealth_context,
    save_profile_cookies,
)

CONFIG: Dict[str, Any] = {
    "worker_ids": [6, 7],
    "timeout_seconds": 600,
    "trigger_after_login": True,
    "use_native_chrome": True,
}


def find_chrome_executable() -> str:
    """Find the path to the installed Google Chrome binary."""
    candidates = [
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
        os.path.expandvars(r"%LOCALAPPDATA%\Google\Chrome\Application\chrome.exe"),
    ]
    for path in candidates:
        if os.path.isfile(path):
            return path
    return "chrome.exe"


def login_with_native_chrome(
    worker_id: int,
    timeout_s: int,
    trigger_after: bool,
) -> bool:
    """Authenticate through native Google Chrome to bypass automated browser detection."""
    from playwright.sync_api import sync_playwright

    w = WORKERS[worker_id]
    name = w["name"]
    profile = w["profile_dir"]
    url = w["notebook_url"]
    cdp_port = w.get("cdp_port", 9000 + worker_id)
    chrome_exe = find_chrome_executable()

    print("=" * 70)
    print(f"INTERACTIVE LOGIN HELPER FOR {name.upper()}")
    print("=" * 70)
    print(f"Account:  {w['account']}")
    print(f"Profile:  {profile}")
    print(f"URL:      {url}")
    print(f"Binary:   {chrome_exe}")
    print(f"Timeout:  {timeout_s} seconds")
    print("=" * 70)

    cdp_active = is_cdp_reachable(cdp_port)
    in_use, proc_pid = is_profile_in_use(profile)

    if in_use and not cdp_active:
        print(f"[WARN] Profile is currently locked by process PID {proc_pid}.")
        print("Please close any existing Chrome window using this profile first.")
        return False

    print("\nOpening native Google Chrome on your desktop...")
    print("This window runs without automation flags to prevent Google security blocks.\n")
    print("Instructions:")
    print(f"  1. Sign in with {w['account']}.")
    print("  2. Complete your password and any two-factor verification.")
    print("  3. Confirm that the Colab notebook is loaded.")
    print("  4. CLOSE the Chrome window when finished to release the profile lock.")
    print("-" * 70)
    print("Waiting for Chrome window to be closed after login...\n")

    try:
        proc = subprocess.Popen([chrome_exe, f"--user-data-dir={profile}", url])
    except Exception as exc:
        print(f"[ERROR] Failed to start Chrome: {exc}")
        return False

    try:
        proc.wait(timeout=timeout_s)
    except subprocess.TimeoutExpired:
        print(f"\n[TIMEOUT] Session exceeded {timeout_s} seconds.")
        proc.terminate()
        return False
    except KeyboardInterrupt:
        print("\n[CANCELLED] Operation cancelled by user.")
        return False

    print("\nChrome window closed. Profile unlocked.")
    print("Verifying session and saving permanent cookies backup...")
    time.sleep(2)

    with sync_playwright() as p:
        ctx = launch_stealth_context(
            p,
            profile_dir=profile,
            headless=True,
            cdp_port=cdp_port,
        )
        page = ctx.new_page()
        page.goto(url, wait_until="commit", timeout=60000)
        time.sleep(6)

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

        if state["isGoogleLogin"]:
            print("\n[FAILED] Session is still redirected to Google Sign-In.")
            print("Authentication was not completed. Run the script again and finish login.")
            ctx.close()
            return False

        print(f"\n[SUCCESS] Notebook loaded successfully ({state['cellCount']} cells detected).")
        save_profile_cookies(ctx, profile)
        print("  [SUCCESS] Permanent session cookies saved to cookies.json.")

        if trigger_after:
            print("\nTriggering runtime connection and self-play cell execution...")
            connect_runtime_if_needed(page)
            time.sleep(4)

            ok = trigger_cell_execution(page, worker_id, BOOTLOADER_TEMPLATE)
            print(f"  Cell trigger result: {'Success' if ok else 'Failed'}")
            time.sleep(5)
            dismiss_modals(page)

        print("\nSession saved. Closing browser context...")
        ctx.close()
        print(f"[DONE] Profile {name} is authenticated and ready for background operations.")
        return True


def login_with_playwright(
    worker_id: int,
    timeout_s: int,
    trigger_after: bool,
) -> bool:
    """Authenticate through headed Playwright browser context."""
    from playwright.sync_api import sync_playwright

    w = WORKERS[worker_id]
    name = w["name"]
    profile = w["profile_dir"]
    url = w["notebook_url"]
    cdp_port = w.get("cdp_port", 9000 + worker_id)

    print("=" * 70)
    print(f"INTERACTIVE PLAYWRIGHT LOGIN HELPER FOR {name.upper()}")
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
        ctx = launch_stealth_context(
            p,
            profile_dir=profile,
            headless=False,
            cdp_port=cdp_port,
        )
        page = ctx.new_page()
        page.goto(url)

        print("\n--> Window is open. Please complete any Google login prompts in the browser.")
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
                    print(f"\n[SUCCESS] Notebook loaded successfully ({state['cellCount']} cells detected).")
                    save_profile_cookies(ctx, profile)
                    print("  [SUCCESS] Permanent session cookies saved to cookies.json.")
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

            ok = trigger_cell_execution(page, worker_id, BOOTLOADER_TEMPLATE)
            print(f"  Cell trigger result: {'Success' if ok else 'Failed'}")
            time.sleep(5)
            dismiss_modals(page)

        print("\nSession saved. Closing browser...")
        ctx.close()
        print(f"[DONE] Profile {name} is authenticated and ready for background operations.")
        return True


def login_and_wait(
    worker_id: int,
    timeout_s: int,
    trigger_after: bool,
    use_native_chrome: bool = True,
) -> bool:
    """Route to appropriate login method based on configuration."""
    if use_native_chrome:
        return login_with_native_chrome(worker_id, timeout_s, trigger_after)
    return login_with_playwright(worker_id, timeout_s, trigger_after)


def main() -> None:
    parser = argparse.ArgumentParser(description="Interactive login helper for Colab workers.")
    parser.add_argument("--worker-ids", type=int, nargs="+", default=None, help="Worker IDs to authenticate sequentially (e.g. 2 4).")
    parser.add_argument("--worker-id", type=int, default=None, help="Single worker ID (e.g. 2).")
    parser.add_argument("--timeout", type=int, default=CONFIG["timeout_seconds"], help="Max wait seconds for user login.")
    parser.add_argument("--no-trigger", action="store_true", help="Do not trigger cell execution after login.")
    parser.add_argument("--playwright", action="store_true", help="Use Playwright headed mode instead of native Chrome.")
    args = parser.parse_args()

    trigger = not args.no_trigger
    use_native = not args.playwright

    if args.worker_ids:
        w_ids = args.worker_ids
    elif args.worker_id is not None:
        w_ids = [args.worker_id]
    else:
        w_ids = CONFIG.get("worker_ids", [2, 4])

    for wid in w_ids:
        if wid not in WORKERS:
            print(f"[WARN] Skipping unknown worker ID: {wid}")
            continue
        ok = login_and_wait(wid, args.timeout, trigger, use_native_chrome=use_native)
        if not ok and len(w_ids) > 1:
            print(f"[WARN] Login not completed for worker {wid}. Stopping sequence.")
            break


if __name__ == "__main__":
    main()
