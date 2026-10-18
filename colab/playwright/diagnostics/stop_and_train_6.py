"""Stop running selfplay cell and immediately trigger training on Colab 6."""

import sys as _sys
from pathlib import Path as _Path
_repo_root = _Path(__file__).resolve().parents[3]
if str(_repo_root) not in _sys.path:
    _sys.path.insert(0, str(_repo_root))


import time
import sys
from pathlib import Path
from playwright.sync_api import sync_playwright

CURRENT_DIR = Path(__file__).resolve().parent
REPO_ROOT = CURRENT_DIR.parent.parent.parent
if str(CURRENT_DIR) not in sys.path:
    sys.path.insert(0, str(CURRENT_DIR))

from colab.config import WORKERS
from colab.playwright.browser_utils import launch_stealth_context, dismiss_modals, get_notebook_dom_state

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

    # 1. Stop any currently executing cell
    print("Stopping any running cell...")
    stopped = page.evaluate("""() => {
        const nb = typeof colab !== 'undefined' && colab.global ? colab.global.notebook : null;
        if (!nb || !nb.cells) return 'no notebook';

        // Check each cell for running state or stop button
        let stoppedCount = 0;
        for (let i = 0; i < nb.cells.length; i++) {
            const c = nb.cells[i];
            const elem = c.getElement ? c.getElement() : (c.element_ || c.dom_);
            if (c.isRunning && c.isRunning()) {
                if (typeof c.interrupt === 'function') c.interrupt();
                stoppedCount++;
            }
            if (elem) {
                const btn = elem.querySelector('colab-run-button');
                if (btn) {
                    const inner = btn.shadowRoot ? btn.shadowRoot.querySelector('button, [role="button"]') : btn;
                    if (inner) {
                        const title = (inner.getAttribute('title') || inner.getAttribute('aria-label') || '').toLowerCase();
                        if (title.includes('interromper') || title.includes('cancelar') || title.includes('stop') || title.includes('interrupt')) {
                            inner.click();
                            stoppedCount++;
                        }
                    }
                }
            }
        }
        if (typeof nb.interruptKernel === 'function') {
            nb.interruptKernel();
        }
        return stoppedCount;
    }""")
    print("Stopped count:", stopped)

    # Mouse click on stop button coordinate as fallback (x=96, y=445)
    page.mouse.click(96, 445)
    time.sleep(4)
    dismiss_modals(page)

    # 2. Set training code on Cell 0
    print("Setting training code on Cell 0...")
    page.evaluate("""(code) => {
        const nb = typeof colab !== 'undefined' && colab.global ? colab.global.notebook : null;
        if (!nb || !nb.cells || nb.cells.length === 0) return;

        const cell = nb.cells[0];
        if (cell.model && cell.model.setText) cell.model.setText(code);
        if (cell.model && cell.model.removeOutputs) cell.model.removeOutputs();

        if (typeof monaco !== 'undefined') {
            const models = monaco.editor.getModels();
            if (models && models.length > 0) {
                models[0].setValue(code);
            }
        }

        // Execute Cell 0
        if (typeof cell.manualExecute === 'function') {
            cell.manualExecute();
        } else {
            const elem = cell.getElement ? cell.getElement() : (cell.element_ || cell.dom_);
            if (elem) {
                const btn = elem.querySelector('colab-run-button');
                if (btn) btn.click();
            }
        }
    }""", code)

    # Also click run button on Cell 0 at coordinate (x=96, y=175)
    page.mouse.click(96, 175)
    print("Cell 0 triggered! Monitoring for 25s...")
    time.sleep(20)
    dismiss_modals(page)

    dom = get_notebook_dom_state(page, ["v331", "EPOCH", "run_train_colab.sh", "heartbeat"])
    print(f"Post-run DOM Status: {dom['statusText']}")
    print(f"Running: {dom['running']}, Pending: {dom['pending']}")
    if dom.get("outText"):
        print("Recent Output:\n", dom["outText"][-800:])

    page.screenshot(path="colab/artifacts/colab_6_stopped_and_trained.png")
    print("Screenshot saved to colab/artifacts/colab_6_stopped_and_trained.png")
    ctx.close()
