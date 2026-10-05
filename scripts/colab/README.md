# Colab Worker Orchestration Suite for Zchezz

This directory contains automated, headless Playwright tooling to inspect,
bootstrap, monitor, and manage remote Google Colab self-play workers for Zchezz.

## Worker Registry

| Worker ID | Name | Google Account | Notebook URL | Target Shard Prefix |
| :---: | :---: | :---: | :---: | :---: |
| 1 | Colab 1 | gustavozambrano@gmail.com | [Notebook Colab 1](https://colab.research.google.com/drive/13O4yYpM8ElgOFzo774Jps488DAPzIbDT) | sp_v507_a1_ |
| 2 | Colab 2 | lightdyn@gmail.com | [Notebook Colab 2](https://colab.research.google.com/drive/1rPSnvqg7stxwU5V8ITgpGVv02j7qVsD1) | sp_v507_a2_ |
| 3 | Colab 3 | zambraprojects@gmail.com | [Notebook Colab 3](https://colab.research.google.com/drive/1tTPVhIs4Jq0Qr1yHNPRfBDtohE3EjX9E) | sp_v507_a3_ |
| 4 | Colab 4 | zquoridor@gmail.com | [Notebook Colab 4](https://colab.research.google.com/drive/1nC1LOjwFm1LyeJtx4kxg6T7wQXym9FnA) | sp_v507_a4_ |
| 5 | Colab 5 | gustati2201@gmail.com | [Notebook Colab 5](https://colab.research.google.com/drive/1cPMl8_zEi-el5GAE8sv2Bw3T6uKDwK1i) | sp_v507_a5_ |
| 6 (331) | Colab 6 (v331) | zchezzproject@gmail.com | [Notebook Colab v331](https://colab.research.google.com/drive/1j8-gG7qApv--t2DBM8tf1gmgKjuUXiLC) | sp_v331_r2 |
| 7 (507) | Colab 7 (v507) | zbrainproject@gmail.com | [Notebook Colab v507](https://colab.research.google.com/drive/1WaoYFjPIl70cECrs9CGZEwEoMxVzBEp8) | sp_v507_r2 |

## The 3 Core Tools

### 1. Disparar: `launch_workers.py`
Bootstraps workers and starts selfplay generation without interrupting active runs:
```bash
python scripts/colab/launch_workers.py
```
- Skips workers that are already actively running (to prevent interrupting progress).
- Connects runtime if disconnected.
- Locates target cell (Remessa 2 / selfplay) and clicks execute.
- Dismisses confirmation modals ("Executar mesmo assim", "Conectar ao Google Drive", "Continuar").
- Safe against browser profile collisions.
- Override flags:
  - `--worker-ids v331 v507`: Select specific workers.
  - `--force-restart`: Force re-execution even if the worker is currently running.

### 2. Monitorar: `watchdog_workers.py`
Continuous active watchdog and keep-alive monitor:
```bash
python scripts/colab/watchdog_workers.py
```
- Keeps persistent browser sessions open with periodic micro-interactions (mouse moves) to prevent Google Colab idle timeout disconnects.
- Continuous loop reporting real-time shard progress, games, and positions.
- Detects VM disconnects and automatically reconnects and re-triggers execution.
- Captures periodic health screenshots and status sidecars into `artifacts/colab/`.

### 3. Reportar: `report_workers.py`
Snapshot inspection and structured audit:
```bash
python scripts/colab/report_workers.py
```
- Audits runtime status (`CONNECTED`, `CONNECTING`, `DISCONNECTED`).
- Audits execution status (`ACTIVE RUNNING`, `PENDING VM`, `IDLE`).
- Parses live progress: current shard ID, games completed, positions generated, and speed metrics.
- Connects via CDP if watchdog is running, or launches headlessly if idle.
- Saves clean visual screenshots for all workers to `artifacts/colab/`.
- Generates a consolidated Markdown audit report at `artifacts/colab/report.md`.

### Auxiliary Tool: `manage_runtime.py`
Administrative operations on Colab notebook environments:
```bash
# Switch accelerator from GPU to standard CPU (resolves quota blocks)
python scripts/colab/manage_runtime.py --action switch-cpu

# Terminate stuck ghost sessions in "Gerenciar sessões"
python scripts/colab/manage_runtime.py --action terminate-active

# Disconnect and delete VM environment
python scripts/colab/manage_runtime.py --action reset
```

## Resilient Execution & Architecture Safety

Google Colab free-tier VMs recycle every 12 hours. Upon recycling, the VM filesystem
is reset. The bootloader recovers the repository, builds the native engine and selfplay
binaries, mounts Google Drive, and resumes idempotent shard generation:

```python
from google.colab import drive
import os

if not os.path.exists('/content/drive/MyDrive'):
    drive.mount('/content/drive')

if not os.path.exists('/content/Zchezz'):
    !git clone https://github.com/gitzambrano/zchezz.git /content/Zchezz

%cd /content/Zchezz
!git pull origin main
!pip -q install python-chess numpy
!make -C /content/Zchezz/engine/build TOOLS_ENGINE={profile} ENGINE={profile} STATIC_FLAG="" selfplay native
!PROFILE={profile} ACCOUNT_ID={account_id} bash colab/run_selfplay_colab.sh
```

> [!IMPORTANT]
> **Profile Concurrency Safety**:
> When a watchdog or browser session is already actively running on a profile,
> the suite automatically avoids `ProcessSingleton` lock collisions and attaches
> via Chrome DevTools Protocol (CDP) or inspects latest persisted state without
> terminating active Chrome processes.
