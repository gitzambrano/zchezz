
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
url = _private_resource('drive_folder_url_3')

with sync_playwright() as p:
    ctx = p.chromium.launch_persistent_context(profile, headless=True, channel="chrome")
    page = ctx.pages[0] if ctx.pages else ctx.new_page()
    page.goto(url, timeout=45000)
    time.sleep(6)
    
    el = page.get_by_text("selfplay_v507", exact=True).first
    print("Found element:", el.is_visible())
    el.dblclick()
    time.sleep(6)
    print("New URL:", page.url)
    
    items = page.evaluate("""() => {
        return Array.from(document.querySelectorAll('[data-target="item"], [role="row"], [data-id]')).map(e => e.innerText ? e.innerText.split('\\n')[0].trim() : '').filter(Boolean);
    }""")
    print(f"Total elements inside selfplay_v507: {len(items)}")
    for it in items[:30]:
        print("  -", it)
        
    page.screenshot(path="colab/artifacts/inside_v507.png")
    ctx.close()
