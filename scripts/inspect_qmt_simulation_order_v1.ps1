[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)][string]$BridgeRoot,
    [Parameter(Mandatory = $true)][string]$IntentId,
    [switch]$Json
)

. (Join-Path $PSScriptRoot "windows_runtime_common_v1.ps1")

$repositoryRoot = Get-QPRepositoryRoot
$pythonExecutable = Join-Path $repositoryRoot ".venv\Scripts\python.exe"
if (-not (Test-Path $pythonExecutable -PathType Leaf)) {
    throw "Runtime virtual environment not found. Run bootstrap_windows_runtime_v1.ps1 first."
}

$runtimeEnvironment = $null
$exitCode = 1
try {
    $runtimeEnvironment = Push-QPRuntimeEnvironment
    $env:PYTHONPATH = Join-Path $repositoryRoot "src"
    $arguments = @(
        (Join-Path $repositoryRoot "scripts\inspect_qmt_simulation_order_v1.py"),
        "--bridge-root", $BridgeRoot,
        "--intent-id", $IntentId
    )
    if ($Json) {
        $arguments += @("--format", "json")
    }
    & $pythonExecutable @arguments
    $exitCode = $LASTEXITCODE
}
finally {
    if ($null -ne $runtimeEnvironment) {
        Restore-QPRuntimeEnvironment -Snapshot $runtimeEnvironment.Snapshot
    }
}
if ($exitCode -ne 0) {
    throw "QMT broker-simulation order inspection failed validation (exit $exitCode)."
}
