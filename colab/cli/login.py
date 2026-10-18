"""Authorize isolated CLI credentials for registered Google accounts."""

import sys as _sys
from pathlib import Path as _Path
_repo_root = _Path(__file__).resolve().parents[2]
if str(_repo_root) not in _sys.path:
    _sys.path.insert(0, str(_repo_root))

import argparse
from importlib import resources
import json

from colab.config import WORKERS
from colab.cli.settings import CONFIG, account_directory


def prepare(worker):
    """Create an authorization request for the expected account."""
    if WORKERS[worker]["account"].endswith("@example.invalid"):
        raise ValueError("Configure this account in the private COLAB_ACCOUNTS_FILE before authentication.")
    from google_auth_oauthlib.flow import InstalledAppFlow
    from colab_cli.auth import PUBLIC_SCOPES, REMOTE_REDIRECT_URI
    config = json.loads(resources.files("colab_cli").joinpath("oauth_config.json").read_text())
    flow = InstalledAppFlow.from_client_config(config, PUBLIC_SCOPES)
    flow.redirect_uri = REMOTE_REDIRECT_URI
    url, state = flow.authorization_url(prompt="consent", token_usage="remote", login_hint=WORKERS[worker]["account"])
    directory = account_directory(worker)
    directory.mkdir(parents=True, exist_ok=True)
    pending = {"url": url, "state": state, "verifier": flow.code_verifier}
    (directory / "pending.json").write_text(json.dumps(pending), encoding="utf-8")
    return url


def exchange(worker, code):
    """Validate account identity before a credential replacement."""
    from google_auth_oauthlib.flow import InstalledAppFlow
    from google.auth.transport.requests import AuthorizedSession
    from colab_cli.auth import PUBLIC_SCOPES, REMOTE_REDIRECT_URI
    directory = account_directory(worker)
    pending_path = directory / "pending.json"
    pending = json.loads(pending_path.read_text(encoding="utf-8"))
    config = json.loads(resources.files("colab_cli").joinpath("oauth_config.json").read_text())
    flow = InstalledAppFlow.from_client_config(config, PUBLIC_SCOPES, state=pending["state"], code_verifier=pending["verifier"])
    flow.redirect_uri = REMOTE_REDIRECT_URI
    flow.fetch_token(code=code.strip())
    response = AuthorizedSession(flow.credentials).get("https://www.googleapis.com/oauth2/v2/userinfo", timeout=CONFIG["request_timeout"])
    response.raise_for_status()
    if response.json().get("email", "").lower() != WORKERS[worker]["account"].lower():
        raise ValueError("The selected Google account does not match the worker registry.")
    data = json.loads(flow.credentials.to_json())
    data["type"] = "authorized_user"
    path = directory / "credentials.json"
    temporary = directory / "credentials.tmp"
    temporary.write_text(json.dumps(data), encoding="utf-8")
    temporary.chmod(0o600)
    temporary.replace(path)
    pending_path.unlink()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--worker-ids", type=int, nargs="+", choices=CONFIG["worker_ids"], default=CONFIG["worker_ids"])
    modes = parser.add_mutually_exclusive_group()
    modes.add_argument("--prepare", action="store_true")
    modes.add_argument("--exchange", action="store_true")
    parser.add_argument("--code-file", type=str)
    parser.add_argument("--show-config", action="store_true")
    args = parser.parse_args()
    if args.show_config:
        print(json.dumps(CONFIG, default=str, indent=2))
        return
    if args.code_file and (not args.exchange or len(args.worker_ids) != 1):
        parser.error("Use --code-file with --exchange and one worker.")
    from pathlib import Path
    for worker in args.worker_ids:
        if not args.exchange:
            url = prepare(worker)
            if args.prepare:
                print(f"Worker {worker}: authorization request saved outside the repository.")
                continue
            print(f"Authorize {WORKERS[worker]['account']}:\n{url}")
        code = Path(args.code_file).read_text().strip() if args.code_file else input("Authorization code: ")
        exchange(worker, code)
        if args.code_file:
            Path(args.code_file).unlink()
        print(f"Worker {worker}: account identity verified and credentials saved.")


if __name__ == "__main__":
    main()
