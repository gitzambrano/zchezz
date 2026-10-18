# Historical browser diagnostics

This directory preserves targeted inspection, repair, and download utilities.
These scripts are not the default monitor or launcher. A file with a `test_`
prefix here is an operational browser utility, not an automated unit test.
Some utilities reconnect runtimes, execute cells, or change Drive sharing.
Select a utility only for an explicit request for that action.

Use `python -m colab.playwright.monitor` for read-only observation.
Use the parent directory launchers for routine execution and recovery.
Account identities and private Drive resources load from local configuration.
