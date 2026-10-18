"""Set training code, trigger run, and immediately approve any Google Drive modals."""

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


def run_training_worker(worker_id: int):
    w = WORKERS[worker_id]
    profile = w.get("profile", "v507")

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

    print(f"Connecting to {w['name']} ({w['account']}) to start training...")
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
        dismiss_modals(page)

        # Listen for Google OAuth popups
        ctx.on("page", lambda p_new: handle_google_oauth_popup(p_new, w["account"]))

        # Inject code into Cell 0 and execute
        print(f"Injecting code for profile {profile} into Cell 0...")
        page.evaluate("""(code) => {
            const nb = colab.global.notebook;
            const cell = nb.cells[0];
            if (cell.setText) cell.setText(code);
            else if (cell.model && cell.model.setText) cell.model.setText(code);

            if (typeof monaco !== 'undefined') {
                const models = monaco.editor.getModels();
                if (models && models.length > 0) models[0].setValue(code);
            }

            if (typeof cell.manualExecute === 'function') {
                cell.manualExecute();
            }
        }""", code)

        print("Cell 0 triggered. Monitoring for Drive mount modals...")
        # Check every 2s for 30s to catch and click 'Conectar ao Google Drive'
        for i in range(15):
            time.sleep(2)
            btn = page.locator("text='Conectar ao Google Drive'").or_(page.locator("text='Connect to Google Drive'")).first
            if btn.is_visible():
                print("Drive mount modal appeared! Clicking Conectar ao Google Drive...")
                try:
                    with ctx.expect_page(timeout=10000) as popup_info:
                        btn.click()
                    popup = popup_info.value
                    print("Popup opened:", popup.url)
                    handle_google_oauth_popup(popup, w["account"])
                    print("OAuth approved!")
                except Exception as e:
                    print("Popup exception (might have auto-approved):", e)
                    btn.click()
                break
            dismiss_modals(page)

        time.sleep(10)
        dismiss_modals(page)

        screenshot_path = REPO_ROOT / "artifacts" / "colab" / "playwright" / f"colab_{worker_id}_training_started.png"
        page.screenshot(path=str(screenshot_path))
        print(f"Screenshot saved to {screenshot_path}")

        # Check output
        out = page.evaluate("""() => {
            const nb = colab.global.notebook;
            const cell = nb.cells[0];
            return cell.output_ ? cell.output_.innerText : '';
        }""")
        if out:
            print("Cell output:\n", out[-500:])

        ctx.close()


if __name__ == "__main__":
    wid = int(sys.argv[1]) if len(sys.argv) > 1 else 7
    run_training_worker(wid)
