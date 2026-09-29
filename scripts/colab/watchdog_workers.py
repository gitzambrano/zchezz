"""Continuous watchdog and keep-alive monitor for Google Colab self-play workers in Zchezz.

Maintains active persistent browser sessions with periodic micro-interactions to
prevent Colab idle disconnects. Detects session disconnects, automatically reconnects,
re-triggers execution, and saves periodic status screenshots and metrics.
"""

import argparse
import json
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, List, Optional

sys.stdout.reconfigure(encoding='utf-8')

# Ensure scripts root is in path
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
    get_notebook_dom_state,
    trigger_cell_execution,
)

CONFIG: Dict[str, Any] = {
    "worker_ids": ["v331", "v507"],
    "check_interval_seconds": 60,
    "screenshot_interval_cycles": 10,
    "auto_reconnect": True,
    "headless": True,
    "page_timeout_ms": 60000,
    "artifacts_dir": str(REPO_ROOT / "artifacts" / "colab"),
}


def create_artifacts_dir(dir_path: str) -> Path:
    p = Path(dir_path)
    p.mkdir(parents=True, exist_ok=True)
    return p


def init_worker_session(p: Any, worker: Dict[str, Any], headless: bool, timeout_ms: int) -> Optional[Dict[str, Any]]:
    """Initialize or attach to a persistent browser session for a Colab worker."""
    wid = worker["worker_id"]
    name = worker["name"]
    profile = worker["profile_dir"]
    url = worker["notebook_url"]
    cdp_port = worker["cdp_port"]

    print(f"Initializing session for {name} ({wid})...")

    cdp_active = is_cdp_reachable(cdp_port)
    in_use, proc_pid = is_profile_in_use(profile)

    if in_use and not cdp_active:
        print(f"  [WARN] Profile for {name} is locked by external process PID {proc_pid}.")
        return None

    try:
        if cdp_active:
            print(f"  Attaching over live CDP on port {cdp_port}...")
            browser = p.chromium.connect_over_cdp(f"http://127.0.0.1:{cdp_port}")
            ctx = browser.contexts[0] if browser.contexts else browser.new_context()
            page = ctx.pages[0] if ctx.pages else ctx.new_page()
            is_cdp = True
        else:
            ctx = p.chromium.launch_persistent_context(
                user_data_dir=profile,
                headless=headless,
                channel="chrome",
                args=[
                    f"--remote-debugging-port={cdp_port}",
                    "--no-sandbox",
                    "--disable-gpu",
                    "--remote-allow-origins=*",
                ],
            )
            page = ctx.pages[0] if ctx.pages else ctx.new_page()
            page.goto(url, wait_until="commit", timeout=timeout_ms)
            is_cdp = False

        print(f"  Connected to {name}.")
        return {
            "worker": worker,
            "ctx": ctx,
            "page": page,
            "is_cdp": is_cdp,
            "reconnect_count": 0,
            "last_progress": "Initializing...",
        }
    except Exception as exc:
        print(f"  [ERROR] Failed to initialize {name}: {exc}")
        return None


def run_watchdog(cfg: Dict[str, Any]) -> None:
    from playwright.sync_api import sync_playwright

    artifacts_path = create_artifacts_dir(cfg["artifacts_dir"])
    worker_ids = [resolve_worker_key(wid) for wid in cfg["worker_ids"] if resolve_worker_key(wid) in WORKERS]
    if not worker_ids:
        print("[WATCHDOG] No valid worker IDs configured.")
        return

    print("=" * 70)
    print("ZCHEZZ COLAB ACTIVE WATCHDOG & KEEP-ALIVE")
    print("=" * 70)
    print(f"Monitoring workers: {worker_ids}")
    print(f"Interval: {cfg['check_interval_seconds']}s | Auto-reconnect: {cfg['auto_reconnect']}")
    print(f"Artifacts output: {artifacts_path}")
    print("=" * 70)

    with sync_playwright() as p:
        sessions: Dict[str, Optional[Dict[str, Any]]] = {}

        # 1. Initialize persistent contexts or attach via CDP
        for wid in worker_ids:
            sessions[wid] = init_worker_session(p, WORKERS[wid], cfg["headless"], cfg["page_timeout_ms"])

        if not any(sessions.values()):
            print("[WATCHDOG] No direct sessions could be initialized. Retrying in main loop...")

        time.sleep(8)
        cycle = 0

        # 2. Continuous monitoring and keep-alive loop
        try:
            while True:
                cycle += 1
                now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                print(f"\n--- [Cycle {cycle:04d}] {now_str} ---")

                for wid in worker_ids:
                    w = WORKERS[wid]
                    sess = sessions.get(wid)

                    # Auto-recover dead or closed browser sessions
                    if sess is None or sess.get("page") is None or sess["page"].is_closed():
                        print(f"[{w['name']}] Session missing or closed. Recovering...")
                        try:
                            if sess and not sess.get("is_cdp") and sess.get("ctx"):
                                sess["ctx"].close()
                        except Exception:
                            pass
                        sess = init_worker_session(p, w, cfg["headless"], cfg["page_timeout_ms"])
                        sessions[wid] = sess
                        if not sess:
                            continue

                    page = sess["page"]
                    keywords = w.get("target_keywords", ["Remessa 2", wid, "selfplay"])

                    try:
                        dismiss_modals(page)

                        # Extract state from Colab DOM
                        state = get_notebook_dom_state(page, keywords)

                        # Extract clean progress line
                        lines = [line.strip() for line in state["outText"].splitlines() if line.strip()]
                        progress_lines = [
                            l for l in lines
                            if any(k in l for k in ["Iniciando Shard:", "Progresso:", "validado:", "posicoes", "games", "ok:", "MATCH:"])
                        ]
                        current_progress = progress_lines[-1] if progress_lines else (lines[-1] if lines else "No output yet")
                        sess["last_progress"] = current_progress

                        # Keep-alive micro-interaction: subtle mouse movement prevents idle timeout
                        page.mouse.move(60 + (cycle % 40), 60 + (cycle % 40))

                        run_tag = "[RUNNING]" if state["running"] else ("[PENDING]" if state["pending"] else "[IDLE]")
                        print(f"[{w['name']}] {run_tag} (VM: {state['statusText']}) -> {current_progress[:90]}")

                        # 3. Auto-reconnect if VM disconnected and not running
                        if cfg["auto_reconnect"] and not state["running"] and not state["pending"]:
                            if "Conectar" in state["statusText"] and "Conectando" not in state["statusText"]:
                                print(f"[{w['name']}] [DISCONNECTED] Connecting VM...")
                                sess["reconnect_count"] += 1
                                connect_runtime_if_needed(page)
                                time.sleep(12)

                            print(f"[{w['name']}] [IDLE] Triggering target cell...")
                            ok = trigger_cell_execution(page, w, bootloader_template=None, target_keywords=keywords)
                            if ok:
                                print(f"[{w['name']}] Triggered execution successfully.")
                            else:
                                print(f"[{w['name']}] Trigger attempt complete (will re-verify next cycle).")

                        # 4. Periodically capture status screenshot and sidecar JSON
                        if cycle % cfg["screenshot_interval_cycles"] == 0:
                            ss_path = artifacts_path / f"{wid}_watchdog.png"
                            page.screenshot(path=str(ss_path))

                            status_data = {
                                "worker_id": wid,
                                "name": w["name"],
                                "account": w["account"],
                                "cycle": cycle,
                                "timestamp": now_str,
                                "running": state["running"],
                                "pending": state["pending"],
                                "status_text": state["statusText"],
                                "progress": current_progress,
                                "reconnect_count": sess["reconnect_count"],
                                "screenshot": str(ss_path),
                            }
                            json_path = artifacts_path / f"{wid}_status.json"
                            with open(json_path, "w", encoding="utf-8") as f:
                                json.dump(status_data, f, indent=2)

                            print(f"[{w['name']}] Saved snapshot to {ss_path.name}")

                    except Exception as err:
                        print(f"[{w['name']}] [ERROR in cycle {cycle}]: {err}")
                        err_str = str(err).lower()
                        if any(k in err_str for k in ["closed", "target", "connection closed", "session"]):
                            print(f"[{w['name']}] Connection lost. Resetting session for next cycle recovery...")
                            try:
                                if sess and not sess.get("is_cdp") and sess.get("ctx"):
                                    sess["ctx"].close()
                            except Exception:
                                pass
                            sessions[wid] = None

                sys.stdout.flush()
                time.sleep(cfg["check_interval_seconds"])

        except KeyboardInterrupt:
            print("\n[WATCHDOG] Stopped by user (KeyboardInterrupt).")
        finally:
            print("[WATCHDOG] Cleaning up sessions...")
            for wid, sess in sessions.items():
                try:
                    if sess:
                        if sess.get("is_cdp"):
                            sess["ctx"].browser.disconnect()
                        elif sess.get("ctx"):
                            sess["ctx"].close()
                        print(f"Closed session for {wid}.")
                except Exception:
                    pass
            print("[WATCHDOG] Closed successfully.")


def main() -> None:
    parser = argparse.ArgumentParser(description="Zchezz Colab active watchdog and keep-alive monitor.")
    parser.add_argument("--worker-ids", nargs="+", default=CONFIG["worker_ids"], help="Worker identifiers (e.g. v331 v507 1 2).")
    parser.add_argument("--interval", type=int, default=CONFIG["check_interval_seconds"], help="Seconds between checks.")
    parser.add_argument("--no-auto-reconnect", action="store_true", help="Disable automatic VM reconnection.")
    parser.add_argument("--headed", action="store_true", help="Run browser in visible headed mode.")
    parser.add_argument("--show-config", action="store_true", help="Display effective configuration and exit.")
    args = parser.parse_args()

    effective_cfg = dict(CONFIG)
    effective_cfg["worker_ids"] = [resolve_worker_key(w) for w in args.worker_ids]
    effective_cfg["check_interval_seconds"] = args.interval
    if args.no_auto_reconnect:
        effective_cfg["auto_reconnect"] = False
    if args.headed:
        effective_cfg["headless"] = False

    if args.show_config:
        print("Effective Configuration:")
        for k, v in effective_cfg.items():
            print(f"  {k}: {v}")
        return

    run_watchdog(effective_cfg)


if __name__ == "__main__":
    main()
