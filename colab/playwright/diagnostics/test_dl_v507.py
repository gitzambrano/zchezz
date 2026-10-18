
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

REPO_ROOT = Path(r"C:\Projetos\Zchezz")
DATA_DIR = REPO_ROOT / "data"
DOWNLOADS_DIR = DATA_DIR / "downloads"
DOWNLOADS_DIR.mkdir(parents=True, exist_ok=True)

profile = _PRIVATE_WORKERS[7]["profile_dir"]
url = _private_resource('drive_folder_url_3')

with sync_playwright() as p:
    ctx = p.chromium.launch_persistent_context(
        profile,
        headless=True,
        channel="chrome",
        downloads_path=str(DOWNLOADS_DIR),
        accept_downloads=True,
    )
    page = ctx.pages[0] if ctx.pages else ctx.new_page()
    page.goto(url, timeout=45000)
    time.sleep(6)
    
    # Click selfplay_v507 to select it
    el = page.get_by_text("selfplay_v507", exact=True).first
    print("Found selfplay_v507:", el.is_visible())
    el.click()
    time.sleep(2)
    
    # Right-click to see context menu
    el.click(button="right")
    time.sleep(2)
    
    page.screenshot(path="colab/artifacts/v507_context_menu.png")
    
    # Find all menu items
    menu_items = page.evaluate("""() => {
        return Array.from(document.querySelectorAll('[role="menuitem"], [role="menu"] div')).map(e => e.innerText ? e.innerText.trim() : '').filter(Boolean);
    }""")
    print("Menu items:", menu_items[:15])
    
    dl_btn = page.locator('[role="menuitem"]:has-text("Baixar")').first
    if dl_btn.count() == 0:
        dl_btn = page.get_by_text("Baixar", exact=True).first
    
    print("Download button found ('Baixar'):", dl_btn.count() > 0)
    if dl_btn.count() > 0:
        print("Clicking 'Baixar' and expecting download...")
        with page.expect_download(timeout=180000) as dl_info:
            dl_btn.click()
            print("Clicked 'Baixar'! Waiting for Drive to zip and download...")
            for s in range(1, 120):
                time.sleep(1)
                if s % 5 == 0:
                    print(f"  elapsed {s}s...")
        dl = dl_info.value
        dest = DATA_DIR / "selfplay_v507.zip"
        dl.save_as(str(dest))
        print(f"SUCCESS: Downloaded to {dest} ({dest.stat().st_size:,} bytes)!")
    
    ctx.close()
