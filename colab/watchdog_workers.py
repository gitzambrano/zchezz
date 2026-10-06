"""Continuous watchdog and keep-alive monitor for Google Colab self-play workers in Zchezz.

Maintains active persistent browser sessions with periodic micro-interactions to
prevent Colab idle disconnects. Detects session disconnects, automatically reconnects,
re-triggers the resilient bootloader cell, and saves periodic status screenshots and metrics.
"""

import argparse
import json
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, List, Optional

# Ensure colab root is in path
CURRENT_DIR = Path(__file__).resolve().parent
REPO_ROOT = CURRENT_DIR.parent
if str(CURRENT_DIR) not in sys.path:
    sys.path.insert(0, str(CURRENT_DIR))

from config import WORKERS, BOOTLOADER_TEMPLATE
from browser_utils import (
    is_cdp_reachable,
    is_profile_in_use,
    dismiss_modals,
    handle_google_oauth_popup,
    connect_runtime_if_needed,
    get_notebook_dom_state,
    trigger_cell_execution,
    launch_stealth_context,
    save_profile_cookies,
)
from human_actions import random_human_idle

CONFIG: Dict[str, Any] = {
    "worker_ids": [6, 7],
    "check_interval_seconds": 60,
    "screenshot_interval_cycles": 10,
    "auto_reconnect": True,
    "headless": True,
    "page_timeout_ms": 60000,
    "artifacts_dir": str(CURRENT_DIR / "artifacts"),
}


def create_artifacts_dir(dir_path: str) -> Path:
    p = Path(dir_path)
    p.mkdir(parents=True, exist_ok=True)
    return p


def init_worker_session(p: Any, worker: Dict[str, Any], headless: bool, timeout_ms: int) -> Optional[Dict[str, Any]]:
    """Initialize or attach to a persistent browser session for a Colab worker."""
    wid = worker["worker_id"]
    cdp_port = worker.get("cdp_port", 9000 + wid)
    print(f"Initializing session for {worker['name']} (Worker #{wid})...", flush=True)

    cdp_active = is_cdp_reachable(cdp_port)
    in_use, proc_pid = is_profile_in_use(worker["profile_dir"])

    if in_use and not cdp_active:
        print(f"  [WARN] Profile for {worker['name']} is locked by external process PID {proc_pid}.", flush=True)
        return None

    try:
        if cdp_active:
            print(f"  Attaching over live CDP on port {cdp_port}...", flush=True)
            browser = p.chromium.connect_over_cdp(f"http://127.0.0.1:{cdp_port}", timeout=15000)
            ctx = browser.contexts[0] if browser.contexts else browser.new_context()

            colab_page = None
            to_close = []
            for pg in ctx.pages:
                url = pg.url or ""
                if "colab.research.google.com" in url:
                    colab_page = pg
                elif "accounts.google.com" in url or "about:blank" in url:
                    to_close.append(pg)
            for pg in to_close:
                try:
                    pg.close()
                except Exception:
                    pass

            if not colab_page:
                colab_page = ctx.new_page()
                colab_page.goto(worker["notebook_url"], wait_until="commit", timeout=timeout_ms)
            page = colab_page
            is_cdp = True
        else:
            ctx = launch_stealth_context(
                p,
                profile_dir=worker["profile_dir"],
                headless=headless,
                cdp_port=cdp_port,
                extra_args=["--disable-gpu"],
            )
            page = ctx.pages[0] if ctx.pages else ctx.new_page()
            page.goto(worker["notebook_url"], wait_until="commit", timeout=timeout_ms)
            is_cdp = False

        try:
            page.set_default_timeout(30000)
        except Exception:
            pass

        print(f"  Connected to {worker['name']}.", flush=True)
        return {
            "worker": worker,
            "ctx": ctx,
            "page": page,
            "is_cdp": is_cdp,
            "reconnect_count": 0,
            "last_progress": "Initializing...",
        }
    except Exception as exc:
        print(f"  [ERROR] Failed to initialize {worker['name']}: {exc}", flush=True)
        return None


def run_watchdog_inner(cfg: Dict[str, Any], artifacts_path: Path, worker_ids: List[int]) -> bool:
    from playwright.sync_api import sync_playwright
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
        sessions: Dict[int, Optional[Dict[str, Any]]] = {}

        # 1. Initialize persistent contexts or attach via CDP
        for wid in worker_ids:
            sessions[wid] = init_worker_session(p, WORKERS[wid], cfg["headless"], cfg["page_timeout_ms"])

        if not any(sessions.values()):
            print("[WATCHDOG] No sessions could be initialized. Retrying in main loop...")

        time.sleep(10)
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
                    is_dead = False
                    if sess is None or sess.get("page") is None:
                        is_dead = True
                    else:
                        try:
                            is_dead = sess["page"].is_closed()
                        except Exception:
                            is_dead = True

                    if is_dead:
                        print(f"[{w['name']}] Session missing or closed. Recovering...", flush=True)
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
                    keywords = w.get("target_keywords", ["run_colab_worker.py", "selfplay_targeted_weakness", "selfplay_15m", "zquoridor"])

                    try:
                        # Handle OAuth consent or close extraneous background popups
                        if sess.get("ctx"):
                            for pg in list(sess["ctx"].pages):
                                if pg != page and not pg.is_closed():
                                    if "accounts.google.com" in (pg.url or ""):
                                        print(f"[{w['name']}] OAuth popup detected. Handling consent...", flush=True)
                                        handle_google_oauth_popup(pg, w.get("account"))
                                    elif "about:blank" in (pg.url or ""):
                                        try:
                                            pg.close()
                                        except Exception:
                                            pass

                        dismiss_modals(page)

                        # Extract state from Colab DOM
                        state = get_notebook_dom_state(page, keywords)

                        # Extract clean progress line
                        lines = [line.strip() for line in state["outText"].splitlines() if line.strip()]
                        progress_lines = [
                            l for l in lines
                            if any(kw in l.lower() for kw in [
                                "progresso", "shard", "games", "jogos", "selfplay",
                                "iniciando", "pular", "positions", "posições", "posicoes",
                                "meta atingida", "total acumulado", "meta", "ok:", "pos/s", "j/s", "pts:"
                            ]) and not l.startswith("gcc ") and not l.startswith("make")
                        ]
                        current_progress = progress_lines[-1] if progress_lines else (lines[-1] if lines else "No output")
                        sess["last_progress"] = current_progress

                        # Keep-alive micro interaction: human-like glide and subtle scroll via Fitts & Bezier
                        try:
                            random_human_idle(page)
                        except Exception:
                            page.mouse.move(60 + (cycle % 40), 60 + (cycle % 40))

                        run_tag = "[RUNNING]" if state["running"] else ("[PENDING]" if state["pending"] else "[IDLE]")
                        print(f"[{w['name']}] {run_tag} (VM: {state['statusText']}) -> {current_progress[:90]}", flush=True)

                        # 3. Auto-reconnect or bootstrap if idle and not running
                        if cfg["auto_reconnect"] and not state["running"] and not state["pending"]:
                            is_completed = any(
                                k in state["outText"].lower()
                                for k in ["meta atingida", "target reached", "meta completada"]
                            )
                            if is_completed:
                                print(f"[{w['name']}] [COMPLETED] Target positions reached. Standing by.", flush=True)
                            else:
                                st_lower = state["statusText"].lower()
                                if not any(k in st_lower for k in ["conectando", "connecting", "alocando"]):
                                    if any(k in st_lower for k in ["conectar", "reconectar", "connect", "reconnect"]):
                                        print(f"[{w['name']}] [DISCONNECTED ({state['statusText']})] Connecting VM...", flush=True)
                                        sess["reconnect_count"] += 1
                                        connect_runtime_if_needed(page)
                                        time.sleep(12)

                                    print(f"[{w['name']}] Triggering cell execution...", flush=True)
                                    tmpl = w.get("bootloader_template", BOOTLOADER_TEMPLATE)
                                    ok = trigger_cell_execution(page, w, tmpl, target_keywords=keywords)
                                    if ok:
                                        print(f"[{w['name']}] Triggered execution successfully.", flush=True)
                                    else:
                                        print(f"[{w['name']}] Trigger attempt complete (will re-verify next cycle).", flush=True)

                        # 4. Periodic health screenshot and status sidecar
                        if cycle % cfg["screenshot_interval_cycles"] == 0 or cycle == 1:
                            shot_file = artifacts_path / f"colab_{wid}_watchdog.png"
                            try:
                                page.screenshot(path=str(shot_file), timeout=5000)
                            except Exception:
                                pass
                            save_profile_cookies(sess["ctx"], w["profile_dir"])

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
                                "screenshot": str(shot_file),
                            }
                            json_path = artifacts_path / f"colab_{wid}_status.json"
                            with open(json_path, "w", encoding="utf-8") as f:
                                json.dump(status_data, f, indent=2)

                            print(f"[{w['name']}] Saved snapshot to {shot_file.name}", flush=True)

                    except Exception as err:
                        print(f"[{w['name']}] [ERROR in cycle {cycle}]: {err}", flush=True)
                        err_str = str(err).lower()
                        if any(k in err_str for k in ["closed", "target", "connection closed", "session", "timeout"]):
                            print(f"[{w['name']}] Connection lost or timed out. Resetting session for next cycle recovery...", flush=True)
                            try:
                                if sess and not sess.get("is_cdp") and sess.get("ctx"):
                                    sess["ctx"].close()
                            except Exception:
                                pass
                            sessions[wid] = None

                sys.stdout.flush()
                time.sleep(cfg["check_interval_seconds"])

        except KeyboardInterrupt:
            print("\n[WATCHDOG] Interrupted by user. Closing sessions cleanly...")
            return False
        except Exception as loop_err:
            print(f"\n[WATCHDOG LOOP EXCEPTION]: {loop_err}", flush=True)
            return True
        finally:
            for wid, sess in sessions.items():
                try:
                    if sess:
                        if sess.get("is_cdp"):
                            if sess.get("ctx") and sess["ctx"].browser:
                                sess["ctx"].browser.close()
                        elif sess.get("ctx"):
                            sess["ctx"].close()
                        print(f"Closed session for Worker #{wid}.")
                except Exception:
                    pass
            print("[WATCHDOG] Sessions released.")

    return True


def run_watchdog(cfg: Dict[str, Any]) -> None:
    artifacts_path = create_artifacts_dir(cfg["artifacts_dir"])
    worker_ids = [wid for wid in cfg["worker_ids"] if wid in WORKERS]
    if not worker_ids:
        print("[WATCHDOG] No valid worker IDs configured.")
        return

    while True:
        try:
            should_retry = run_watchdog_inner(cfg, artifacts_path, worker_ids)
            if not should_retry:
                break
        except KeyboardInterrupt:
            print("\n[WATCHDOG] Terminated by user.")
            break
        except Exception as outer_err:
            print(f"\n[WATCHDOG DRIVER EXCEPTION]: {outer_err}. Re-initializing in 15 seconds...", flush=True)
        time.sleep(15)


def main() -> None:
    parser = argparse.ArgumentParser(description="Zchezz Colab active watchdog and keep-alive monitor.")
    parser.add_argument("--worker-ids", type=int, nargs="+", default=CONFIG["worker_ids"], help="Worker IDs (e.g. 3 4 5).")
    parser.add_argument("--interval", type=int, default=CONFIG["check_interval_seconds"], help="Seconds between checks.")
    parser.add_argument("--no-auto-reconnect", action="store_true", help="Disable automatic VM reconnection.")
    parser.add_argument("--headed", action="store_true", help="Run browser in visible headed mode.")
    parser.add_argument("--show-config", action="store_true", help="Display effective configuration and exit.")
    args = parser.parse_args()

    effective_cfg = dict(CONFIG)
    effective_cfg["worker_ids"] = args.worker_ids
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
