[CmdletBinding()]
param([switch]$Json)
. (Join-Path $PSScriptRoot "windows_runtime_common_v1.ps1")

$root = Get-QPRepositoryRoot
$python = Join-Path $root ".venv\Scripts\python.exe"
if (-not (Test-Path $python -PathType Leaf)) {
    throw "Runtime virtual environment not found. Run bootstrap_windows_runtime_v1.ps1 first."
}

$runtimeEnvironment = $null
$doctorExitCode = 1
try {
    $runtimeEnvironment = Push-QPRuntimeEnvironment
    $env:PYTHONPATH = Join-Path $root "src"
    $format = "text"
    if ($Json) {
        $format = "json"
    }
    & $python (Join-Path $root "scripts\runtime_doctor_v1.py") --format $format --strict
    $doctorExitCode = $LASTEXITCODE
    if (-not $Json -and (Get-Command docker -ErrorAction SilentlyContinue)) {
        Invoke-QPCompose -ComposeArguments @("ps")
    }
    elseif (-not $Json) {
        Write-Host "NOT_READY      docker_services: Docker executable is not on PATH."
    }
}
finally {
    if ($null -ne $runtimeEnvironment) {
        Restore-QPRuntimeEnvironment -Snapshot $runtimeEnvironment.Snapshot
    }
}
if ($doctorExitCode -ne 0) {
    throw "Runtime status found one or more missing required components (doctor exit $doctorExitCode)."
}
