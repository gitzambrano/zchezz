param(
    [Parameter(Position = 0)]
    [ValidateRange(1, 7)]
    [int]$WorkerId = 1,
    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]]$ColabArguments
)
$projectRoot = Split-Path (Split-Path $PSScriptRoot -Parent) -Parent
$python = Join-Path $projectRoot 'artifacts\colab\cli\venv\Scripts\python.exe'
Push-Location $projectRoot
try {
    & $python -m colab.cli.run --worker-id $WorkerId -- @ColabArguments
    $resultCode = $LASTEXITCODE
}
finally { Pop-Location }
exit $resultCode
