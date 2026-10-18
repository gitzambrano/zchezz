"""Load account identities from private local configuration."""
import json
import os
from pathlib import Path

CONFIG = {"path": Path.home() / ".config/colab-cli/accounts.local.json"}
ACCOUNT_FIELDS = {"account", "profile_dir", "notebook_url", "cdp_port"}


def load():
    """Keep personal account data outside the repository."""
    path = Path(os.environ.get("COLAB_ACCOUNTS_FILE", CONFIG["path"]))
    return json.loads(path.read_text(encoding="utf-8")) if path.is_file() else {}


def apply_accounts(workers, project):
    """Apply local identity overrides without changes to workload settings."""
    data = load().get("projects", {}).get(project, {})
    for key, values in data.items():
        worker = int(key)
        if worker in workers:
            workers[worker].update({name: value for name, value in values.items() if name in ACCOUNT_FIELDS})


def resource(name):
    """Read a private Drive resource without a public fallback."""
    value = load().get("resources", {}).get(name)
    if not value:
        raise ValueError(f"Configure the private Drive resource {name} in COLAB_ACCOUNTS_FILE.")
    return value
