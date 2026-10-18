"""Connect Colab runtimes, ensure T4 GPU, run training cell, and handle Drive dialogs."""

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

def ensure_worker_running(wid: int):
    w = WORKERS[wid]
    profile = w.get("profile", "v331" if wid == 6 else "v507")
    print(f"\n=======================================================")
    print(f" Connecting and Starting Worker {wid} ({w['name']} - Profile: {profile})")
    print(f"=======================================================")

    with sync_playwright() as p:
        ctx = p.chromium.launch_persistent_context(
            user_data_dir=w["profile_dir"],
            headless=True,
            channel="chrome",
            args=[f"--remote-debugging-port={w['cdp_port']}", "--no-sandbox"],
        )
        page = ctx.pages[0] if ctx.pages else ctx.new_page()
        page.goto(w["notebook_url"], timeout=45000)
        time.sleep(8)
        dismiss_modals(page)

        # Handle OAuth popups
        ctx.on("page", lambda p_new: handle_google_oauth_popup(p_new, w["account"]))

        # Step 1: Click connect button if needed
        print("Checking connection status...")
        for attempt in range(12):
            dismiss_modals(page)
            btn = page.locator("colab-connect-button").first
            btn_text = btn.inner_text() if btn.count() > 0 else ""
            if "ram" in btn_text.lower() or "disco" in btn_text.lower() or "disk" in btn_text.lower():
                print(f"Runtime is fully connected: {btn_text}")
                break
            print(f"Attempt {attempt+1}/12: Status is '{btn_text}'. Clicking connect...")
            if btn.count() > 0:
                btn.click()
            time.sleep(6)

        # Step 2: Ensure Cell 0 code is correct
        code = f'''from google.colab import drive
import os

if not os.path.exists('/content/drive/MyDrive'):
    drive.mount('/content/drive')

if not os.path.exists('/content/Zchezz'):
    !git clone https://github.com/gitzambrano/zchezz.git /content/Zchezz

%cd /content/Zchezz
!git fetch origin main
!git reset --hard origin/main
!pip -q install python-chess numpy torch
!PROFILE={profile} EPOCHS=100 LR=1e-5 ETA_MIN=1e-7 K=0.1 bash colab/run_train_colab.sh
'''
        page.evaluate("""(code) => {
            const nb = colab.global.notebook;
            if (!nb || !nb.cells || nb.cells.length === 0) return;
            const c0 = nb.cells[0];
            const cur = c0.getText ? c0.getText() : (c0.model ? c0.model.getText() : '');
            if (!cur.includes('run_train_colab.sh')) {
                if (c0.setText) c0.setText(code);
                else if (c0.model && c0.model.setText) c0.model.setText(code);
            }
        }""", code)
        time.sleep(2)

        # Step 3: Check if already running; if not, click run
        is_running = page.evaluate("""() => {
            const nb = colab.global.notebook;
            if (nb && nb.isExecuting && nb.isExecuting()) return true;
            const btn = document.querySelector('colab-run-button');
            if (btn) {
                const label = (btn.getAttribute('aria-label') || '').toLowerCase();
                if (label.includes('interromper') || label.includes('interrupt') || label.includes('stop')) return true;
            }
            return false;
        }""")
        if is_running:
            print("Cell 0 is ALREADY executing!")
        else:
            print("Cell 0 is not running. Clicking run button...")
            run_btn = page.locator("colab-run-button").first
            if run_btn.is_visible():
                run_btn.click(force=True)
            else:
                page.keyboard.press("Control+Enter")
            print("Triggered execution.")

        time.sleep(8)
        dismiss_modals(page)

        # Step 4: Handle Drive dialog if visible
        for _ in range(5):
            clicked = page.evaluate("""() => {
                const btns = Array.from(document.querySelectorAll('button, md-text-button, mwc-button'));
                for (const b of btns) {
                    const txt = (b.innerText || '').toLowerCase();
                    if (txt.includes('conectar ao google drive') || txt.includes('permitir') || txt.includes('connect to google drive')) {
                        b.click();
                        return true;
                    }
                }
                return false;
            }""")
            if clicked:
                print("Clicked Drive permission button!")
                time.sleep(4)
                break
            time.sleep(2)

        snap = REPO_ROOT / "colab" / "artifacts" / f"worker_{wid}_active.png"
        page.screenshot(path=str(snap))
        print(f"Screenshot saved to {snap}")
        ctx.close()

if __name__ == "__main__":
    for wid in [6, 7]:
        try:
            ensure_worker_running(wid)
        except Exception as e:
            print(f"Error on Worker {wid}: {e}")
