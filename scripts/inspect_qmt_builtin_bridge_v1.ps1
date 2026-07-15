[CmdletBinding()]
param([switch]$Json)
. (Join-Path $PSScriptRoot "windows_runtime_common_v1.ps1")

$repositoryRoot = Get-QPRepositoryRoot
$pythonExecutable = Join-Path $repositoryRoot ".venv\Scripts\python.exe"
if (-not (Test-Path $pythonExecutable -PathType Leaf)) {
    throw "Runtime virtual environment not found. Run bootstrap_windows_runtime_v1.ps1 first."
}

$runtimeEnvironment = $null
$inspectionExitCode = 1
try {
    $runtimeEnvironment = Push-QPRuntimeEnvironment
    $env:PYTHONPATH = Join-Path $repositoryRoot "src"
    $inspectionArguments = @((Join-Path $repositoryRoot "scripts\inspect_qmt_builtin_bridge_v1.py"))
    if ($Json) {
        $inspectionArguments += @("--format", "json")
    }
    & $pythonExecutable @inspectionArguments
    $inspectionExitCode = $LASTEXITCODE
}
finally {
    if ($null -ne $runtimeEnvironment) {
        Restore-QPRuntimeEnvironment -Snapshot $runtimeEnvironment.Snapshot
    }
}
if ($inspectionExitCode -ne 0) {
    throw "QMT built-in bridge inspection failed validation (exit $inspectionExitCode)."
}
