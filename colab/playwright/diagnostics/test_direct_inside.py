
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
    
    page.screenshot(path="colab/artifacts/direct_inside_v507.png")
    
    # Click the folder dropdown in breadcrumb: 'selfplay_v507' header
    header = page.get_by_role("heading", name="selfplay_v507").or_(page.locator('button:has-text("selfplay_v507")')).first
    print("Found header button:", header.count(), flush=True)
    if header.count():
        header.click()
        time.sleep(2)
        page.screenshot(path="colab/artifacts/header_dropdown_v507.png")
        
        menu_items = page.evaluate("""() => {
            return Array.from(document.querySelectorAll('[role="menuitem"]')).map(e => e.innerText ? e.innerText.trim() : '').filter(Boolean);
        }""")
        print("Header menu items:", menu_items, flush=True)
        
    ctx.close()
