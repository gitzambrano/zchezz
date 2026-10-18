
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
PROFILE_6 = _PRIVATE_WORKERS[6]["profile_dir"]

def download_folder_from_drive(profile_dir, folder_name, out_zip_name, cdp_port):
    print(f"\n=======================================================")
    print(f" Downloading '{folder_name}' via profile {Path(profile_dir).name}...")
    print(f"=======================================================")
    
    with sync_playwright() as p:
        ctx = p.chromium.launch_persistent_context(
            profile_dir,
            headless=True,
            channel="chrome",
            args=[f"--remote-debugging-port={cdp_port}", "--no-sandbox"],
            downloads_path=str(DOWNLOADS_DIR),
            accept_downloads=True,
        )
        page = ctx.pages[0] if ctx.pages else ctx.new_page()
        page.goto("https://drive.google.com/drive/my-drive", wait_until="commit", timeout=45000)
        time.sleep(8)
        
        # Enter zchezz_data folder if present
        zrow = page.locator('div[role="row"]:has-text("zchezz_data"), tr:has-text("zchezz_data")').first
        if zrow.count() > 0:
            print("Entering zchezz_data folder...")
            zrow.dblclick()
            time.sleep(6)
            
        print(f"Looking for target folder '{folder_name}'...")
        target_row = page.locator(f'div[role="row"]:has-text("{folder_name}"), [data-target="item"]:has-text("{folder_name}")').first
        if target_row.count() == 0:
            print(f"ERROR: Folder '{folder_name}' not found on page!")
            page.screenshot(path=str(REPO_ROOT / f"colab/artifacts/missing_{folder_name}.png"))
            ctx.close()
            return False
            
        print(f"Found '{folder_name}'! Right-clicking to open context menu...")
        target_row.click(button="right")
        time.sleep(2)
        
        page.screenshot(path=str(REPO_ROOT / f"colab/artifacts/menu_{folder_name}.png"))
        
        # Look for 'Fazer download' or 'Download'
        dl_item = page.locator('div[role="menuitem"]:has-text("Fazer download"), div[role="menuitem"]:has-text("Download"), [role="menuitem"]:has-text("download")').first
        if dl_item.count() == 0:
            print("Context menu download option not found by role, trying broad text selector...")
            dl_item = page.locator('text="Fazer download"').or_(page.locator('text="Download"')).first
            
        if dl_item.count() == 0:
            print("ERROR: Could not find download menu item!")
            page.screenshot(path=str(REPO_ROOT / f"colab/artifacts/no_dl_menu_{folder_name}.png"))
            ctx.close()
            return False
            
        print("Clicking 'Fazer download' and waiting for download event...")
        out_zip_path = DATA_DIR / out_zip_name
        
        try:
            with page.expect_download(timeout=300000) as download_info:
                dl_item.click()
                print("Clicked download menu item. Google Drive is zipping files...")
                # Google Drive takes some seconds to zip files before triggering the download
                for sec in range(1, 60):
                    time.sleep(1)
                    if sec % 10 == 0:
                        print(f"  Zipping in progress... {sec}s")
            
            download = download_info.value
            print(f"Download started: {download.suggested_filename}")
            download.save_as(str(out_zip_path))
            print(f"SUCCESS: Saved download to {out_zip_path} ({out_zip_path.stat().st_size:,} bytes)")
        except Exception as e:
            print(f"Download wait error: {e}")
            page.screenshot(path=str(REPO_ROOT / f"colab/artifacts/dl_err_{folder_name}.png"))
            # Check if file was saved directly in downloads folder
            recent = list(DOWNLOADS_DIR.glob("*"))
            if recent:
                newest = max(recent, key=lambda x: x.stat().st_mtime)
                print(f"Found recent file in downloads folder: {newest} ({newest.stat().st_size:,} bytes)")
                newest.replace(out_zip_path)
            else:
                ctx.close()
                return False

        ctx.close()
        
        # Extract if zip exists
        if out_zip_path.is_file() and out_zip_path.stat().st_size > 0:
            extract_dir = DATA_DIR / folder_name
            print(f"Extracting {out_zip_path} to {extract_dir}...")
            extract_dir.mkdir(parents=True, exist_ok=True)
            try:
                with zipfile.ZipFile(out_zip_path, 'r') as zf:
                    zf.extractall(extract_dir)
                print(f"Extraction complete! Files in {extract_dir}: {len(list(extract_dir.glob('*')))}")
            except Exception as e:
                print(f"Zip extraction error: {e}")
            return True
        return False

if __name__ == "__main__":
    target = sys.argv[1] if len(sys.argv) > 1 else "both"
    if target in ["v507", "both"]:
        download_folder_from_drive(PROFILE_7, "selfplay_v507", "selfplay_v507.zip", 9508)
    if target in ["v331", "both"]:
        download_folder_from_drive(PROFILE_6, "selfplay_v331", "selfplay_v331.zip", 9332)
