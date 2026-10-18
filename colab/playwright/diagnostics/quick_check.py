"""Quick live inspector for Colab workers 6 and 7."""

import sys as _sys
from pathlib import Path as _Path
_repo_root = _Path(__file__).resolve().parents[3]
if str(_repo_root) not in _sys.path:
    _sys.path.insert(0, str(_repo_root))


import sys
from pathlib import Path
from playwright.sync_api import sync_playwright

REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT))

from colab.config import WORKERS
from colab.playwright.browser_utils import launch_stealth_context, get_notebook_dom_state

def check_all():
    for wid in [6, 7]:
        w = WORKERS[wid]
        print(f"\n=== Checking Worker {wid} ({w['name']} - {w['account']}) ===")
        try:
            with sync_playwright() as p:
                ctx = launch_stealth_context(p, profile_dir=w["profile_dir"], headless=True, cdp_port=w["cdp_port"])
                page = ctx.pages[0] if ctx.pages else ctx.new_page()
                page.goto(w["notebook_url"], timeout=45000)
                dom = get_notebook_dom_state(page, ["EPOCH", "batch", "loss", "Agrupando", "shards", "heartbeat"])
                print(f"Status: {dom['statusText']}")
                print(f"Running: {dom['running']}, Pending: {dom['pending']}")
                if dom.get("outText"):
                    lines = [ln.strip() for ln in dom["outText"].split("\n") if ln.strip()]
                    tail = lines[-6:] if len(lines) >= 6 else lines
                    print("Tail Output:")
                    for line in tail:
                        print("  ", line)
                else:
                    print("Tail Output: (empty)")
                
                snap = REPO_ROOT / "colab" / "artifacts" / f"live_w{wid}.png"
                page.screenshot(path=str(snap))
                ctx.close()
        except Exception as e:
            print(f"Error checking worker {wid}: {e}")

if __name__ == "__main__":
    check_all()
