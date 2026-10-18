
import sys as _sys
from pathlib import Path as _Path
_repo_root = _Path(__file__).resolve().parents[3]
if str(_repo_root) not in _sys.path:
    _sys.path.insert(0, str(_repo_root))

from colab.config import WORKERS as _PRIVATE_WORKERS
from colab.private import resource as _private_resource

import time
from playwright.sync_api import sync_playwright

profile = _PRIVATE_WORKERS[7]["profile_dir"]
url = _private_resource('drive_folder_url_1')

with sync_playwright() as p:
    ctx = p.chromium.launch_persistent_context(profile, headless=True, channel="chrome", accept_downloads=True)
    page = ctx.pages[0] if ctx.pages else ctx.new_page()
    page.goto(url, timeout=45000)
    time.sleep(6)
    
    # Click at (650, 95) which is right inside selfplay_v507 header
    print("Clicking folder header at (650, 95)...", flush=True)
    page.mouse.click(650, 95)
    time.sleep(2)
    page.screenshot(path="colab/artifacts/folder_header_menu.png")
    
    items = page.evaluate("""() => {
        return Array.from(document.querySelectorAll('[role="menuitem"], [role="menu"] div')).map(e => e.innerText ? e.innerText.trim() : '').filter(Boolean);
    }""")
    print("Menu items:", items, flush=True)
    
    # Check for 'Fazer download' or 'Baixar'
    dl = page.locator('[role="menuitem"]:has-text("Fazer download"), [role="menuitem"]:has-text("Baixar"), [role="menuitem"]:has-text("Download")').first
    if dl.count() == 0:
        dl = page.get_by_text("Fazer download").or_(page.get_by_text("Baixar")).or_(page.get_by_text("Download")).first
    print("Download button found:", dl.count() > 0, flush=True)
    if dl.count() > 0:
        print("Clicking download...", flush=True)
        with page.expect_download(timeout=180000) as dl_info:
            dl.click()
            print("Download triggered! Waiting for zip...", flush=True)
        download = dl_info.value
        save_path = "data/selfplay_v507.zip"
        download.save_as(save_path)
        print(f"SUCCESS: Saved download to {save_path}!", flush=True)
        
    ctx.close()
