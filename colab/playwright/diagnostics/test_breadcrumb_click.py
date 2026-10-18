
import sys as _sys
from pathlib import Path as _Path
_repo_root = _Path(__file__).resolve().parents[3]
if str(_repo_root) not in _sys.path:
    _sys.path.insert(0, str(_repo_root))

from colab.config import WORKERS as _PRIVATE_WORKERS
from colab.private import resource as _private_resource

import time
from pathlib import Path
from playwright.sync_api import sync_playwright

profile = _PRIVATE_WORKERS[7]["profile_dir"]
url = _private_resource('drive_folder_url_1')

with sync_playwright() as p:
    ctx = p.chromium.launch_persistent_context(profile, headless=True, channel="chrome", accept_downloads=True)
    page = ctx.pages[0] if ctx.pages else ctx.new_page()
    page.goto(url, timeout=45000)
    time.sleep(6)
    
    print("Clicking breadcrumb folder title at (555, 136)...", flush=True)
    page.mouse.click(555, 136)
    time.sleep(2)
    page.screenshot(path="colab/artifacts/breadcrumb_menu.png")
    
    items = page.evaluate("""() => {
        return Array.from(document.querySelectorAll('[role="menuitem"], [role="menu"] div')).map(e => e.innerText ? e.innerText.trim() : '').filter(Boolean);
    }""")
    print("Breadcrumb menu items:", items, flush=True)
    ctx.close()
