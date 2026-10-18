
import sys as _sys
from pathlib import Path as _Path
_repo_root = _Path(__file__).resolve().parents[3]
if str(_repo_root) not in _sys.path:
    _sys.path.insert(0, str(_repo_root))

from colab.config import WORKERS as _PRIVATE_WORKERS
from colab.private import resource as _private_resource

import time
from playwright.sync_api import sync_playwright

profile = _PRIVATE_WORKERS[6]["profile_dir"]

with sync_playwright() as p:
    ctx = p.chromium.launch_persistent_context(profile, headless=True, channel="chrome")
    page = ctx.pages[0] if ctx.pages else ctx.new_page()
    page.goto("https://drive.google.com/drive/my-drive", timeout=45000)
    time.sleep(6)
    
    el = page.get_by_text("zchezz_data", exact=True).first
    print("zchezz_data visible:", el.is_visible())
    el.dblclick()
    time.sleep(6)
    print("URL inside zchezz_data:", page.url)
    
    items = page.evaluate("""() => {
        return Array.from(document.querySelectorAll('[data-target="item"], [role="row"], [data-id]')).map(e => e.innerText ? e.innerText.split('\\n')[0].trim() : '').filter(Boolean);
    }""")
    print("Items in zchezz_data:")
    for it in items[:30]:
        print(" -", it)
        
    page.screenshot(path='colab/artifacts/worker-6_zchezz_data.png')
    
    # Also if selfplay_v331 is found, enter it
    v331 = page.get_by_text("selfplay_v331", exact=True).first
    if v331.is_visible():
        print("selfplay_v331 visible! Entering...")
        v331.dblclick()
        time.sleep(6)
        print("URL inside selfplay_v331:", page.url)
        v331_items = page.evaluate("""() => {
            return Array.from(document.querySelectorAll('[data-target="item"], [role="row"], [data-id]')).map(e => e.innerText ? e.innerText.split('\\n')[0].trim() : '').filter(Boolean);
        }""")
        print("Items inside selfplay_v331:")
        for it in v331_items[:30]:
            print("   -", it)
        page.screenshot(path='colab/artifacts/worker-6_inside_v331.png')
        
    ctx.close()
