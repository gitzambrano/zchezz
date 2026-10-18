"""Connect Colab Worker 6, set GPU T4, start training v331, and verify GPU execution."""

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

def start_worker_6():
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

    print(f"=== Starting Worker 6 ({w['name']} - {w['account']}) on GPU T4 ===")
    with sync_playwright() as p:
        ctx = p.chromium.launch_persistent_context(
            user_data_dir=w["profile_dir"],
            headless=True,
            channel="chrome",
            args=[f"--remote-debugging-port={w['cdp_port']}", "--no-sandbox"],
        )
        page = ctx.pages[0] if ctx.pages else ctx.new_page()
        page.goto(w["notebook_url"], wait_until="commit", timeout=45000)
        time.sleep(8)
        dismiss_modals(page)

        # Listen for Google OAuth popups
        ctx.on("page", lambda p_new: handle_google_oauth_popup(p_new, w["account"]))

        # 1. Switch to GPU T4
        print("Ensuring GPU T4 accelerator...")
        menu = page.locator('div[id="runtime-menu-button"]').or_(page.locator('text="Ambiente de execução"')).first
        if menu.is_visible():
            menu.click()
            time.sleep(1.5)
            change_item = page.locator('text="Alterar o tipo de ambiente de execução"').or_(page.locator('text="Change runtime type"')).first
            if change_item.is_visible():
                change_item.click()
                time.sleep(2)
                # Look for T4 radio
                t4_opt = page.locator('text="GPUs: T4"').or_(page.locator('text="T4"')).or_(page.locator('text="T4 GPU"')).first
                if t4_opt.is_visible():
                    t4_opt.click()
                    time.sleep(1)
                    print("Selected T4 GPU radio option.")
                
                save_btn = page.locator('md-text-button:has-text("Salvar"), button:has-text("Salvar"), button:has-text("Save")').first
                if save_btn.is_visible():
                    save_btn.click(force=True)
                    time.sleep(2)
                    # Dismiss any confirm dialog
                    page.evaluate("""() => {
                        const btns = Array.from(document.querySelectorAll('mwc-button, md-text-button, button'));
                        const ok = btns.find(b => b.innerText && (['Sim', 'Continuar', 'Desconectar', 'Yes', 'Continue', 'OK'].includes(b.innerText.trim())));
                        if (ok) ok.click();
                    }""")
                    time.sleep(4)
                    print("Saved runtime settings.")

        # 2. Connect runtime
        print("Ensuring runtime connection...")
        for attempt in range(15):
            dismiss_modals(page)
            state = page.evaluate("""() => {
                const btn = document.querySelector('colab-connect-button');
                const txt = btn ? btn.innerText : '';
                return {
                    status: txt,
                    connected: txt.includes('RAM') || txt.includes('Disco') || txt.includes('Disk')
                };
            }""")
            if state["connected"]:
                print(f"Connected: {state['status']}")
                break
            print(f"Connecting... (status: {state['status']}) attempt {attempt+1}/15")
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

        # 3. Inject code into Cell 0 and run
        print("Injecting training bootloader and executing...")
        res = page.evaluate("""(code) => {
            const nb = colab.global.notebook;
            if (!nb || !nb.cells || nb.cells.length === 0) return { error: 'no_cells' };
            const cell = nb.cells[0];
            if (cell.setText) cell.setText(code);
            else if (cell.model && cell.model.setText) cell.model.setText(code);

            // Clean other cells
            for (let i = 1; i < nb.cells.length; i++) {
                if (nb.cells[i].model && nb.cells[i].model.setText) {
                    nb.cells[i].model.setText('# Célula desativada');
                }
            }

            // Interrupt any previous run
            if (nb.interruptKernel) {
                try { nb.interruptKernel(); } catch(e) {}
            }

            // Run Cell 0
            if (cell.element) {
                const runBtn = cell.element.querySelector('colab-run-button');
                if (runBtn) {
                    if (runBtn.shadowRoot) {
                        const b = runBtn.shadowRoot.querySelector('button, [role="button"]');
                        if (b) b.click();
                        else runBtn.click();
                    } else {
                        runBtn.click();
                    }
                    return { ok: true, method: 'runBtn' };
                }
            }
            if (cell.execute) {
                cell.execute();
                return { ok: true, method: 'execute' };
            }
            return { error: 'no_run_method' };
        }""", code)
        print("Run trigger result:", res)
        time.sleep(15)

        dismiss_modals(page)
        # Check OAuth or Drive permissions popup
        for _ in range(5):
            page.evaluate("""() => {
                const btns = Array.from(document.querySelectorAll('button, md-text-button, mwc-button'));
                for (const b of btns) {
                    const t = (b.innerText || '').toLowerCase();
                    if (t.includes('conectar ao google drive') || t.includes('connect to google drive') || t.includes('permitir') || t.includes('allow')) {
                        b.click();
                    }
                }
            }""")
            time.sleep(3)

        out_snap = REPO_ROOT / "colab" / "artifacts" / "train_w6_launched.png"
        out_snap.parent.mkdir(parents=True, exist_ok=True)
        page.screenshot(path=str(out_snap))
        print(f"Screenshot saved to {out_snap}")
        ctx.close()

if __name__ == "__main__":
    start_worker_6()
