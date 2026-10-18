"""Locate the CLI environment and isolate each account."""
import os
from pathlib import Path

from colab.config import WORKERS

ROOT = Path(__file__).resolve().parents[2]
CONFIG = {
    "worker_ids": list(WORKERS),
    "environment": ROOT / "artifacts/colab/cli/venv",
    "account_root": Path.home() / ".config/colab-cli/zquoridor",
    "session_root": Path.home() / ".config/colab-cli/projects" / ROOT.name.lower(),
    "output": ROOT / "artifacts/colab/cli",
    "request_timeout": 20,
    "revision": "ab72e524cedbfa4798464b8fd8b5279fd4ad85c4",
    "kernel_client_revision": "f18e982c3265df5e923aa9def101ab3fd737e139",
}


def account_directory(worker_id):
    """Return the private directory for a registered account."""
    if worker_id not in WORKERS:
        raise ValueError(f"Unknown worker: {worker_id}")
    return Path(CONFIG["account_root"]) / f"worker-{worker_id}"


def cli_python():
    """Locate the project installation or an explicit override."""
    override = os.environ.get("COLAB_CLI_PYTHON")
    candidate = Path(override) if override else Path(CONFIG["environment"]) / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
    if not candidate.is_file():
        raise FileNotFoundError("Install the CLI with colab/cli/setup.ps1 or set COLAB_CLI_PYTHON.")
    return str(candidate)


def session_file(worker_id):
    """Keep kernel metadata separate for each project and account."""
    account_directory(worker_id)
    path = Path(CONFIG["session_root"]) / f"worker-{worker_id}" / "sessions.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def cli_executable():
    """Locate the command beside the selected Python interpreter."""
    candidate = Path(cli_python()).with_name("colab.exe" if os.name == "nt" else "colab")
    if not candidate.is_file():
        raise FileNotFoundError("The selected environment does not contain the colab command.")
    return str(candidate)


def account_environment(worker_id):
    """Select ADC credentials without changes to the parent environment."""
    env = os.environ.copy()
    env["GOOGLE_APPLICATION_CREDENTIALS"] = str(account_directory(worker_id) / "credentials.json")
    env["PYTHONUTF8"] = "1"
    return env


def command(worker_id, arguments):
    """Build a command that preserves account isolation in child processes."""
    return [cli_executable(), "--auth", "adc", "--config", str(session_file(worker_id)), *arguments]
