
import sys as _sys
from pathlib import Path as _Path
_repo_root = _Path(__file__).resolve().parents[3]
if str(_repo_root) not in _sys.path:
    _sys.path.insert(0, str(_repo_root))

from colab.config import WORKERS as _PRIVATE_WORKERS
from colab.private import resource as _private_resource

import time
from playwright.sync_api import sync_playwright

PROFILE_6 = _PRIVATE_WORKERS[6]["profile_dir"]

with sync_playwright() as p:
    ctx = p.chromium.launch_persistent_context(
        PROFILE_6,
        headless=True,
        channel="chrome",
        args=["--remote-debugging-port=9332", "--no-sandbox"],
    )
    page = ctx.pages[0] if ctx.pages else ctx.new_page()
    page.goto("https://drive.google.com/drive/my-drive", wait_until="commit", timeout=45000)
    time.sleep(8)
    
    # Check for zchezz_data or open it
    row = page.locator('div[role="row"]:has-text("zchezz_data"), tr:has-text("zchezz_data")').first
    if row.count() > 0:
        row.dblclick()
        time.sleep(6)
        
    items = page.evaluate("""() => {
        const els = Array.from(document.querySelectorAll('[data-target="item"], [role="row"], [data-id]'));
        return els.map(el => {
            return el.innerText ? el.innerText.trim() : '';
        }).filter(Boolean);
    }""")
    
    print(f"Total elements: {len(items)}")
    for it in items[:30]:
        lines = [l.strip() for l in it.split("\n") if l.strip()]
        if lines:
            print("  Item:", " | ".join(lines[:3]))
            
    page.screenshot(path="colab/artifacts/zchezz_data_view_v331.png")
    print("Screenshot saved to colab/artifacts/zchezz_data_view_v331.png")
    ctx.close()
