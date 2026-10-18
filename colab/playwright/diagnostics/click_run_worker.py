"""Click run button on a Colab notebook and handle OAuth/consent modals."""

import sys as _sys
from pathlib import Path as _Path
_repo_root = _Path(__file__).resolve().parents[3]
if str(_repo_root) not in _sys.path:
    _sys.path.insert(0, str(_repo_root))


import sys
import time
from pathlib import Path
from playwright.sync_api import sync_playwright

REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT))

from colab.config import WORKERS
from colab.playwright.browser_utils import dismiss_modals, handle_google_oauth_popup

def run_cell_on_worker(wid: int):
    w = WORKERS[wid]
    print(f"=== Triggering Run on Worker {wid} ({w['name']} - {w['account']}) ===")
    with sync_playwright() as p:
        ctx = p.chromium.launch_persistent_context(
            user_data_dir=w["profile_dir"],
            headless=True,
            channel="chrome",
            args=[f"--remote-debugging-port={w['cdp_port']}", "--no-sandbox"],
        )
        page = ctx.pages[0] if ctx.pages else ctx.new_page()
        page.goto(w["notebook_url"], timeout=45000)
        time.sleep(6)
        dismiss_modals(page)

        # Listen for Google OAuth popup
        ctx.on("page", lambda p_new: handle_google_oauth_popup(p_new, w["account"]))

        # Click the run button of Cell 0
        btn = page.locator("colab-run-button").first
        if btn.is_visible():
            btn.click()
            print("Clicked colab-run-button directly!")
        else:
            page.keyboard.press("Control+Enter")
            print("Pressed Control+Enter!")

        time.sleep(6)
        dismiss_modals(page)

        # Check for Google Drive authorization modal
        for _ in range(8):
            dismiss_modals(page)
            clicked = page.evaluate("""() => {
                let hit = false;
                const btns = Array.from(document.querySelectorAll('button, md-text-button, mwc-button, [role="button"]'));
                for (const b of btns) {
                    const txt = (b.innerText || '').toLowerCase();
                    if (txt.includes('conectar ao google drive') || txt.includes('connect to google drive') || txt.includes('permitir') || txt.includes('allow')) {
                        b.click();
                        hit = true;
                    }
                }
                return hit;
            }""")
            if clicked:
                print("Clicked Drive authorization button in DOM!")
            time.sleep(3)

        snap = REPO_ROOT / "colab" / "artifacts" / f"train_w{wid}_running.png"
        page.screenshot(path=str(snap))
        print(f"Screenshot saved to {snap}")
        ctx.close()

if __name__ == "__main__":
    wid = int(sys.argv[1]) if len(sys.argv) > 1 else 6
    run_cell_on_worker(wid)
