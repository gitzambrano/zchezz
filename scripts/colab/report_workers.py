"""Comprehensive status inspection, metric parser, and reporting tool for Zchezz Colab workers.

Connects headlessly via Playwright (or live CDP if watchdog is running), gathers
live runtime and cell execution metrics, captures screenshots into artifacts/colab/,
and outputs both terminal and markdown reports. Safe against profile lock collisions.
"""

import argparse
import json
import os
import shutil
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, List

# Ensure scripts root is in path
CURRENT_DIR = Path(__file__).resolve().parent
REPO_ROOT = CURRENT_DIR.parent.parent
if str(CURRENT_DIR) not in sys.path:
    sys.path.insert(0, str(CURRENT_DIR))

from config import WORKERS, resolve_worker_key
from browser_utils import is_cdp_reachable, is_profile_in_use, get_notebook_dom_state, dismiss_modals

CONFIG: Dict[str, Any] = {
    "worker_ids": ["v331", "v507"],
    "headless": True,
    "page_timeout_ms": 60000,
    "load_delay_seconds": 8,
    "artifacts_dir": str(REPO_ROOT / "artifacts" / "colab"),
}


def create_artifacts_dir(dir_path: str) -> Path:
    p = Path(dir_path)
    p.mkdir(parents=True, exist_ok=True)
    return p


def parse_metrics_from_text(text: str) -> Dict[str, Any]:
    """Extract shard, games, positions, and speed metrics from terminal text."""
    import re

    metrics: Dict[str, Any] = {
        "current_shard": "Unknown",
        "games_completed": 0,
        "total_games": 0,
        "positions_generated": 0,
        "speed_nps": "N/A",
        "speed_pps": "N/A",
        "latest_line": "",
    }
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    if not lines:
        return metrics

    metrics["latest_line"] = lines[-1]

    # Shard detection via regex
    shard_matches = re.findall(r'(?:Iniciando Shard:?\s*|Shard\s+)(sp_[a-zA-Z0-9_]+)', text)
    if shard_matches:
        metrics["current_shard"] = shard_matches[-1]
    else:
        for line in reversed(lines):
            if ("shard" in line.lower() or "sp_" in line) and (".bin" in line or "shard:" in line.lower()):
                for token in line.split():
                    if ("sp_" in token) and len(token) > 3:
                        clean_tok = token.replace(".bin", "").replace("'", "").replace('"', '').strip(":,")
                        metrics["current_shard"] = clean_tok
                        break
                if metrics["current_shard"] != "Unknown":
                    break

    # Positions / progress detection via regex
    pos_matches = re.findall(r'([0-9,]+)\s*/\s*([0-9,]+)\s*posi', text, re.IGNORECASE)
    if pos_matches:
        try:
            metrics["positions_generated"] = int(pos_matches[-1][0].replace(",", ""))
        except Exception:
            pass

    # Games progress fallback
    for line in reversed(lines):
        if "progresso:" in line.lower() or "partidas" in line.lower() or "games" in line.lower():
            try:
                for part in line.split("|"):
                    part = part.strip()
                    if "/" in part and "pos" not in part.lower():
                        for token in part.split():
                            if "/" in token and any(c.isdigit() for c in token):
                                g_done, g_tot = token.split("/")[:2]
                                metrics["games_completed"] = int(g_done.replace(",", ""))
                                metrics["total_games"] = int(g_tot.replace(",", ""))
                                break
                    if metrics["positions_generated"] == 0 and ("posic" in part.lower() or "pos" in part.lower()):
                        for token in part.split():
                            if token.replace(",", "").isdigit():
                                metrics["positions_generated"] = int(token.replace(",", ""))
                                break
                if metrics["games_completed"] > 0:
                    break
            except Exception:
                pass

    # Speed parsing
    speed_matches = re.findall(r'([0-9.]+\s*pos/s)', text)
    if speed_matches:
        metrics["speed_pps"] = speed_matches[-1]

    for line in reversed(lines):
        if "pos/s" in line or "nos/s" in line or "nps" in line.lower():
            for token in line.split("|"):
                token = token.strip()
                if "nos/s" in token or "nps" in token.lower():
                    metrics["speed_nps"] = token
                elif "pos/s" in token and metrics["speed_pps"] == "N/A":
                    metrics["speed_pps"] = token
            if metrics["speed_nps"] != "N/A":
                break

    return metrics


def report_single_worker(worker: Dict[str, Any], headless: bool, timeout_ms: int, delay_s: int, artifacts_dir: Path) -> Dict[str, Any]:
    from playwright.sync_api import sync_playwright

    wid = worker["worker_id"]
    name = worker["name"]
    profile = worker["profile_dir"]
    url = worker["notebook_url"]
    account = worker["account"]
    cdp_port = worker["cdp_port"]
    keywords = worker.get("target_keywords", ["Remessa 2", wid])

    record: Dict[str, Any] = {
        "worker_id": wid,
        "name": name,
        "account": account,
        "url": url,
        "connected": False,
        "running": False,
        "pending": False,
        "status_text": "Unknown",
        "current_shard": "Unknown",
        "games_completed": 0,
        "total_games": 0,
        "positions_generated": 0,
        "speed_nps": "N/A",
        "speed_pps": "N/A",
        "latest_line": "",
        "screenshot_path": None,
        "error": None,
    }

    cdp_active = is_cdp_reachable(cdp_port)
    in_use, proc_pid = is_profile_in_use(profile)

    # Fallback to disk artifacts if profile is held by an external process without CDP
    if in_use and not cdp_active:
        record["status_text"] = f"Managed by external process (PID {proc_pid})"
        record["connected"] = True
        record["running"] = True

        # Check for existing watchdog snapshot or sidecar JSON
        json_sidecar = artifacts_dir / f"{wid}_status.json"
        if json_sidecar.exists():
            try:
                with open(json_sidecar, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    record["running"] = data.get("running", True)
                    record["pending"] = data.get("pending", False)
                    record["status_text"] = data.get("status_text", record["status_text"])
                    record["latest_line"] = data.get("progress", "")
            except Exception:
                pass

        # Check existing screenshots
        candidates = [
            artifacts_dir / f"{wid}_watchdog.png",
            artifacts_dir / f"{wid}_report.png",
            REPO_ROOT / "artifacts" / f"{wid}_watchdog_live.png",
            REPO_ROOT / "artifacts" / f"{wid}_remessa2_live_now.png",
        ]
        for c in candidates:
            if c.exists():
                dest = artifacts_dir / f"{wid}_report.png"
                if c != dest:
                    try:
                        shutil.copy2(c, dest)
                    except Exception:
                        pass
                record["screenshot_path"] = str(dest if dest.exists() else c)
                break

        return record

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
                    args=[
                        f"--remote-debugging-port={cdp_port}",
                        "--no-sandbox",
                        "--disable-gpu",
                        "--remote-allow-origins=*",
                    ],
                )
                page = ctx.pages[0] if ctx.pages else ctx.new_page()
                page.goto(url, wait_until="commit", timeout=timeout_ms)
                browser_to_close = ctx

            time.sleep(delay_s)
            dismiss_modals(page)

            dom_state = get_notebook_dom_state(page, keywords)
            record["connected"] = dom_state["kConnected"] or ("RAM" in dom_state["statusText"])
            record["status_text"] = dom_state["statusText"]
            record["running"] = dom_state["running"]
            record["pending"] = dom_state["pending"]

            metrics = parse_metrics_from_text(dom_state["outText"])
            record["current_shard"] = metrics["current_shard"]
            record["games_completed"] = metrics["games_completed"]
            record["total_games"] = metrics["total_games"]
            record["positions_generated"] = metrics["positions_generated"]
            record["speed_nps"] = metrics["speed_nps"]
            record["speed_pps"] = metrics["speed_pps"]
            record["latest_line"] = metrics["latest_line"]

            ss_path = artifacts_dir / f"{wid}_report.png"
            page.screenshot(path=str(ss_path))
            record["screenshot_path"] = str(ss_path)

            if not cdp_active and browser_to_close:
                browser_to_close.close()

    except Exception as exc:
        record["error"] = str(exc)

    return record


def generate_markdown_report(records: List[Dict[str, Any]], artifacts_dir: Path) -> str:
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    md = [
        "# Zchezz Colab Self-Play Worker Report",
        "",
        f"*Generated at: {now_str}*",
        "",
        "| Worker | Account | VM Status | Execution | Shard | Progress | Positions | Speed |",
        "| :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |",
    ]

    for r in records:
        w_name = r["name"]
        account = r["account"]
        vm_status = r["status_text"]
        if r.get("error"):
            exec_status = "Error"
            shard = "N/A"
            prog = f"Error: {r['error'][:40]}"
            pos = "N/A"
            spd = "N/A"
        else:
            exec_status = "Running" if r["running"] else ("Pending" if r["pending"] else "Idle")
            shard = r["current_shard"]
            prog = f"{r['games_completed']}/{r['total_games']}" if r['total_games'] > 0 else (r['latest_line'][:35] or "N/A")
            pos = f"{r['positions_generated']:,}" if r['positions_generated'] > 0 else "N/A"
            spd = r["speed_pps"] if r["speed_pps"] != "N/A" else r["speed_nps"]

        md.append(f"| **{w_name}** | `{account}` | {vm_status} | {exec_status} | {shard} | {prog} | {pos} | {spd} |")

    md.append("")
    md.append("## Worker Visual Screenshots")
    md.append("")

    for r in records:
        if r.get("screenshot_path"):
            rel_path = os.path.relpath(r["screenshot_path"], artifacts_dir.parent)
            md.append(f"### {r['name']} ({r['worker_id']})")
            md.append(f"![{r['name']} Screenshot]({rel_path})")
            md.append("")

    report_path = artifacts_dir / "report.md"
    with open(report_path, "w", encoding="utf-8") as f:
        f.write("\n".join(md))

    return str(report_path)


def main() -> None:
    parser = argparse.ArgumentParser(description="Audit and report Zchezz Colab worker status.")
    parser.add_argument("--worker-ids", nargs="+", default=CONFIG["worker_ids"], help="Worker identifiers (e.g. v331 v507 1 2).")
    parser.add_argument("--headed", action="store_true", help="Run browser in visible headed mode.")
    parser.add_argument("--show-config", action="store_true", help="Display effective configuration and exit.")
    args = parser.parse_args()

    effective_cfg = dict(CONFIG)
    effective_cfg["worker_ids"] = [resolve_worker_key(w) for w in args.worker_ids]
    if args.headed:
        effective_cfg["headless"] = False

    if args.show_config:
        print("Effective Configuration:")
        for k, v in effective_cfg.items():
            print(f"  {k}: {v}")
        return

    artifacts_path = create_artifacts_dir(effective_cfg["artifacts_dir"])

    print("=" * 70)
    print("ZCHEZZ COLAB WORKER AUDIT & REPORT")
    print("=" * 70)

    records: List[Dict[str, Any]] = []
    for wid in effective_cfg["worker_ids"]:
        if wid not in WORKERS:
            continue
        w = WORKERS[wid]
        print(f"Auditing {w['name']} ({wid}, {w['account']})...")
        rec = report_single_worker(
            worker=w,
            headless=effective_cfg["headless"],
            timeout_ms=effective_cfg["page_timeout_ms"],
            delay_s=effective_cfg["load_delay_seconds"],
            artifacts_dir=artifacts_path,
        )
        records.append(rec)

        if rec.get("error"):
            print(f"  [ERROR] {rec['error']}")
        else:
            tag = "[RUNNING]" if rec["running"] else ("[PENDING]" if rec["pending"] else "[IDLE]")
            print(f"  Status: {tag} (VM: {rec['status_text']})")
            if rec.get("latest_line"):
                print(f"  Output: {rec['latest_line'][:90]}")
            if rec.get("screenshot_path"):
                print(f"  Screenshot saved: {rec['screenshot_path']}")

    report_file = generate_markdown_report(records, artifacts_path)
    print("\n" + "-" * 70)
    with open(report_file, "r", encoding="utf-8") as f:
        print(f.read())
    print("-" * 70)
    print(f"Markdown report generated: {report_file}")


if __name__ == "__main__":
    main()
