[CmdletBinding()]
param([switch]$SkipDocker)
. (Join-Path $PSScriptRoot "windows_runtime_common_v1.ps1")

$root = Get-QPRepositoryRoot
$python = Join-Path $root ".venv\Scripts\python.exe"
if (-not (Test-Path $python -PathType Leaf)) {
    throw "Runtime virtual environment not found. Run bootstrap_windows_runtime_v1.ps1 first."
}
if (-not $SkipDocker -and -not (Get-Command docker -ErrorAction SilentlyContinue)) {
    throw "Docker is required for startup. Start Docker Desktop, then retry."
}

$runtimeEnvironment = $null
try {
    $runtimeEnvironment = Push-QPRuntimeEnvironment
    $env:PYTHONPATH = Join-Path $root "src"
    if (-not $SkipDocker) {
        Invoke-QPCompose -ComposeArguments @("up", "-d")
        Wait-QPControlCenter
    }
    $doctorArguments = @((Join-Path $root "scripts\runtime_doctor_v1.py"), "--strict")
    if ($SkipDocker) {
        $doctorArguments += "--skip-services"
    }
    & $python @doctorArguments
    if ($LASTEXITCODE -ne 0) {
        throw "Runtime Doctor found a missing required runtime component (exit $LASTEXITCODE)."
    }
    if ($SkipDocker) {
        Write-Host "Runtime configuration is valid; Docker startup and service probes were skipped."
    }
    else {
        Write-Host "QuantPilot runtime services are ready. Broker connectivity and order submission remain disabled."
        Write-Host "Next: powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\status_windows_runtime_v1.ps1"
    }
}
finally {
    if ($null -ne $runtimeEnvironment) {
        Restore-QPRuntimeEnvironment -Snapshot $runtimeEnvironment.Snapshot
    }
}
