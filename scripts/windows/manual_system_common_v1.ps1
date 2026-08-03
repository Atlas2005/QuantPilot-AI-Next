Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

function Get-QPManualRepositoryRoot {
    return [IO.Path]::GetFullPath((Join-Path $PSScriptRoot "..\.."))
}

function Read-QPManualJson([string]$Path) {
    $jsonText = Get-Content -LiteralPath $Path -Raw -Encoding UTF8 -ErrorAction Stop
    return $jsonText | ConvertFrom-Json -ErrorAction Stop
}

function Invoke-QPManualSystem([string[]]$Arguments) {
    $root = Get-QPManualRepositoryRoot
    $python = Join-Path $root ".venv\Scripts\python.exe"
    if (-not (Test-Path $python -PathType Leaf)) {
        throw "QuantPilot Python environment is missing: $python"
    }
    $script = Join-Path $root "scripts\run_quantpilot_manual_system_v1.py"
    Push-Location $root
    try {
        & $python $script @Arguments
        if ($LASTEXITCODE -ne 0) {
            throw "QuantPilot manual system failed with exit code $LASTEXITCODE."
        }
    }
    finally {
        Pop-Location
    }
}
