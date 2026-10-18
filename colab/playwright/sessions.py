"""Locate existing profile sessions without browser termination."""
import os
from pathlib import Path

CONFIG = {"connect_timeout_ms": 10000}


def cdp_url(worker):
    """Resolve a fixed or dynamic Chrome debugging port for one profile."""
    from colab.playwright.browser_utils import is_cdp_reachable
    port = worker["cdp_port"]
    if is_cdp_reachable(port):
        return f"http://127.0.0.1:{port}"
    import psutil
    expected = Path(worker["profile_dir"])
    for process in psutil.process_iter(["name", "cmdline"]):
        try:
            args = process.info["cmdline"] or []
            if not process.info["name"] or "chrome" not in process.info["name"].lower():
                continue
            profile = next((a.split("=", 1)[1].strip('"') for a in args if a.startswith("--user-data-dir=")), None)
            debug = next((a.split("=", 1)[1] for a in args if a.startswith("--remote-debugging-port=")), None)
            if profile and debug and Path(profile).name.lower() == expected.name.lower() and is_cdp_reachable(int(debug)):
                return f"http://127.0.0.1:{int(debug)}"
        except (psutil.Error, ValueError, OSError):
            continue
    return None
