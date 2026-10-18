
import sys as _sys
from pathlib import Path as _Path
_repo_root = _Path(__file__).resolve().parents[3]
if str(_repo_root) not in _sys.path:
    _sys.path.insert(0, str(_repo_root))

from playwright.sync_api import sync_playwright
import time
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT))
from colab.config import WORKERS

w = WORKERS[7]
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

    # Click Salvar on the modal
    print("Clicking Salvar...")
    clicked = False
    for btn in page.locator('button:has-text("Salvar"), md-text-button:has-text("Salvar")').all():
        try:
            if btn.is_visible():
                btn.click(force=True)
                clicked = True
                print("Clicked Salvar button!")
                break
        except Exception:
            pass
            
    time.sleep(3)
    # Check any confirm dialog
    page.evaluate('''() => {
        const btns = Array.from(document.querySelectorAll("button, md-text-button, mwc-button"));
        for (const b of btns) {
            const t = (b.innerText || "").trim().toLowerCase();
            if (["sim", "salvar", "continuar", "desconectar", "yes", "save", "continue", "ok", "alterar"].includes(t)) {
                b.click();
            }
        }
    }''')
    time.sleep(5)

    # Click colab-run-button
    print("Clicking colab-run-button...")
    run_btn = page.locator("colab-run-button").first
    if run_btn.is_visible():
        run_btn.click(force=True)
        print("Clicked run button!")
    else:
        page.keyboard.press("Control+Enter")

    time.sleep(10)
    page.screenshot(path="colab/artifacts/train_w7_final_check.png")
    print("Screenshot saved to colab/artifacts/train_w7_final_check.png")
    ctx.close()
