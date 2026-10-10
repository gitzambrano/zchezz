"""Set link sharing on zchezz_data folder to 'Anyone with the link'."""

import time
from playwright.sync_api import sync_playwright

PROFILE_7 = r"C:\Projetos\TikTok\profiles\zbrainproject"
FOLDER_URL_7 = "https://drive.google.com/drive/folders/1DQW0XgLAcwwZpYednaMaEA_NUAzuDrWj"


def set_public_link():
    print("Opening Drive in zbrainproject...")
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

        breadcrumb = page.get_by_text("zchezz_data").first
        breadcrumb.click()
        time.sleep(1.5)

        page.evaluate("""() => {
            const items = Array.from(document.querySelectorAll('[role="menuitem"]'));
            const comp = items.filter(el => el.innerText && el.innerText.includes('Compartilhar'));
            if (comp.length > 1) comp[1].click(); else if (comp.length === 1) comp[0].click();
        }""")
        time.sleep(3)

        print("Clicking Restrito dropdown at (370, 655)...")
        page.mouse.click(370, 655)
        time.sleep(1.5)
        page.screenshot(path="colab/artifacts/drive_restrito_menu.png")

        print("Selecting 'Qualquer pessoa com o link'...")
        # Check all frames for 'Qualquer pessoa com o link'
        clicked_pub = False
        for f in page.frames:
            try:
                pub = f.locator("text='Qualquer pessoa com o link'").or_(f.locator("text='Anyone with the link'")).first
                if pub.is_visible():
                    pub.click()
                    clicked_pub = True
                    print(f"Clicked public option in frame {f.name}!")
                    break
            except Exception:
                pass

        if not clicked_pub:
            page.keyboard.press("ArrowDown")
            page.keyboard.press("Enter")
            print("Pressed ArrowDown + Enter for dropdown selection.")

        time.sleep(2)
        # Click Concluído
        for f in page.frames:
            try:
                done = f.locator("button:has-text('Concluído'), button:has-text('Done')").first
                if done.is_visible():
                    done.click()
                    print(f"Clicked Concluído in frame {f.name}!")
                    break
            except Exception:
                pass

        page.screenshot(path="colab/artifacts/drive_public_link_result.png")
        ctx.close()


if __name__ == "__main__":
    set_public_link()
