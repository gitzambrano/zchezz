"""Download selfplay datasets from Google Drive for v507 and v331."""

import sys as _sys
from pathlib import Path as _Path
_repo_root = _Path(__file__).resolve().parents[3]
if str(_repo_root) not in _sys.path:
    _sys.path.insert(0, str(_repo_root))

from colab.config import WORKERS as _PRIVATE_WORKERS
from colab.private import resource as _private_resource


import os
import sys
import time
from pathlib import Path
from playwright.sync_api import sync_playwright

CURRENT_DIR = Path(__file__).resolve().parent
REPO_ROOT = CURRENT_DIR.parent.parent.parent
DATA_DIR = REPO_ROOT / "data"

PROFILE_7 = _PRIVATE_WORKERS[7]["profile_dir"]
PROFILE_6 = _PRIVATE_WORKERS[6]["profile_dir"]
FOLDER_URL_7 = _private_resource('drive_folder_url_3')

def inspect_and_download(profile_dir, account_name, cdp_port):
    print(f"\n=======================================================")
    print(f" Checking Google Drive for {account_name}...")
    print(f"=======================================================")
    
    with sync_playwright() as p:
        ctx = p.chromium.launch_persistent_context(
            user_data_dir=profile_dir,
            headless=True,
            channel="chrome",
            args=[f"--remote-debugging-port={cdp_port}", "--no-sandbox"],
            downloads_path=str(DATA_DIR / "downloads"),
        )
        page = ctx.pages[0] if ctx.pages else ctx.new_page()
        page.goto("https://drive.google.com/drive/my-drive", wait_until="commit", timeout=45000)
        time.sleep(8)
        
        # Look for zchezz_data folder
        print("Looking for zchezz_data in root...")
        zrow = page.locator('div[role="row"]:has-text("zchezz_data"), tr:has-text("zchezz_data")').first
        if zrow.count() > 0:
            print("Found zchezz_data! Double clicking...")
            zrow.dblclick()
            time.sleep(6)
        else:
            print("zchezz_data not found in root, trying direct URL...")
            page.goto(FOLDER_URL_7, wait_until="commit", timeout=45000)
            time.sleep(6)
            
        print(f"Current URL: {page.url}")
        
        # List all rows/folders inside
        rows = page.locator('div[role="row"], tr').all()
        print(f"Total row elements found: {len(rows)}")
        for r in rows:
            try:
                txt = r.inner_text().strip().replace("\n", " | ")
                if any(k in txt.lower() for k in ["selfplay", "sp_", "v507", "v331", "shards"]):
                    print("  Row:", txt)
            except Exception:
                pass
                
        screenshot_path = REPO_ROOT / "artifacts" / "colab" / "playwright" / f"drive_check_{account_name}.png"
        screenshot_path.parent.mkdir(parents=True, exist_ok=True)
        page.screenshot(path=str(screenshot_path))
        print(f"Screenshot saved to {screenshot_path}")
        ctx.close()

if __name__ == "__main__":
    inspect_and_download(PROFILE_7, 'worker-7_v507', 9508)
    inspect_and_download(PROFILE_6, 'worker-6_v331', 9332)
