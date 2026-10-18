"""Approve Google Drive modal and OAuth popup on Colab workers."""

import sys as _sys
from pathlib import Path as _Path
_repo_root = _Path(__file__).resolve().parents[3]
if str(_repo_root) not in _sys.path:
    _sys.path.insert(0, str(_repo_root))


import sys
import time
from pathlib import Path
from playwright.sync_api import sync_playwright

CURRENT_DIR = Path(__file__).resolve().parent
REPO_ROOT = CURRENT_DIR.parent.parent.parent
if str(CURRENT_DIR) not in sys.path:
    sys.path.insert(0, str(CURRENT_DIR))

from colab.config import WORKERS
from colab.playwright.browser_utils import dismiss_modals, handle_google_oauth_popup


def approve_worker(worker_id: int):
    w = WORKERS[worker_id]
    print(f"Connecting to handle Drive modal on {w['name']} ({w['account']})...")
    with sync_playwright() as p:
        ctx = p.chromium.launch_persistent_context(
            user_data_dir=w["profile_dir"],
            headless=True,
            channel="chrome",
            args=[f"--remote-debugging-port={w['cdp_port']}", "--no-sandbox"],
        )
        page = ctx.pages[0] if ctx.pages else ctx.new_page()
        page.goto(w["notebook_url"], wait_until="commit", timeout=45000)
        time.sleep(6)

        # Listen for popups
        ctx.on("page", lambda p_new: handle_google_oauth_popup(p_new, w["account"]))

        btn = page.locator("text='Conectar ao Google Drive'").or_(page.locator("text='Connect to Google Drive'")).first
        if btn.is_visible():
            print("Found 'Conectar ao Google Drive' button! Clicking...")
            try:
                with ctx.expect_page(timeout=10000) as popup_info:
                    btn.click()
                popup = popup_info.value
                print("Popup opened:", popup.url)
                handle_google_oauth_popup(popup, w["account"])
                print("OAuth handled!")
            except Exception as e:
                print("Popup handling:", e)
                btn.click()
        else:
            print("Modal button not visible, running dismiss_modals...")
            dismiss_modals(page)

        time.sleep(10)
        screenshot_path = REPO_ROOT / "artifacts" / "colab" / "playwright" / f"colab_{worker_id}_approved.png"
        page.screenshot(path=str(screenshot_path))
        print(f"Screenshot saved to {screenshot_path}")
        ctx.close()


if __name__ == "__main__":
    wid = int(sys.argv[1]) if len(sys.argv) > 1 else 7
    approve_worker(wid)
