"""Authorize CLI accounts through their existing browser profiles."""
import argparse
import json
from pathlib import Path
import re
import subprocess
import sys
import time
from urllib.parse import parse_qs, urlparse

if str(Path(__file__).resolve().parents[2]) not in sys.path:
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from colab.config import WORKERS
from colab.cli.settings import CONFIG, account_directory, cli_python


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--worker-ids", type=int, nargs="+", choices=list(WORKERS), default=CONFIG["worker_ids"])
    parser.add_argument("--replace", action="store_true")
    parser.add_argument("--verification-seconds", type=int, default=600)
    parser.add_argument("--show-config", action="store_true")
    args = parser.parse_args()
    if args.show_config:
        print(json.dumps(CONFIG, default=str, indent=2))
        return
    from playwright.sync_api import sync_playwright
    from colab.playwright.sessions import cdp_url
    with sync_playwright() as playwright:
        for worker in args.worker_ids:
            directory = account_directory(worker)
            if (directory / "credentials.json").exists() and not args.replace:
                print(f"Worker {worker}: existing CLI credentials preserved.", flush=True)
                continue
            subprocess.run([cli_python(), "-m", "colab.cli.login", "--worker-ids", str(worker), "--prepare"], cwd=Path(__file__).resolve().parents[2], check=True)
            pending = json.loads((directory / "pending.json").read_text(encoding="utf-8"))
            created = None
            try:
                address = cdp_url(WORKERS[worker])
                if address:
                    browser = playwright.chromium.connect_over_cdp(address, timeout=10000)
                    context = browser.contexts[0]
                else:
                    created = playwright.chromium.launch_persistent_context(WORKERS[worker]["profile_dir"], channel="chrome", headless=False,
                        args=[f"--remote-debugging-port={WORKERS[worker]['cdp_port']}"])
                    context = created
                page = context.new_page()
                page.goto(pending["url"], wait_until="domcontentloaded", timeout=60000)
                deadline = time.monotonic() + args.verification_seconds
                previous_text = None
                while "sdk.cloud.google.com/applicationdefaultauthcode.html" not in page.url:
                    allow = page.get_by_role("button", name=re.compile(r"^(Allow|Permitir)$"))
                    if allow.count():
                        allow.click()
                    elif "accounts.google.com" in page.url:
                        text = page.locator("body").inner_text()[:1600]
                        proceed = page.get_by_role("button", name=re.compile(r"^(Continue|Continuar)$"))
                        if proceed.count() and ("Google Auth Library" in text):
                            if "Selecionar tudo" in text or "Select all" in text:
                                page.get_by_role("checkbox").first.check()
                            proceed.click()
                        if text != previous_text:
                            print(f"Worker {worker}: Google verification:\n{text}", flush=True)
                            previous_text = text
                    if time.monotonic() >= deadline:
                        raise TimeoutError("Complete Google verification in the browser, then run authorization again.")
                    page.wait_for_timeout(2000)
                codes = parse_qs(urlparse(page.url).query).get("code", [])
                if not codes:
                    codes = re.findall(r"4/[A-Za-z0-9_-]+", page.locator("body").inner_text())
                if len(set(codes)) != 1:
                    raise RuntimeError("The authorization page does not contain one code.")
                code_file = directory / "authorization-code.txt"
                code_file.write_text(codes[0], encoding="utf-8")
                result = subprocess.run([cli_python(), "-m", "colab.cli.login", "--worker-ids", str(worker), "--exchange", "--code-file", str(code_file)],
                                        cwd=Path(__file__).resolve().parents[2], capture_output=True, text=True)
                if result.returncode:
                    raise RuntimeError("The credential exchange failed. Complete login with colab.cli.login.")
                print(result.stdout.strip(), flush=True)
                page.close()
                if created:
                    created.close()
            except Exception as error:
                print(f"Worker {worker}: authorization needs attention ({type(error).__name__}). The browser tab remains open.", flush=True)
                continue


if __name__ == "__main__":
    main()
