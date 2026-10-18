
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
profile = _PRIVATE_WORKERS[7]["profile_dir"]
url = _private_resource('drive_folder_url_3')

with sync_playwright() as p:
    ctx = p.chromium.launch_persistent_context(
        profile,
        headless=True,
        channel="chrome",
        accept_downloads=True,
    )
    page = ctx.pages[0] if ctx.pages else ctx.new_page()
    page.goto(url, timeout=45000)
    time.sleep(6)
    
    el = page.get_by_text("selfplay_v507", exact=True).first
    print("Found selfplay_v507:", el.is_visible(), flush=True)
    el.click(button="right")
    time.sleep(2)
    
    # Click Baixar
    dl_btn = page.get_by_text("Baixar", exact=True).first
    print("Clicking Baixar...", flush=True)
    dl_btn.click()
    
    for i in range(1, 10):
        time.sleep(5)
        page.screenshot(path=f"colab/artifacts/dl_step_{i}.png")
        print(f"Captured step {i} ({i*5}s)", flush=True)
        
    ctx.close()
