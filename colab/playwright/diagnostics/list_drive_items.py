
import sys as _sys
from pathlib import Path as _Path
_repo_root = _Path(__file__).resolve().parents[3]
if str(_repo_root) not in _sys.path:
    _sys.path.insert(0, str(_repo_root))

from colab.config import WORKERS as _PRIVATE_WORKERS
from colab.private import resource as _private_resource

import time
from playwright.sync_api import sync_playwright

PROFILE = _PRIVATE_WORKERS[7]["profile_dir"]
URL = _private_resource('drive_folder_url_3')

with sync_playwright() as p:
    ctx = p.chromium.launch_persistent_context(
        PROFILE,
        headless=True,
        channel="chrome",
        args=["--remote-debugging-port=9508", "--no-sandbox"],
    )
    page = ctx.pages[0] if ctx.pages else ctx.new_page()
    page.goto(URL, wait_until="commit", timeout=45000)
    time.sleep(8)
    
    # Extract all text items from the folder view
    items = page.evaluate("""() => {
        const els = Array.from(document.querySelectorAll('[data-target="item"], [role="row"], [data-id]'));
        return els.map(el => {
            const nameEl = el.querySelector('[aria-label], [data-tooltip], [data-name]');
            return el.innerText ? el.innerText.trim() : (nameEl ? nameEl.getAttribute('aria-label') : '');
        }).filter(Boolean);
    }""")
    
    print(f"Total elements: {len(items)}")
    for it in items[:30]:
        lines = [l.strip() for l in it.split("\n") if l.strip()]
        if lines:
            print("  Item:", " | ".join(lines[:3]))
            
    page.screenshot(path="colab/artifacts/zchezz_data_view.png")
    print("Screenshot saved to colab/artifacts/zchezz_data_view.png")
    ctx.close()
