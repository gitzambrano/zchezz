"""Restart Colab 6 session and run fresh training on Cell 0."""

import sys as _sys
from pathlib import Path as _Path
_repo_root = _Path(__file__).resolve().parents[3]
if str(_repo_root) not in _sys.path:
    _sys.path.insert(0, str(_repo_root))


import time
from playwright.sync_api import sync_playwright
import sys
from pathlib import Path

CURRENT_DIR = Path(__file__).resolve().parent
REPO_ROOT = CURRENT_DIR.parent.parent.parent
if str(CURRENT_DIR) not in sys.path:
    sys.path.insert(0, str(CURRENT_DIR))

from colab.config import WORKERS
from colab.playwright.browser_utils import launch_stealth_context, dismiss_modals

w = WORKERS[6]
profile = "v331"

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

print("Connecting to Colab 6...")
with sync_playwright() as p:
    ctx = launch_stealth_context(p, profile_dir=w["profile_dir"], headless=True, cdp_port=w["cdp_port"])
    page = ctx.pages[0] if ctx.pages else ctx.new_page()
    page.goto(w["notebook_url"], wait_until="commit", timeout=45000)
    time.sleep(8)
    dismiss_modals(page)

    # 1. Restart session to cancel any lingering selfplay execution
    print("Restarting session to clear hanging cells...")
    menu = page.locator('div[id="runtime-menu-button"]').or_(page.locator('text="Ambiente de execução"')).first
    if menu.is_visible():
        menu.click()
        time.sleep(1.5)
        restart_btn = page.locator('text="Reiniciar sessão"').or_(page.locator('text="Restart session"')).first
        if restart_btn.is_visible():
            restart_btn.click()
            time.sleep(2)
            # Confirm dialog
            page.evaluate("""() => {
                const btns = Array.from(document.querySelectorAll('mwc-button, md-text-button, button'));
                const ok = btns.find(b => b.innerText && (['Sim', 'Reiniciar', 'Yes', 'Restart'].includes(b.innerText.trim())));
                if (ok) ok.click();
            }""")
            print("Confirmed restart session!")
            time.sleep(5)
            dismiss_modals(page)

    # 2. Wait for kernel to be ready
    print("Waiting for kernel ready...")
    time.sleep(6)
    dismiss_modals(page)

    # 3. Set code on Cell 0
    print("Setting training code on Cell 0...")
    page.evaluate("""(code) => {
        const nb = typeof colab !== 'undefined' && colab.global ? colab.global.notebook : null;
        if (!nb || !nb.cells || nb.cells.length === 0) return;

        const cell = nb.cells[0];
        if (cell.model && cell.model.setText) cell.model.setText(code);
        if (cell.model && cell.model.removeOutputs) cell.model.removeOutputs();

        // Find cell editor model
        if (typeof monaco !== 'undefined') {
            const models = monaco.editor.getModels();
            for (const m of models) {
                const val = m.getValue();
                if (val.includes('Célula') || val.includes('zchezz') || val.includes('drive.mount') || val.includes('PROFILE')) {
                    m.setValue(code);
                }
            }
        }

        // Trigger execution
        if (typeof cell.manualExecute === 'function') {
            cell.manualExecute();
        }
    }""", code)

    print("Cell 0 triggered! Monitoring for 20s...")
    time.sleep(15)
    dismiss_modals(page)

    page.screenshot(path="colab/artifacts/colab_6_fresh_start.png")
    print("Screenshot saved to colab/artifacts/colab_6_fresh_start.png")
    ctx.close()
