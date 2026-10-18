# Colab transports

Use either transport for the same seven Google accounts. Select the transport by
its entry point. Credentials stay outside Git. Reports stay under `artifacts/colab`.

| Directory | Purpose |
| --- | --- |
| `cli/` | Install, authorize, execute commands, monitor artifacts, and resume configured jobs through the official CLI. |
| `remote/` | Execute self-play, training, and runtime helpers inside a Colab VM. |
| `notebooks/` | Store notebook entry points. |
| `playwright/diagnostics/` | Preserve targeted historical diagnostics outside the current command surface. |
| `playwright/` | Authorize browser profiles, execute notebook cells, inspect notebook output, and run existing browser controllers. |
| `config.py` | Share the account registry and project bootloaders. |
| `monitoring.py` | Classify progress and write monitor reports. |
| `control.py` | Prevent concurrent managed controllers for one account across both projects. |

## Accounts

Personal emails, notebook URLs, and browser profile paths come from
`~/.config/colab-cli/accounts.local.json`, outside both repositories.
`COLAB_ACCOUNTS_FILE` can select another private file.
Tracked defaults contain placeholders only. `accounts.example.json` documents
the private file schema. Copy the example outside the repository before it
receives real account data. Preserve this local file when
reinstalling the tools. Do not copy it into a tracked source file.


| ID | Private account slot |
| --- | --- |
| 1 | `worker-1` |
| 2 | `worker-2` |
| 3 | `worker-3` |
| 4 | `worker-4` |
| 5 | `worker-5` |
| 6 | `worker-6` |
| 7 | `worker-7` |

Both repositories use the same credentials per account at
`~/.config/colab-cli/zquoridor/worker-N/credentials.json`. The `zquoridor`
directory name remains for compatibility with the initial installation.
Session files are separate at `~/.config/colab-cli/projects/PROJECT/worker-N/`.
The account registry defines browser profiles and notebook URLs.
Authentication does not allocate a runtime or start a job.

## Monitor through the CLI

Run these commands from the repository root:

```powershell
.\colab\cli\setup.ps1
.\artifacts\colab\cli\venv\Scripts\python.exe -m colab.cli.accounts --attach
.\artifacts\colab\cli\venv\Scripts\python.exe -m colab.cli.monitor --once
.\artifacts\colab\cli\venv\Scripts\python.exe -m colab.cli.monitor
```

The monitor reads runtime and file metadata. It does not execute cells or
allocate VMs. It checks all seven accounts by default. Use `--worker-ids 1 2`
for a subset. Use `--interval 60` and `--stall-seconds 900` to set the observation
interval and stall threshold. Use `--max-cycles 2` for a bounded trial.
The JSON report is `artifacts/colab/cli/monitor.json`.
A checkpoint listed as `present_unverified` confirms file presence only.
It does not prove that the checkpoint is valid or complete.

## Monitor through Playwright

```powershell
python -m colab.playwright.monitor --once --open-profiles
python -m colab.playwright.monitor --open-profiles
```

The read-only browser monitor observes notebook output and connection state.
It does not reconnect runtimes or execute cells. By default, it attaches only
to existing browser debugging sessions. `--open-profiles` permits a temporary
headless browser for a profile that has no debugging session.
The JSON report is `artifacts/colab/playwright/monitor.json`.
This transport does not verify persisted checkpoint files.

Both read-only monitors can run at the same time. Their reports are separate.
If a transport fails, run the other monitor and compare the observations.
A disconnected notebook page does not by itself prove that its VM stopped.
The existing `playwright/watchdog_workers.py` provides browser recovery and
cell re-execution. Select it explicitly when those actions are required.

## Execute through the CLI

```powershell
.\colab\cli\colab.ps1 1 sessions
.\colab\cli\colab.ps1 1 exec -s zq-worker-1 -f C:\path\job.py
.\colab\cli\colab.ps1 7 new -s zq-worker-7
```

The wrapper selects credentials and session metadata for the chosen account.
The CLI does not select an engine profile or change installed engine weights.
The project bootloader remains responsible for engine prerequisites.

## Authentication and controllers

For terminal authorization, run `python -m colab.cli.login` with the CLI
interpreter above. For authorization through the existing browser profiles, run
`python -m colab.playwright.authorize_cli`. Use `--worker-ids` for a subset.
Complete phone verification in the Google prompt when required.
The authorization helper checks the email before it saves credentials.

Managed execution and recovery commands use account locks under
`~/.config/colab-cli/control`. A lock applies across both projects and transports.
Stop the old controller before a switch of execution transport. Controllers
that started before this update do not hold the new locks. Direct third-party
CLI commands also do not participate in these project locks.

Read [CLI operations](cli/README.md) and [browser operations](playwright/README.md)
for authentication, recovery policies, and existing controller entry points.
Colab can reclaim a VM. Preserve checkpoints outside the VM and use commands
that explicitly support resume. Neither monitor guarantees uninterrupted compute.

Remote entry points remain `colab/remote/run_selfplay_colab.sh`, `colab/remote/run_train_colab.sh`,
and `colab/notebooks/zchezz_selfplay_colab.ipynb`. Bare engine workflows retain the repository
default profile. The supported secondary profile remains explicit.

## Check privacy before a commit

Run `python -m colab.privacy_check` in each repository. The check reports file
paths and finding categories without private values. It compares configured
personal identifiers and checks for OAuth token literals and private keys.
It excludes ignored files, unreadable files, files over 8 MB, and Git history.
The ignore rules cover local account settings, credentials, tokens, cookies,
browser profiles, traces, screenshots, and reports. Ignore rules do not remove
information from existing commits.

## Canonical paths and compatibility

`layout.json` records the directory roles and compatibility entry points.
A compatibility entry point forwards to the canonical implementation. It does
not contain a second copy of the runner. Existing notebooks can keep their
old commands while new automation uses `remote/`.

Historical diagnostics live in `playwright/diagnostics/`. Some diagnostics
change runtime state. Inspect the selected diagnostic before execution.
Use the public monitors for routine observation. Use the public launchers
and recovery commands for controlled execution.

Frozen experiment snapshots remain in their historical directories. They do
not supply the current Colab command surface. Generated output stays under
`artifacts/colab`. Private account data stays in the external configuration.

Run `python tools/audit_repository.py` to check source organization. Its report
is `artifacts/repository_organization/audit.json`. The check identifies active
duplicate source groups and missing compatibility targets without source deletion.
