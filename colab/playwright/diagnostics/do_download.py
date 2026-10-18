
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
import zipfile
from pathlib import Path
from playwright.sync_api import sync_playwright

REPO_ROOT = Path(r"C:\Projetos\Zchezz")
DATA_DIR = REPO_ROOT / "data"
DOWNLOADS_DIR = DATA_DIR / "downloads"
DOWNLOADS_DIR.mkdir(parents=True, exist_ok=True)

PROFILE_7 = _PRIVATE_WORKERS[7]["profile_dir"]
URL = _private_resource('drive_folder_url_3')

print('Launching browser with profile worker-7...', flush=True)
with sync_playwright() as p:
    ctx = p.chromium.launch_persistent_context(
        PROFILE_7,
        headless=True,
        channel="chrome",
        args=["--remote-debugging-port=9508", "--no-sandbox"],
        downloads_path=str(DOWNLOADS_DIR),
        accept_downloads=True,
    )
    page = ctx.pages[0] if ctx.pages else ctx.new_page()
    page.goto(URL, wait_until="commit", timeout=45000)
    time.sleep(8)

    # Click selfplay_v507 row to select it
    folder = page.get_by_text("selfplay_v507", exact=True).first
    print("Folder selfplay_v507 visible:", folder.is_visible(), flush=True)
    folder.click()
    time.sleep(2)
    
    print("Clicking toolbar download icon at (510, 208)...", flush=True)
    save_path = DATA_DIR / "selfplay_v507.zip"
    
    try:
        with page.expect_download(timeout=300000) as dl_info:
            page.mouse.click(510, 208)
            print("Download triggered! Waiting for Drive to zip...", flush=True)
            for i in range(1, 120):
                time.sleep(1)
                if i % 10 == 0:
                    print(f"  Zipping in progress ({i}s)...", flush=True)
        download = dl_info.value
        download.save_as(str(save_path))
        print(f"SUCCESS: Saved download to {save_path} ({save_path.stat().st_size:,} bytes)!", flush=True)
    except Exception as e:
        print(f"Download wait error: {e}", flush=True)
        page.screenshot(path="colab/artifacts/after_click_dl.png")
        
    ctx.close()

if save_path.is_file() and save_path.stat().st_size > 0:
    extract_dir = DATA_DIR / "selfplay_v507"
    print(f"Extracting {save_path} to {extract_dir}...", flush=True)
    extract_dir.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(save_path, 'r') as zf:
        zf.extractall(extract_dir)
    print(f"Extracted {len(list(extract_dir.glob('*')))} files into {extract_dir}!", flush=True)
