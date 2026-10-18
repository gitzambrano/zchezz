"""Dedicated Colab Training Monitor and Watchdog.

Keeps browser session alive, ensures runtime kernel connects, sets code,
triggers execution, and logs epoch heartbeats for Zchezz NNUE training.
"""

import sys as _sys
from pathlib import Path as _Path
_repo_root = _Path(__file__).resolve().parents[2]
if str(_repo_root) not in _sys.path:
    _sys.path.insert(0, str(_repo_root))


import argparse
import sys
import time
from pathlib import Path

CURRENT_DIR = Path(__file__).resolve().parent
REPO_ROOT = CURRENT_DIR.parent.parent
if str(CURRENT_DIR) not in sys.path:
    sys.path.insert(0, str(CURRENT_DIR))

from colab.config import WORKERS
from colab.playwright.browser_utils import launch_stealth_context, dismiss_modals, get_notebook_dom_state


def monitor_worker(worker_id: int, max_epochs: int = 100):
    w = WORKERS[worker_id]
    profile = w.get("profile", "v331")
    cdp_port = w.get("cdp_port", 9000 + worker_id)

    print("=" * 70)
    print(f"COLAB TRAINING MONITOR - Worker {worker_id} ({profile}) - Account: {w['account']}")
    print("=" * 70)

    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        ctx = launch_stealth_context(
            p,
            profile_dir=w["profile_dir"],
            headless=True,
            cdp_port=cdp_port,
            extra_args=["--no-sandbox", "--disable-dev-shm-usage"]
        )
        page = ctx.pages[0] if ctx.pages else ctx.new_page()
        page.goto(w["notebook_url"], wait_until="commit", timeout=60000)
        time.sleep(10)
        dismiss_modals(page)

        # Step 1: Wait for runtime to transition from 'Conectando' to active
        print("Waiting for runtime connection...")
        connected = False
        for wait_i in range(30):  # Wait up to 2.5 minutes
            dismiss_modals(page)
            dom = get_notebook_dom_state(page, ["v331", "v507", "run_train_colab.sh", "EPOCH"])
            status = dom["statusText"]
            print(f"  [{wait_i+1}/30] Connection status: {status}")

            if "RAM" in status or dom["kConnected"]:
                connected = True
                print("  Runtime kernel successfully connected!")
                break

            # Try clicking connect/reconnect button
            page.evaluate("""() => {
                const btn = document.querySelector('colab-connect-button');
                if (btn && btn.shadowRoot) {
                    const conn = btn.shadowRoot.querySelector('#connect, #connect-button, button');
                    if (conn && (conn.innerText.includes('Conectar') || conn.innerText.includes('Reconectar'))) conn.click();
                } else if (btn) {
                    btn.click();
                }
            }""")
            time.sleep(5)

        # Step 2: Inject bootloader and trigger cell execution
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

        print(f"Injecting training bootloader for profile {profile}...")
        res = page.evaluate("""(code) => {
            const nb = typeof colab !== 'undefined' && colab.global ? colab.global.notebook : null;
            if (!nb || !nb.cells || nb.cells.length === 0) return { success: false, reason: 'no_cells' };

            const targetCell = nb.cells[0];
            if (targetCell.model && targetCell.model.setText) {
                targetCell.model.setText(code);
            }
            if (targetCell.model && targetCell.model.removeOutputs) {
                targetCell.model.removeOutputs();
            }

            if (typeof monaco !== 'undefined') {
                const models = monaco.editor.getModels();
                if (models && models.length > 0) {
                    models[0].setValue(code);
                }
            }

            const elem = targetCell.getElement ? targetCell.getElement() : (targetCell.element_ || targetCell.dom_);
            if (elem && elem.scrollIntoView) elem.scrollIntoView();

            if (typeof targetCell.manualExecute === 'function') {
                targetCell.manualExecute();
                return { success: true, method: 'manualExecute' };
            }
            return { success: false, reason: 'no_execute' };
        }""", code)
        print("Trigger result:", res)
        time.sleep(10)
        dismiss_modals(page)

        # Step 3: Keep-alive monitoring loop
        print("\nEntering active training monitoring loop (press Ctrl+C to stop)...")
        last_out = ""
        iteration = 0
        while iteration < 20:  # Monitor for initial confirmation
            iteration += 1
            dismiss_modals(page)
            # Gentle mouse jitter to prevent Colab idle timeouts
            page.mouse.move(300 + (iteration % 50), 300 + (iteration % 50))

            dom = get_notebook_dom_state(page, ["run_train_colab.sh", "EPOCH", "heartbeat", profile])
            out = dom.get("outText", "")
            if out and out != last_out:
                new_part = out[len(last_out):] if out.startswith(last_out) else out[-600:]
                print(f"\n[OUTPUT {time.strftime('%H:%M:%S')}]\n{new_part}")
                last_out = out

            if dom["running"]:
                print(f"\r[STATUS {time.strftime('%H:%M:%S')}] Runtime: {dom['statusText']} | Cell is actively running...", end="", flush=True)
            else:
                print(f"\r[STATUS {time.strftime('%H:%M:%S')}] Runtime: {dom['statusText']} | Cell idle / pending...", end="", flush=True)

            time.sleep(15)

        ss_path = REPO_ROOT / "artifacts" / "colab" / "playwright" / f"train_worker_{worker_id}_monitored.png"
        page.screenshot(path=str(ss_path))
        print(f"\nMonitoring snapshot saved to {ss_path}")
        ctx.close()


if __name__ == "__main__":
    from colab.control import invocation_lease
    with invocation_lease(globals().get("CONFIG", {}), "playwright"):
        parser = argparse.ArgumentParser(description="Colab Training Monitor.")
        parser.add_argument("--worker", type=int, default=6, help="Worker ID (6 for v331, 7 for v507)")
        args = parser.parse_args()
        monitor_worker(args.worker)
