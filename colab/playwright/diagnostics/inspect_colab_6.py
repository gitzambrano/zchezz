"""Inspect Colab 6 runtime and dialog state."""

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
from colab.playwright.browser_utils import launch_stealth_context, dismiss_modals, get_notebook_dom_state

w = WORKERS[6]
print("Connecting to Colab 6...")
with sync_playwright() as p:
    ctx = launch_stealth_context(
        p,
        profile_dir=w["profile_dir"],
        headless=True,
        cdp_port=w["cdp_port"]
    )
    page = ctx.pages[0] if ctx.pages else ctx.new_page()
    page.goto(w["notebook_url"], wait_until="commit", timeout=45000)
    time.sleep(8)
    dismiss_modals(page)

    dom = get_notebook_dom_state(page, ["v331", "sp_v331", "run_train_colab.sh"])
    print(f"Status Text: {dom['statusText']}")
    print(f"Running: {dom['running']}, Pending: {dom['pending']}")

    # Open runtime type dialog to inspect GPU availability
    menu = page.locator('div[id="runtime-menu-button"]').or_(page.locator('text="Ambiente de execução"')).first
    if menu.is_visible():
        menu.click()
        time.sleep(1.5)
        change = page.locator('text="Alterar o tipo de ambiente de execução"').or_(page.locator('text="Change runtime type"')).first
        if change.is_visible():
            change.click()
            time.sleep(2)
            dialog = page.locator('colab-dialog, [role="dialog"]').first
            if dialog.is_visible():
                print("Runtime Type Dialog Text:\n", dialog.inner_text())

    page.screenshot(path="colab/artifacts/colab_6_runtime_type_info.png")
    print("Screenshot saved to colab/artifacts/colab_6_runtime_type_info.png")
    ctx.close()
