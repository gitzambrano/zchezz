
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
url = _private_resource('drive_folder_url_3')

with sync_playwright() as p:
    ctx = p.chromium.launch_persistent_context(profile, headless=True, channel="chrome", accept_downloads=True)
    page = ctx.pages[0] if ctx.pages else ctx.new_page()
    page.goto(url, timeout=45000)
    time.sleep(6)
    
    # Click selfplay_v507 to select it
    el = page.get_by_text("selfplay_v507", exact=True).first
    el.click()
    time.sleep(2)
    
    # Click the download icon in the toolbar
    print("Clicking toolbar download icon at (510, 208)...", flush=True)
    page.mouse.click(510, 208)
    time.sleep(3)
    page.screenshot(path="colab/artifacts/after_toolbar_click_1.png")
    
    for i in range(2, 6):
        time.sleep(5)
        page.screenshot(path=f"colab/artifacts/after_toolbar_click_{i}.png")
        print(f"Step {i} ({i*5}s)...", flush=True)
        
    ctx.close()
