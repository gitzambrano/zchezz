"""Administrative runtime management for Zchezz Google Colab notebooks via Playwright.

Provides tools to switch hardware accelerators (e.g. from GPU to CPU to clear quota
exhaustion), reset hanging environments, or terminate stale ghost sessions.
"""

import argparse
import sys
import time
from pathlib import Path
from typing import Dict, Any

# Ensure colab root is in path
CURRENT_DIR = Path(__file__).resolve().parent
REPO_ROOT = CURRENT_DIR.parent
if str(CURRENT_DIR) not in sys.path:
    sys.path.insert(0, str(CURRENT_DIR))

from config import WORKERS, resolve_worker_key
from browser_utils import is_cdp_reachable, is_profile_in_use

CONFIG: Dict[str, Any] = {
    "worker_ids": ["v331", "v507"],
    "action": "switch-cpu",  # Options: 'switch-cpu', 'reset', 'terminate-active'
    "headless": True,
    "page_timeout_ms": 45000,
    "load_delay_seconds": 8,
}


def manage_worker(worker: Dict[str, Any], action: str, headless: bool, timeout_ms: int, delay_s: int) -> Dict[str, Any]:
    from playwright.sync_api import sync_playwright

    name = worker["name"]
    profile = worker["profile_dir"]
    url = worker["notebook_url"]
    wid = worker["worker_id"]
    cdp_port = worker["cdp_port"]

    result: Dict[str, Any] = {
        "worker_id": wid,
        "name": name,
        "action": action,
        "success": False,
        "details": "",
        "error": None,
    }

    cdp_active = is_cdp_reachable(cdp_port)
    in_use, proc_pid = is_profile_in_use(profile)

    if in_use and not cdp_active:
        msg = f"Profile directory is actively locked by process PID {proc_pid}. Skipping manage action."
        print(f"  [WARN] {msg}")
        result["error"] = msg
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
                ctx = p.chromium.launch_persistent_context(
                    user_data_dir=profile,
                    headless=headless,
                    channel="chrome",
                    args=[f"--remote-debugging-port={cdp_port}", "--no-sandbox"],
                )
                page = ctx.new_page()
                page.goto(url, timeout=timeout_ms)
                browser_to_close = ctx

            time.sleep(delay_s)

            if action == "switch-cpu":
                page.locator('div[id="runtime-menu-button"]').click()
                time.sleep(1)
                page.locator('text="Alterar o tipo de ambiente de execução"').click()
                time.sleep(2)

                page.get_by_text("CPU", exact=True).click()
                time.sleep(1)

                page.locator('md-text-button').filter(has_text="Salvar").click()
                time.sleep(5)
                result["success"] = True
                result["details"] = "Hardware accelerator switched to CPU (Standard)."

            elif action == "reset":
                page.locator('div[id="runtime-menu-button"]').click()
                time.sleep(1)
                page.locator('text="Desconectar e excluir ambiente de execução"').click()
                time.sleep(2)

                page.evaluate("""() => {
                    const btns = Array.from(document.querySelectorAll('mwc-button, paper-button, button'));
                    const ok = btns.find(b => b.innerText && (b.innerText.trim() === 'Sim' || b.innerText.trim() === 'Desconectar'));
                    if (ok) ok.click();
                }""")
                time.sleep(3)
                result["success"] = True
                result["details"] = "Runtime disconnected and deleted."

            elif action == "terminate-active":
                page.locator('div[id="runtime-menu-button"]').click()
                time.sleep(1)
                page.locator('text="Gerenciar sessões"').click()
                time.sleep(2)

                terminated = page.evaluate("""() => {
                    const btns = Array.from(document.querySelectorAll('mwc-icon-button, paper-icon-button, button'));
                    const trashBtns = btns.filter(b => {
                        const title = (b.getAttribute('title') || b.getAttribute('aria-label') || '').toLowerCase();
                        return title.includes('cancelar') || title.includes('encerrar') || title.includes('terminate');
                    });
                    for (const b of trashBtns) {
                        b.click();
                    }
                    return trashBtns.length;
                }""")
                time.sleep(2)
                result["success"] = True
                result["details"] = f"Terminated {terminated} active session(s)."

            if not cdp_active:
                browser_to_close.close()
            else:
                browser_to_close.disconnect()

    except Exception as exc:
        result["error"] = str(exc)

    return result


def main() -> None:
    parser = argparse.ArgumentParser(description="Administrative management of Zchezz Colab runtimes.")
    parser.add_argument("--worker-ids", nargs="+", default=CONFIG["worker_ids"], help="Worker identifiers (e.g. v331 v507 1 2).")
    parser.add_argument("--action", choices=["switch-cpu", "reset", "terminate-active"], default=CONFIG["action"], help="Administrative action.")
    parser.add_argument("--headed", action="store_true", help="Run browser in visible headed mode.")
    parser.add_argument("--show-config", action="store_true", help="Display effective configuration and exit.")
    args = parser.parse_args()

    effective_cfg = dict(CONFIG)
    effective_cfg["worker_ids"] = [resolve_worker_key(w) for w in args.worker_ids]
    effective_cfg["action"] = args.action
    if args.headed:
        effective_cfg["headless"] = False

    if args.show_config:
        print("Effective Configuration:")
        for k, v in effective_cfg.items():
            print(f"  {k}: {v}")
        return

    print("=" * 70)
    print(f"ZCHEZZ COLAB RUNTIME MANAGER - Action: {effective_cfg['action']}")
    print("=" * 70)

    for wid in effective_cfg["worker_ids"]:
        if wid not in WORKERS:
            continue
        w = WORKERS[wid]
        print(f"Executing '{effective_cfg['action']}' on {w['name']} ({wid})...")
        res = manage_worker(
            worker=w,
            action=effective_cfg["action"],
            headless=effective_cfg["headless"],
            timeout_ms=effective_cfg["page_timeout_ms"],
            delay_s=effective_cfg["load_delay_seconds"],
        )

        status_str = "[OK]" if res["success"] else "[FAILED]"
        print(f"  Status: {status_str}")
        if res.get("details"):
            print(f"  Details: {res['details']}")
        if res.get("error"):
            print(f"  Error: {res['error']}")

    print("\nManagement sequence completed.")


if __name__ == "__main__":
    main()
