"""Observe notebook progress without reconnect or execution actions."""
import argparse
import json
from pathlib import Path
import re
import sys
import time

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from colab.config import WORKERS
from colab.monitoring import CONFIG as MONITOR_CONFIG, display, evaluate, merge_report, read_report, write_report
from colab.playwright.browser_utils import is_cdp_reachable
from colab.playwright.sessions import cdp_url
from colab.control import file_lease

CONFIG = {**MONITOR_CONFIG, "worker_ids": list(WORKERS), "output": ROOT / "artifacts/colab/playwright/monitor.json", "open_profiles": False}


def progress_from_text(text):
    """Select the last complete progress line from notebook output."""
    patterns = (
        r"Generated\s+(\d+)/(\d+)\s+positions",
        r"progresso:\s*(\d+)/(\d+)\s+partidas\s*\|\s*(\d+)\s+posicoes",
        r"(?i)epoch\s+(\d+)\s*/\s*(\d+)",
        r"(?i)games\s+(\d+)\s*/\s*(\d+)\s+positions\s+(\d+)",
    )
    found = []
    for pattern in patterns:
        found.extend((match.start(), match) for match in re.finditer(pattern, text))
    if not found:
        return {}
    match = max(found, key=lambda item: item[0])[1]
    return {"line": match.group(0), "current": int(match[1]), "total": int(match[2])}


def probe(page, worker):
    """Read the notebook DOM without cell or runtime changes."""
    text = page.locator("body").inner_text(timeout=10000)
    state = page.evaluate("""() => {
        const notebook = globalThis.colab?.global?.notebook;
        return {busy: Boolean(notebook?.kernel?.isBusy?.()),
                connected: Boolean(notebook?.kernel?.isConnected?.())};
    }""")
    progress = progress_from_text(text)
    return {"worker_id": worker, "account": WORKERS[worker]["account"],
            "status": "connected" if state["connected"] else "disconnected",
            "identity": page.url, "busy": state["busy"], "progress": progress,
            "checkpoint_status": "not_checked", "completed": bool(progress and progress["current"] >= progress["total"] and not state["busy"]),
            "artifacts": [], "checkpoints": []}


def run(config):
    from playwright.sync_api import sync_playwright
    if config["interval"] <= 0 or config["stall_seconds"] <= 0:
        raise ValueError("Monitor intervals must be positive.")
    with file_lease(config["output"].with_suffix(".lock")), sync_playwright() as playwright:
        pages, owned_contexts = {}, []
        cycle = 0
        try:
            while True:
                previous = read_report(config["output"])
                snapshots = []
                for worker in config["worker_ids"]:
                    try:
                        page = pages.get(worker)
                        if page is None or page.is_closed():
                            settings = WORKERS[worker]
                            address = cdp_url(settings)
                            if address:
                                browser = playwright.chromium.connect_over_cdp(address, timeout=10000)
                                context = browser.contexts[0]
                            elif config["open_profiles"]:
                                context = playwright.chromium.launch_persistent_context(settings["profile_dir"], channel="chrome", headless=True,
                                    args=[f"--remote-debugging-port={settings['cdp_port']}"])
                                owned_contexts.append(context)
                            else:
                                raise RuntimeError("browser_unavailable")
                            page = next((pg for pg in context.pages if pg.url == settings["notebook_url"]), None)
                            if page is None:
                                page = context.new_page()
                                page.goto(settings["notebook_url"], wait_until="domcontentloaded", timeout=45000)
                                page.wait_for_timeout(8000)
                            pages[worker] = page
                        snapshots.append(probe(page, worker))
                    except Exception as error:
                        snapshots.append({"worker_id": worker, "status": "browser_unavailable", "error_type": type(error).__name__})
                        pages.pop(worker, None)
                now = time.time()
                updates = {str(s["worker_id"]): evaluate(s, previous.get("workers", {}).get(str(s["worker_id"]), {}),
                           now=now, stall_seconds=config["stall_seconds"]) for s in snapshots}
                report = merge_report(previous, updates, now=now, backend="playwright")
                write_report(config["output"], report)
                display(updates)
                cycle += 1
                if config["max_cycles"] and cycle >= config["max_cycles"]:
                    return report
                time.sleep(config["interval"])
        finally:
            for context in owned_contexts:
                context.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--worker-ids", nargs="+", type=int, choices=list(WORKERS), default=CONFIG["worker_ids"])
    parser.add_argument("--interval", type=float, default=CONFIG["interval"])
    parser.add_argument("--stall-seconds", type=float, default=CONFIG["stall_seconds"])
    parser.add_argument("--max-cycles", type=int, default=CONFIG["max_cycles"])
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--open-profiles", action="store_true", default=CONFIG["open_profiles"])
    parser.add_argument("--output", type=Path, default=CONFIG["output"])
    parser.add_argument("--show-config", action="store_true")
    args = parser.parse_args()
    if args.show_config:
        print(json.dumps(CONFIG, default=str, indent=2))
        return
    config = {**CONFIG, **{key: value for key, value in vars(args).items() if key != "once"}}
    if args.once:
        config["max_cycles"] = 1
    try:
        run(config)
    except KeyboardInterrupt:
        print("Monitor stopped. Remote tasks remain active.")


if __name__ == "__main__":
    main()
