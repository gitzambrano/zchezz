
import sys as _sys
from pathlib import Path as _Path
_repo_root = _Path(__file__).resolve().parents[3]
if str(_repo_root) not in _sys.path:
    _sys.path.insert(0, str(_repo_root))

from colab.config import WORKERS as _PRIVATE_WORKERS
from colab.private import resource as _private_resource

import time
import zipfile
from pathlib import Path
from playwright.sync_api import sync_playwright

REPO_ROOT = Path(r"C:\Projetos\Zchezz")
DATA_DIR = REPO_ROOT / "data"
PROFILE = _PRIVATE_WORKERS[6]["profile_dir"]
URL = _private_resource('drive_folder_url_5')

def run_download():
    print(f"Connecting to zchezzproject Drive for selfplay_v331...", flush=True)
    with sync_playwright() as p:
        ctx = p.chromium.launch_persistent_context(
            PROFILE,
            headless=True,
            channel="chrome",
            accept_downloads=True,
        )
        page = ctx.pages[0] if ctx.pages else ctx.new_page()
        page.goto(URL, timeout=45000)
        time.sleep(6)
        
        # Click header at (650, 95)
        print("Clicking folder header at (650, 95)...", flush=True)
        page.mouse.click(650, 95)
        time.sleep(2)
        
        # Click 'Baixar'
        dl = page.locator('[role="menuitem"]:has-text("Baixar"), [role="menuitem"]:has-text("Download")').first
        if dl.count() == 0:
            dl = page.get_by_text("Baixar").or_(page.get_by_text("Download")).first
            
        print("Download menu found:", dl.count() > 0, flush=True)
        save_path = DATA_DIR / "selfplay_v331.zip"
        
        with page.expect_download(timeout=300000) as dl_info:
            dl.click()
            print("Download triggered! Waiting for Drive to zip...", flush=True)
            
        download = dl_info.value
        download.save_as(str(save_path))
        print(f"SUCCESS: Saved download to {save_path} ({save_path.stat().st_size:,} bytes)!", flush=True)
        ctx.close()

    if save_path.is_file() and save_path.stat().st_size > 0:
        extract_dir = DATA_DIR / "selfplay_v331"
        print(f"Extracting {save_path} to {extract_dir}...", flush=True)
        extract_dir.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(save_path, 'r') as zf:
            zf.extractall(extract_dir)
        print(f"Extracted {len(list(extract_dir.glob('*')))} items into {extract_dir}!", flush=True)

if __name__ == "__main__":
    run_download()
