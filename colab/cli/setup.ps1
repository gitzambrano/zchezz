param([string]$Python = 'python')
$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path (Split-Path $PSScriptRoot -Parent) -Parent
$environment = Join-Path $projectRoot 'artifacts\colab\cli\venv'
if (-not (Test-Path (Join-Path $environment 'Scripts\python.exe'))) {
    & $Python -m venv $environment
    if ($LASTEXITCODE -ne 0) { throw 'Could not create the CLI environment.' }
}
$interpreter = Join-Path $environment 'Scripts\python.exe'
& $interpreter -m pip install 'google-colab-cli @ git+https://github.com/googlecolab/google-colab-cli.git@ab72e524cedbfa4798464b8fd8b5279fd4ad85c4' 'jupyter-kernel-client @ git+https://github.com/googlecolab/jupyter-kernel-client.git@f18e982c3265df5e923aa9def101ab3fd737e139'
if ($LASTEXITCODE -ne 0) { throw 'Could not install the pinned CLI packages.' }
& $interpreter -m pip check
if ($LASTEXITCODE -ne 0) { throw 'The CLI dependencies failed verification.' }
& (Join-Path $environment 'Scripts\colab.exe') version
