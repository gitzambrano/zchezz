"""Interactive and headless training manager for Google Colab workers.

Automates switching to GPU, pulling latest commits, and monitoring training epochs.
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

# Ensure colab root is in path
CURRENT_DIR = Path(__file__).resolve().parent
REPO_ROOT = CURRENT_DIR.parent.parent
if str(CURRENT_DIR) not in sys.path:
    sys.path.insert(0, str(CURRENT_DIR))

from colab.config import WORKERS
from colab.playwright.browser_utils import launch_stealth_context, dismiss_modals, get_notebook_dom_state


def get_worker(worker_id):
    if worker_id in WORKERS:
        return WORKERS[worker_id]
    for w in WORKERS.values():
        if w.get("profile") == worker_id:
            return w
    raise ValueError(f"Unknown worker: {worker_id}")


def inspect_worker(page, keywords):
    dismiss_modals(page)
    return get_notebook_dom_state(page, keywords)


def switch_to_gpu(page):
    """Switch hardware accelerator to T4 GPU via Colab UI menu."""
    dismiss_modals(page)
    # Click 'Ambiente de execução' or 'Runtime' menu item
    menu = page.locator('div[id="runtime-menu-button"]')
    if menu.count() == 0:
        menu = page.locator('text="Ambiente de execução"').or_(page.locator('text="Runtime"'))
    
    if menu.count() > 0:
        menu.first.click()
        time.sleep(1.5)
    else:
        print("  [WARN] Runtime menu item not found.")
        return False

    # Click 'Alterar o tipo de ambiente de execução'
    change_item = page.locator('text="Alterar o tipo de ambiente de execução"').or_(page.locator('text="Change runtime type"'))
    if change_item.count() > 0:
        change_item.first.click()
        time.sleep(2)
    else:
        print("  [WARN] 'Alterar o tipo de ambiente de execução' menu item not found.")
        return False

    # Select T4 GPU (Portuguese label is 'GPUs: T4')
    gpu_radio = page.locator('text="GPUs: T4"').or_(page.locator('text="T4"')).or_(page.locator('text="T4 GPU"')).first
    if gpu_radio.is_visible():
        gpu_radio.click()
        time.sleep(1)
        print("  Selected GPUs: T4 option.")
    else:
        print("  [WARN] GPUs: T4 not visible directly.")

    # Click 'Salvar' / 'Save'
    save_btn = page.locator('button:has-text("Salvar"), md-text-button:has-text("Salvar"), button:has-text("Save")').first
    if save_btn.is_visible():
        save_btn.click(force=True)
        time.sleep(2)
        # Handle "dismiss-runtime-warning yes-no-dialog" if changing while active
        page.evaluate("""() => {
            const btns = Array.from(document.querySelectorAll('mwc-button, md-text-button, button'));
            const ok = btns.find(b => b.innerText && (['Sim', 'Continuar', 'Desconectar', 'Yes', 'Continue', 'OK'].includes(b.innerText.trim())));
            if (ok) ok.click();
        }""")
        time.sleep(5)
        print("  Clicked Save in runtime dialog and dismissed warnings.")
        return True
    else:
        print("  [WARN] Save button not found in runtime dialog.")
        return False


def set_and_run_training(page, profile):
    """Inject training bootloader into cell and trigger execution."""
    dismiss_modals(page)
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

    res = page.evaluate("""(code) => {
        const nb = typeof colab !== 'undefined' && colab.global ? colab.global.notebook : null;
        if (!nb || !nb.cells || nb.cells.length === 0) return { success: false, reason: 'no_cells' };

        // Interrupt any running kernel first
        if (nb && typeof nb.interruptKernel === 'function') {
            try { nb.interruptKernel(); } catch (e) {}
        }

        // Disable all other cells so only Cell 0 runs
        for (let i = 1; i < nb.cells.length; i++) {
            if (nb.cells[i].model && nb.cells[i].model.setText) {
                nb.cells[i].model.setText('# Célula desativada');
            }
            if (nb.cells[i].model && nb.cells[i].model.removeOutputs) {
                nb.cells[i].model.removeOutputs();
            }
        }

        // Cell 0 is the designated runner cell
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
                for (let i = 1; i < models.length; i++) {
                    models[i].setValue('# Célula desativada');
                }
            }
        }

        const elem = targetCell.getElement ? targetCell.getElement() : (targetCell.element_ || targetCell.dom_);
        if (elem && elem.scrollIntoView) elem.scrollIntoView();

        if (typeof targetCell.manualExecute === 'function') {
            targetCell.manualExecute();
            return { success: true, method: 'manualExecute' };
        } else if (elem) {
            const btn = elem.querySelector('colab-run-button');
            if (btn) {
                if (btn.shadowRoot) {
                    const inner = btn.shadowRoot.querySelector('button, [role="button"]');
                    if (inner) inner.click();
                    else btn.click();
                } else {
                    btn.click();
                }
                return { success: true, method: 'colab-run-button' };
            }
        }
        return { success: false, reason: 'no_run_method' };
    }""", code)

    time.sleep(3)
    dismiss_modals(page)
    return res


def main():
    parser = argparse.ArgumentParser(description="Manage Colab Training.")
    parser.add_argument("--worker", default="7", help="Worker ID (6 or 7, or v331 or v507)")
    parser.add_argument("--action", choices=["status", "switch-gpu", "start", "full-setup"], default="status")
    parser.add_argument("--headed", action="store_true")
    args = parser.parse_args()

    w = get_worker(int(args.worker) if args.worker.isdigit() else args.worker)
    profile = w.get("profile", "v331")
    print(f"=== Managing {w['name']} (Profile: {profile}, Account: {w['account']}) - Action: {args.action} ===")

    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        ctx = launch_stealth_context(
            p,
            profile_dir=w["profile_dir"],
            headless=not args.headed,
            cdp_port=w["cdp_port"]
        )
        page = ctx.pages[0] if ctx.pages else ctx.new_page()
        page.goto(w["notebook_url"], wait_until="commit", timeout=45000)
        time.sleep(8)
        dismiss_modals(page)

        if args.action in ["switch-gpu", "full-setup"]:
            print("Switching runtime accelerator to T4 GPU...")
            ok = switch_to_gpu(page)
            print("Switch result:", ok)
            time.sleep(3)
            dismiss_modals(page)

        if args.action in ["start", "full-setup"]:
            print("Ensuring runtime is connected before triggering execution...")
            for attempt in range(15):
                dismiss_modals(page)
                dom = inspect_worker(page, ["run_train_colab.sh", "EPOCH", profile])
                if "RAM" in dom["statusText"] or dom.get("kConnected"):
                    print(f"Runtime connected: {dom['statusText']}")
                    break
                print(f"Waiting for runtime connection ({dom['statusText']})... attempt {attempt+1}/15")
                page.evaluate("""() => {
                    const btn = document.querySelector('colab-connect-button');
                    if (btn && btn.shadowRoot) {
                        const conn = btn.shadowRoot.querySelector('#connect, #connect-button, button');
                        if (conn) conn.click();
                    } else if (btn) {
                        btn.click();
                    }
                }""")
                time.sleep(5)

            print(f"Injecting training bootloader for profile {profile} and executing...")
            res = set_and_run_training(page, profile)
            print("Execution trigger result:", res)
            time.sleep(12)
            dismiss_modals(page)

        dom = inspect_worker(page, ["run_train_colab.sh", "EPOCH", profile])
        print(f"DOM Status: {dom['statusText']}")
        print(f"Running: {dom['running']}, Pending: {dom['pending']}")
        if dom.get("outText"):
            print("Recent Output:\n", dom["outText"][-1000:])
        else:
            print("Recent Output: (empty)")

        screenshot_path = REPO_ROOT / "artifacts" / "colab" / "playwright" / f"train_worker_{w['worker_id']}_{args.action}.png"
        screenshot_path.parent.mkdir(parents=True, exist_ok=True)
        page.screenshot(path=str(screenshot_path))
        print(f"Screenshot saved to {screenshot_path}")

        ctx.close()


if __name__ == "__main__":
    from colab.control import invocation_lease
    with invocation_lease(globals().get("CONFIG", {}), "playwright"):
        main()
