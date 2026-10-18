"""Check versionable files without disclosure of private values."""
import argparse
import json
from pathlib import Path
import re
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from colab.private import load

CONFIG = {"root": ROOT, "max_file_bytes": 8_000_000}


def private_identifiers(data):
    """Collect local values for comparison without log output."""
    values = set(data.get("resources", {}).values())
    for workers in data.get("projects", {}).values():
        for worker in workers.values():
            for key in ("account", "profile_dir", "notebook_url"):
                value = worker.get(key)
                if isinstance(value, str) and value:
                    values.add(value)
                    values.add(value.replace("\\", "\\\\"))
            url = worker.get("notebook_url", "")
            if "/drive/" in url:
                values.add(url.rsplit("/", 1)[-1])
    return {value for value in values if isinstance(value, str) and len(value) >= 8}


def scan(root, identifiers):
    """Inspect tracked and unignored files. Return paths and categories only."""
    paths = subprocess.check_output(["git", "ls-files", "-c", "-o", "--exclude-standard", "-z"], cwd=root).decode("utf-8").split("\0")
    findings = []
    for name in sorted(set(paths) - {""}):
        path = Path(root) / name
        if not path.is_file() or path.stat().st_size > CONFIG["max_file_bytes"]:
            continue
        try:
            text = path.read_text(encoding="utf-8-sig")
        except (OSError, UnicodeError):
            continue
        categories = []
        if any(value in text for value in identifiers):
            categories.append("private_identifier")
        if re.search(r'[\x22\x27](?:refresh_token|access_token)[\x22\x27]\s*:\s*[\x22\x27](?:1//|ya29\.)[A-Za-z0-9_-]{20,}', text):
            categories.append("oauth_token")
        if "-----BEGIN " + "PRIVATE KEY-----" in text:
            categories.append("private_key")
        if categories:
            findings.append({"file": name, "categories": categories})
    return findings


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--show-config", action="store_true")
    args = parser.parse_args()
    if args.show_config:
        print(json.dumps(CONFIG, default=str))
        return 0
    identifiers = private_identifiers(load())
    findings = scan(CONFIG["root"], identifiers)
    if findings:
        print(json.dumps(findings, indent=2))
        return 1
    print("No configured personal identifiers, OAuth token literals, or private keys found in scanned candidate files.")
    if not identifiers:
        print("Private account configuration is absent. Personal identifier comparison was unavailable.")
    print("This check excludes ignored files, unreadable files, files over 8 MB, and Git history.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
