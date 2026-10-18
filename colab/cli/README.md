# CLI operations

Install the pinned Windows PR with `colab/cli/setup.ps1`.
The installation is local to `artifacts/colab/cli/venv` and is ignored by Git.
The PR revision is `ab72e524cedbfa4798464b8fd8b5279fd4ad85c4`.
The Jupyter client revision is `f18e982c3265df5e923aa9def101ab3fd737e139`.
Do not use the upstream updater in this environment. It can replace the Windows changes.
`COLAB_CLI_PYTHON` can select another compatible interpreter.

Run Python module commands below with the installed CLI interpreter:

```powershell
.\artifacts\colab\cli\venv\Scripts\python.exe -m colab.cli.login --worker-ids 1 2 3 4 5 6 7
.\artifacts\colab\cli\venv\Scripts\python.exe -m colab.cli.accounts --attach
.\artifacts\colab\cli\venv\Scripts\python.exe -m colab.cli.run --worker-id 3 -- sessions
```

`accounts --attach` registers an existing runtime. It does not allocate a VM.
An account can be authenticated and have no active runtime.
With multiple runtimes, use `--worker-ids N --endpoint ENDPOINT --attach`.
The pass-through runner defaults to `sessions` on account 1.
Inspection modules accept `--show-config` without remote actions.

## Optional recovery

The monitor does not resume jobs by default. To permit bounded recovery, create
`artifacts/colab/cli/recovery.json` with an explicit policy per account:

```json
{
  "1": {
    "command": ["python", "/content/project/resume_job.py"],
    "process_marker": "resume_job.py",
    "checkpoint_path": "/content/drive/MyDrive/project/checkpoints/latest.pt",
    "cwd": "/content/project",
    "resumes_checkpoint": true
  }
}
```

Use the actual resume script and checkpoint for the job. The script must
validate its input format and engine profile before work starts.
The example paths are placeholders and are not an active recovery policy.

```powershell
.\artifacts\colab\cli\venv\Scripts\python.exe -m colab.cli.recover
.\artifacts\colab\cli\venv\Scripts\python.exe -m colab.cli.monitor --recover
```

The first command validates and lists configured policies. Add `--apply` for
an explicit recovery attempt. The monitor permits recovery only for an idle
or stalled observation. It permits at most three execution attempts with
900 seconds between checks for one account.

Before execution, a separate control kernel checks the Linux process list.
An active process with the configured exact argument prevents a duplicate.
The checkpoint must be a nonempty file under `/content/drive/MyDrive/`.
The work directory must already exist. Recovery never kills a process or
allocates a replacement VM. Missing checkpoints, authentication failures,
and unavailable runtimes require operator attention or the other transport.
The temporary control kernel closes after the check. Notebook kernels remain active.
Recovery output goes to `/tmp/colab-recovery-N.log` on that runtime.

The monitor reports file metadata, not a checksum or a full checkpoint validation.
A stable file set can mean a stalled job or a long batch. Set the threshold
for the expected batch duration. Inspect both transports before intervention.

Account identity fields load from the external `COLAB_ACCOUNTS_FILE` configuration.
Do not add emails or notebook IDs to the registry source. Run
`python -m colab.privacy_check` before staging changes.
