"""Launch and bootstrap Google Colab workers.

Supports both official CLI (default, lightweight) and Playwright (browser fallback) transports.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
from typing import Any, Dict, List

ROOT = Path(__file__).resolve().parents[1]
colab_dir = str(Path(__file__).resolve().parent)
while colab_dir in sys.path:
    sys.path.remove(colab_dir)
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from colab.config import WORKERS, BOOTLOADER_TEMPLATE
from colab.control import account_lease
from colab.cli.settings import CONFIG as CLI_CONFIG, command, account_environment, session_file, account_directory
from colab.cli.backend import client, attach

PROJECT_NAME = ROOT.name.lower()
DEFAULT_WORKERS = [6, 7] if "zchezz" in PROJECT_NAME else [1, 2, 3, 4, 5]

CONFIG: Dict[str, Any] = {
    "backend": "cli",
    "worker_ids": DEFAULT_WORKERS,
    "gpu": "T4",
    "force_restart": False,
    "timeout": 300,
}


def build_bootstrap_script(worker: Dict[str, Any], project: str, force_restart: bool = False) -> str:
    """Generate remote Python bootstrap code executed inside the Colab VM."""
    wid = worker.get("worker_id", 1)
    worker_proj = worker.get("project", "zchezz" if wid in (6, 7) else "zquoridor")
    if worker_proj == "zchezz":
        profile = worker.get("profile", "v507")
        account_id = worker.get("account_id", wid)
        return f"""import os, subprocess, sys, time

# 1. Mount Google Drive with safe timeout
if not os.path.exists('/content/drive/MyDrive'):
    try:
        subprocess.run([sys.executable, '-c', 'from google.colab import drive; drive.mount("/content/drive")'], input=b'\\n', capture_output=True, timeout=15)
        if os.path.exists('/content/drive/MyDrive'):
            print("[OK] Google Drive mounted successfully.")
        else:
            print("[WARN] Drive mount waiting for authorization.")
    except Exception as e:
        print(f"[WARN] Drive mount status: {{e}}")
os.makedirs('/content/drive/MyDrive', exist_ok=True)

# 2. Clone or update repository
repo_dir = '/content/Zchezz'
if not os.path.exists(os.path.join(repo_dir, '.git')):
    print("[INFO] Cloning Zchezz repository...")
    subprocess.run(['git', 'clone', 'https://github.com/gitzambrano/zchezz.git', repo_dir], check=True)

os.chdir(repo_dir)
print("[INFO] Pulling latest code from main...")
subprocess.run(['git', 'fetch', 'origin'], check=True)
subprocess.run(['git', 'reset', '--hard', 'origin/main'], check=True)

# Patch drive mount exit in runner if present
sh_path = os.path.join(repo_dir, 'colab', 'remote', 'run_selfplay_colab.sh')
if os.path.exists(sh_path):
    try:
        txt = open(sh_path, 'r', encoding='utf-8').read()
        txt = txt.replace('exit 1\\nfi\\nmkdir -p "${{DRIVE_DIR}}"', 'fi\\nmkdir -p "${{DRIVE_DIR}}"')
        open(sh_path, 'w', encoding='utf-8').write(txt)
    except Exception:
        pass

# 3. Dependencies
print("[INFO] Installing python dependencies...")
subprocess.run([sys.executable, '-m', 'pip', '-q', 'install', 'python-chess', 'numpy'], check=True)

# 4. Build engine
print("[INFO] Compiling engine binaries for {profile}...")
build_dir = os.path.join(repo_dir, 'engine', 'build')
if '{profile}'.startswith('v5'):
    subprocess.run(['make', '-C', build_dir, 'TOOLS_ENGINE={profile}', 'STATIC_FLAG=', 'selfplay'], check=True)
else:
    subprocess.run(['make', '-C', build_dir, 'ENGINE={profile}', 'STATIC_FLAG=', 'native'], check=True)

# 5. Check if already active
active = False
for entry in os.listdir('/proc'):
    if not entry.isdigit():
        continue
    try:
        cmdline = open(f'/proc/{{entry}}/cmdline', 'rb').read().split(b'\\0')
        if any(b'run_selfplay_colab.sh' in arg or b'selfplay.exe' in arg or b'selfplay' in arg for arg in cmdline):
            if {repr(force_restart)}:
                import signal
                try:
                    os.kill(int(entry), signal.SIGTERM)
                except Exception:
                    pass
            else:
                active = True
                break
    except Exception:
        pass

if active:
    print("[INFO] Selfplay worker is already running in background.")
else:
    log_path = '/content/selfplay_{profile}_worker_{account_id}.log'
    log_file = open(log_path, 'a', buffering=1)
    env = os.environ.copy()
    env['PROFILE'] = '{profile}'
    env['ACCOUNT_ID'] = '{account_id}'
    env['TARGET_POSITIONS'] = '50000000'
    env['NODES'] = '5000'
    env['MOVETIME'] = '50'
    if '{profile}'.startswith('v5'):
        env['TARGET_POSITIONS'] = '60000000'
        env['MOVETIME'] = '200'
        env['MOVETIME_FINAL'] = '50'
        env['MOVETIME_PLIES'] = '60'
        env['MOVETIME_DECAY'] = 'linear'
        env['NODES'] = '0'
        env['TEMPERATURE'] = '1.2'
        env['TEMP_DECAY'] = 'linear'
        env['TEMP_PLIES'] = '60'
        env['TEMP_FINAL'] = '0.02'
        env['RANDOM_PLIES'] = '0'

    cmd = ['bash', 'colab/remote/run_selfplay_colab.sh']
    proc = subprocess.Popen(cmd, cwd=repo_dir, env=env, stdout=log_file, stderr=subprocess.STDOUT, start_new_session=True)
    time.sleep(2)
    if proc.poll() is None:
        print(f"[OK] Selfplay background worker started with PID {{proc.pid}}. Logging to {{log_path}}")
    else:
        print(f"[ERROR] Process exited immediately with code {{proc.poll()}}")
"""
    else:
        # Zquoridor bootstrap: Wall Drops (workers 1-2) or Gumbel Sims (workers 3-5)
        output_dir = worker.get("output_dir", f"/content/drive/MyDrive/zquoridor_data/worker_{wid}")
        cli_cmd = worker.get("cli_command", f"python -u tools/selfplay/run_colab_worker.py --worker-id {wid}")
        job_label = worker.get("job_label", f"Worker {wid}")
        return f"""import os, subprocess, sys, time, shlex
from pathlib import Path

# 1. Mount Google Drive with safe timeout
if not os.path.exists('/content/drive/MyDrive'):
    try:
        subprocess.run([sys.executable, '-c', 'from google.colab import drive; drive.mount("/content/drive")'], input=b'\\n', capture_output=True, timeout=15)
        if os.path.exists('/content/drive/MyDrive'):
            print("[OK] Google Drive mounted successfully.")
        else:
            print("[WARN] Drive mount waiting for authorization.")
    except Exception as e:
        print(f"[WARN] Drive mount status: {{e}}")

# 2. Clone or update repository
repo_dir = '/content/zquoridor'
if not os.path.exists(os.path.join(repo_dir, '.git')):
    print("[INFO] Cloning Zquoridor repository...")
    subprocess.run(['git', 'clone', 'https://github.com/gitzambrano/zquoridor.git', repo_dir], check=True)

os.chdir(repo_dir)
print("[INFO] Pulling latest code from main...")
subprocess.run(['git', 'fetch', 'origin'], check=True)
subprocess.run(['git', 'reset', '--hard', 'origin/main'], check=True)

# 3. Dependencies
print("[INFO] Installing python dependencies...")
subprocess.run([sys.executable, '-m', 'pip', '-q', 'install', 'numpy'], check=True)

# 4. Build native C++ engine (version 4.10) with AVX2 and FMA
runtime_dir = '/content/zquoridor_runtime'
os.makedirs(runtime_dir, exist_ok=True)
zq_bin = os.path.join(runtime_dir, 'zquoridor_uci')
print('[INFO] Compiling native C++ engine (version 4.10) with AVX2 and FMA...', flush=True)
subprocess.run(['g++', '-O3', '-std=c++17', '-mavx2', '-mfma',
                '-I', os.path.join(repo_dir, 'src'),
                os.path.join(repo_dir, 'tools', 'external', 'zquoridor_uci.cpp'),
                '-o', zq_bin], check=True)
os.chmod(zq_bin, 0o755)

# Verify UCI identity
try:
    chk = subprocess.run([zq_bin], input='uci\\nquit\\n', capture_output=True, text=True, check=True, cwd=repo_dir)
    ver_lines = [l.strip() for l in chk.stdout.splitlines() if 'id name' in l]
    print('[INFO] Engine verification:', ver_lines, flush=True)
except Exception as e:
    print('[WARN] Verification warning:', e)

# 5. Clean stale temporary/backup files and sync targets.npz
out_path = Path('{output_dir}')
if out_path.is_dir():
    for stale_tmp in out_path.glob('*.tmp*'):
        try:
            stale_tmp.unlink()
        except Exception:
            pass
    for stale_bak in out_path.glob('*.bak*'):
        try:
            stale_bak.unlink()
        except Exception:
            pass
    if (out_path / 'positions.jsonl').is_file() and (out_path / 'targets.jsonl').is_file():
        try:
            print('[INFO] Synchronizing targets.npz from canonical JSONL records...', flush=True)
            subprocess.run([sys.executable, 'tools/rebuild_npz_from_jsonl.py', '--dir', str(out_path), '--no-backup'], check=True)
        except Exception as e:
            print('[WARN] Rebuild npz note:', e)

# 6. Check if already active
active = False
for entry in os.listdir('/proc'):
    if not entry.isdigit():
        continue
    try:
        cmdline = open(f'/proc/{{entry}}/cmdline', 'rb').read().split(b'\\0')
        if any(b'generate_wall_drops.py' in arg or b'generate_gumbel_sims.py' in arg or b'run_colab_worker.py' in arg for arg in cmdline):
            if {repr(force_restart)}:
                import signal
                try:
                    os.kill(int(entry), signal.SIGTERM)
                except Exception:
                    pass
            else:
                active = True
                break
    except Exception:
        pass

if active:
    print(f"[INFO] Zquoridor worker {wid} is already running in background.")
else:
    log_path = f'/content/worker_{wid}.log'
    log_file = open(log_path, 'a', buffering=1)
    cmd = shlex.split('{cli_cmd}')
    print(f"[INFO] Launching: {job_label}", flush=True)
    proc = subprocess.Popen(cmd, cwd=repo_dir, stdout=log_file, stderr=subprocess.STDOUT, start_new_session=True)
    time.sleep(2)
    if proc.poll() is None:
        print(f"[OK] Zquoridor worker {wid} started with PID {{proc.pid}}. Logging to {{log_path}}")
    else:
        print(f"[ERROR] Process exited immediately with code {{proc.poll()}}")
"""


def launch_worker_cli(worker_id: int, gpu: str = "T4", force_restart: bool = False, timeout: int = 300) -> bool:
    """Launch a single worker using the official Colab CLI."""
    w = WORKERS[worker_id]
    account = w.get("account", f"worker-{worker_id}")
    session_name = f"worker-{worker_id}"

    creds_path = account_directory(worker_id) / "credentials.json"
    if not creds_path.is_file():
        print(f"Worker {worker_id} ({account}): Not authenticated. Run 'python -m colab.playwright.authorize_cli --worker-ids {worker_id}' first.")
        return False

    env = account_environment(worker_id)
    with account_lease([worker_id], f"CLI launch ({PROJECT_NAME})"):
        # 1. Check active runtime on server
        assignments = client(worker_id).list_assignments()
        if assignments:
            print(f"Worker {worker_id} ({account}): Found active runtime {assignments[0].endpoint}. Attaching as '{session_name}'...")
            attach(worker_id, endpoint=assignments[0].endpoint, name=session_name)
        else:
            print(f"Worker {worker_id} ({account}): Allocating new Colab GPU session ({gpu})...")
            new_cmd = command(worker_id, ["new", "-s", session_name, "--gpu", gpu])
            res = subprocess.run(new_cmd, env=env)
            if res.returncode != 0:
                print(f"Worker {worker_id}: Failed to allocate new session.")
                return False
            time.sleep(2)

            try:
                attach(worker_id, name=session_name)
            except Exception as err:
                print(f"Worker {worker_id}: Warning attaching runtime: {err}")

        # 2. Mount Google Drive via CLI credentials propagation
        print(f"Worker {worker_id} ({account}): Ensuring Google Drive is mounted...")
        dm_cmd = command(worker_id, ["drivemount", "-s", session_name])
        try:
            dm_proc = subprocess.run(dm_cmd, env=env, input="", capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=25)
            if "Credentials propagated" in dm_proc.stdout or "already mounted" in dm_proc.stdout:
                print(f"Worker {worker_id}: Google Drive mounted via CLI.")
            elif "Drive Authorization needed" in dm_proc.stdout:
                print(f"Worker {worker_id}: [AUTH PROMPT] Drive authorization required. Will attempt fallback in VM.")
            else:
                out_lines = [l for l in dm_proc.stdout.strip().splitlines() if l.strip()]
                if out_lines:
                    print(f"Worker {worker_id}: drivemount: {out_lines[-1]}")
        except Exception as dm_err:
            print(f"Worker {worker_id}: drivemount note: {dm_err}")

        # 3. Generate bootstrap script
        script_content = build_bootstrap_script(w, PROJECT_NAME, force_restart=force_restart)
        with tempfile.NamedTemporaryFile("w", suffix=".py", delete=False, encoding="utf-8") as tmp:
            tmp.write(script_content)
            tmp_path = tmp.name

        try:
            print(f"Worker {worker_id} ({account}): Executing bootstrap on session '{session_name}'...")
            exec_cmd = command(worker_id, ["exec", "-s", session_name, "-f", tmp_path, "--timeout", str(timeout)])
            res = subprocess.run(exec_cmd, env=env)
            return res.returncode == 0
        finally:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--backend", choices=["cli", "playwright"], default=CONFIG["backend"],
                        help="Transport backend to use (default: cli)")
    parser.add_argument("--worker-ids", type=int, nargs="+", default=CONFIG["worker_ids"],
                        help=f"Worker IDs to launch (default: {CONFIG['worker_ids']})")
    parser.add_argument("--gpu", default=CONFIG["gpu"], choices=["T4", "L4", "A100"],
                        help="GPU accelerator variant (default: T4)")
    parser.add_argument("--force-restart", action="store_true",
                        help="Force restarting worker process")
    parser.add_argument("--headed", action="store_true",
                        help="Playwright only: Run browser in visible headed mode")
    parser.add_argument("--show-config", action="store_true",
                        help="Show effective configuration and exit")
    args = parser.parse_args()

    cfg = {
        "backend": args.backend,
        "worker_ids": args.worker_ids,
        "gpu": args.gpu,
        "force_restart": args.force_restart,
        "timeout": CONFIG["timeout"],
    }
    if args.show_config:
        print(json.dumps(cfg, indent=2))
        return

    print("=" * 70)
    print(f"{PROJECT_NAME.upper()} COLAB WORKER LAUNCHER")
    print("=" * 70)
    print(f"Backend: {cfg['backend']}")
    print(f"Target workers: {cfg['worker_ids']}")
    print(f"GPU accelerator: {cfg['gpu']}")
    print(f"Force restart: {cfg['force_restart']}")
    print("=" * 70)

    if cfg["backend"] == "playwright":
        from colab.playwright.launch_workers import launch_worker, CONFIG as PW_CONFIG, create_artifacts_dir
        pw_cfg = dict(PW_CONFIG)
        pw_cfg["worker_ids"] = cfg["worker_ids"]
        if cfg["force_restart"]:
            pw_cfg["skip_if_running"] = False
        if args.headed:
            pw_cfg["headless"] = False

        artifacts_path = create_artifacts_dir(pw_cfg["artifacts_dir"])
        for wid in cfg["worker_ids"]:
            if wid not in WORKERS:
                print(f"Skipping unknown worker: {wid}")
                continue
            w = WORKERS[wid]
            print(f"\n[Playwright] Launching {w['name']} ({w['account']})...")
            res = launch_worker(
                worker=w,
                skip_if_running=pw_cfg["skip_if_running"],
                headless=pw_cfg["headless"],
                timeout_ms=pw_cfg["page_timeout_ms"],
                delay_s=pw_cfg["load_delay_seconds"],
                wait_run_s=pw_cfg["wait_after_run_seconds"],
                artifacts_dir=artifacts_path,
            )
            print(f"  Action taken: {res.get('action_taken')}")
            print(f"  State: {'RUNNING' if res.get('running') else 'IDLE'}")
    else:
        # CLI backend
        for wid in cfg["worker_ids"]:
            if wid not in WORKERS:
                print(f"Skipping unknown worker: {wid}")
                continue
            print(f"\n[CLI] Launching Worker {wid}...")
            ok = launch_worker_cli(wid, gpu=cfg["gpu"], force_restart=cfg["force_restart"], timeout=cfg["timeout"])
            print(f"  Result: {'[OK]' if ok else '[FAILED]'}")

    print("\nLaunch sequence completed.")


if __name__ == "__main__":
    main()
