"""Automate Google Drive folder sharing between Zchezz Colab accounts."""

import time
from playwright.sync_api import sync_playwright

PROFILE_7 = r"C:\Projetos\TikTok\profiles\zbrainproject"
PROFILE_6 = r"C:\Projetos\TikTok\profiles\zchezzproject"
FOLDER_URL_7 = "https://drive.google.com/drive/folders/1DQW0XgLAcwwZpYednaMaEA_NUAzuDrWj"
TARGET_EMAIL = "zchezzproject@gmail.com"


def share_folder_from_zbrain():
    print("Step 1: Opening Drive in zbrainproject...")
    with sync_playwright() as p:
        ctx = p.chromium.launch_persistent_context(
            user_data_dir=PROFILE_7,
            headless=True,
            channel="chrome",
            args=["--remote-debugging-port=9508", "--no-sandbox"],
        )
        page = ctx.pages[0] if ctx.pages else ctx.new_page()
        page.goto(FOLDER_URL_7, wait_until="commit", timeout=45000)
        time.sleep(6)

        # Look for the share icon or dropdown
        # In Google Drive, clicking the folder name 'zchezz_data' in the breadcrumbs opens its menu
        breadcrumb = page.get_by_text("zchezz_data").first
        breadcrumb.click()
        time.sleep(1.5)

        page.evaluate("""() => {
            const items = Array.from(document.querySelectorAll('[role="menuitem"]'));
            const comp = items.filter(el => el.innerText && el.innerText.includes('Compartilhar'));
            if (comp.length > 1) {
                comp[1].click();
            } else if (comp.length === 1) {
                comp[0].click();
            }
        }""")
        time.sleep(3)

        page.screenshot(path="colab/artifacts/drive_share_dialog.png")
        print("Share dialog screenshot captured.")

        print(f"Typing target email: {TARGET_EMAIL}")
        page.keyboard.type(TARGET_EMAIL, delay=50)
        time.sleep(2)
        page.keyboard.press("Enter")
        time.sleep(2)

        page.screenshot(path="colab/artifacts/drive_share_typing.png")
        time.sleep(2)
        print("Clicking Enviar button across all frames...")
        clicked = False
        for f in page.frames:
            try:
                b = f.locator("button:has-text('Enviar'), button:has-text('Send')").first
                if b.is_visible():
                    b.click()
                    clicked = True
                    print(f"Clicked Enviar in frame {f.name or f.url[:40]}!")
                    break
            except Exception:
                pass

        if not clicked:
            print("Trying mouse click on Enviar position...")
            # The Enviar button in the screenshot is at (880, 550) or let's find the bounding box
            page.mouse.click(880, 550)

        time.sleep(6)
        page.screenshot(path="colab/artifacts/drive_share_final.png")
        ctx.close()


def add_shortcut_in_zchezz():
    print("Step 2: Opening Drive in zchezzproject to add shortcut...")
    with sync_playwright() as p:
        ctx = p.chromium.launch_persistent_context(
            user_data_dir=PROFILE_6,
            headless=True,
            channel="chrome",
            args=["--remote-debugging-port=9332", "--no-sandbox"],
        )
        page = ctx.pages[0] if ctx.pages else ctx.new_page()
        page.goto(FOLDER_URL_7, wait_until="commit", timeout=45000)
        time.sleep(6)
        print("Folder page loaded in zchezzproject. Pressing Shift+Z...")
        page.keyboard.press("Shift+Z")
        time.sleep(3)
        page.screenshot(path="colab/artifacts/drive_shortcut_picker.png")

        # In the shortcut modal, select 'Meu Drive' (or double click) and click 'Adicionar atalho'
        print("Looking for confirmation button...")
        clicked_add = False
        for f in page.frames:
            try:
                btn = f.locator("button:has-text('Adicionar atalho'), button:has-text('Adicionar'), button:has-text('Add shortcut'), button:has-text('Add')").first
                if btn.is_visible():
                    btn.click()
                    clicked_add = True
                    print(f"Clicked Add shortcut in frame {f.name}!")
                    break
            except Exception:
                pass

        if not clicked_add:
            btn = page.locator("button:has-text('Adicionar atalho'), button:has-text('Adicionar'), button:has-text('Add shortcut'), button:has-text('Add')").first
            if btn.is_visible():
                btn.click()
                print("Clicked Add shortcut in main page!")
                clicked_add = True

        time.sleep(5)
        page.screenshot(path="colab/artifacts/drive_shortcut_final.png")
        ctx.close()


if __name__ == "__main__":
    import sys
    action = sys.argv[1] if len(sys.argv) > 1 else "share"
    if action == "share":
        share_folder_from_zbrain()
    elif action == "shortcut":
        add_shortcut_in_zchezz()
