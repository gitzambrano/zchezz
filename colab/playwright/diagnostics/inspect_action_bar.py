
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
    ctx = p.chromium.launch_persistent_context(profile, headless=True, channel="chrome")
    page = ctx.pages[0] if ctx.pages else ctx.new_page()
    page.goto(url, timeout=45000)
    time.sleep(6)
    
    # Click selfplay_v507
    el = page.get_by_text("selfplay_v507", exact=True).first
    el.click()
    time.sleep(2)
    
    # Inspect top action bar buttons
    buttons = page.evaluate("""() => {
        const btns = Array.from(document.querySelectorAll('button, [role="button"]'));
        return btns.map(b => {
            const rect = b.getBoundingClientRect();
            return {
                text: b.innerText ? b.innerText.trim() : '',
                aria: b.getAttribute('aria-label') || '',
                tooltip: b.getAttribute('data-tooltip') || '',
                rect: {x: Math.round(rect.x), y: Math.round(rect.y), w: Math.round(rect.width), h: Math.round(rect.height)}
            };
        }).filter(b => b.rect.y > 150 && b.rect.y < 250 && b.rect.w > 0);
    }""")
    
    print("Action bar buttons when 1 item selected:")
    for b in buttons:
        print(" ", b)
        
    page.screenshot(path="colab/artifacts/action_bar_selected.png")
    ctx.close()
