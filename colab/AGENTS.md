# Colab operator contracts

- Use `cli/` for terminal operations. Use `playwright/` for browser operations.
- Read `README.md` before a launch or a recovery action.
- Use `config.WORKERS` as the registry for all seven accounts.
- Keep credentials, cookies, logs, datasets, and checkpoints outside Git.
- Use the read-only `monitor` entry point for a request to inspect or monitor.
- Select `watchdog_workers` or CLI `--recover` explicitly for recovery actions.
- Preserve active jobs during account authentication and status inspection.
- Use `control.account_lease` for managed execution actions across both projects.
- Keep account credentials shared and session metadata separate per project.
- Do not allocate replacement VMs as a side effect of read-only monitoring.
- Require an explicit resume command and a persistent checkpoint for CLI recovery.
- Keep tests under the repository `tests/` directory. Historical browser diagnostic
  files with a `test_` prefix are operational scripts, not unit tests.

- Keep Google emails, browser profile paths, notebook IDs, and Drive resource IDs
  in the external `COLAB_ACCOUNTS_FILE` configuration. Use placeholders in tracked files.
- Run `python -m colab.privacy_check` before staging Colab changes. The check does
  not inspect ignored artifacts or existing Git history.

- Keep reusable transport commands in `cli/` or `playwright/`. Keep fixed-task
  diagnostics in `playwright/diagnostics/`, runtime implementations in `remote/`,
  and notebooks in `notebooks/`.
- Record compatibility entry points in `layout.json`. A compatibility entry point
  must forward to the canonical implementation rather than duplicate its logic.
- Preserve frozen experiment snapshots. Use `tools/audit_repository.py` to
  distinguish historical copies from duplicate active source.
