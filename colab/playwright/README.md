# Browser operations

Run these commands from the repository root with the existing Playwright Python environment:

```powershell
python -m colab.playwright.monitor --once --open-profiles
python -m colab.playwright.monitor --worker-ids 1 2 3 4 5 6 7 --open-profiles
python -m colab.playwright.authorize_cli --worker-ids 1 2 3 4 5 6 7
python -m colab.playwright.report_workers --show-config
python -m colab.playwright.watchdog_workers --show-config
```

The new `monitor` is read-only. The existing `watchdog_workers` can reconnect
and execute notebook cells. Choose the appropriate entry point explicitly.
The account registry contains seven accounts. Existing job controllers retain
their previous default worker sets. Use their account flags to select another set.
Account availability does not authorize replacing a job already on that runtime.

Canonical browser scripts now live in this directory. Legacy Python imports
through `colab` remain available during the directory migration. Legacy file
paths such as `python colab/watchdog_workers.py` no longer exist. Use
`python -m colab.playwright.watchdog_workers` instead.

The authorization helper reuses a fixed or dynamic Chrome debugging port for
the account profile. If no session exists, it opens a visible Chrome profile.
Phone verification remains with the user. The helper does not store passwords.
After consent, it checks the account email and saves CLI credentials outside Git.
Both projects use those credentials. Notebook session metadata stays separate.

Read-only monitoring can run beside a controller. A second managed controller
for the same account fails with an account lock diagnostic. Stop the first
controller before a switch to CLI execution or another browser controller.
