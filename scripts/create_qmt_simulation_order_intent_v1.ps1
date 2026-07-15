[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)][string]$Symbol,
    [Parameter(Mandatory = $true)][ValidateSet("buy", "sell")][string]$Side,
    [Parameter(Mandatory = $true)][int]$Quantity,
    [Parameter(Mandatory = $true)][string]$LimitPrice,
    [Parameter(Mandatory = $true)][string]$ExpectedRedactedAccountId,
    [Parameter(Mandatory = $true)][string]$BridgeRoot,
    [string]$IntentId,
    [string]$RunLabel,
    [ValidateRange(1, 3600)][int]$ExpiresInSeconds = 900,
    [switch]$ConfirmBrokerSimulationOrder
)

if (-not $ConfirmBrokerSimulationOrder) {
    throw "No intent was created. Pass -ConfirmBrokerSimulationOrder for one deliberate broker-simulation order intent."
}

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
        (Join-Path $repositoryRoot "scripts\create_qmt_simulation_order_intent_v1.py"),
        "--symbol", $Symbol,
        "--side", $Side,
        "--quantity", $Quantity,
        "--limit-price", $LimitPrice,
        "--expected-redacted-account-id", $ExpectedRedactedAccountId,
        "--bridge-root", $BridgeRoot,
        "--expires-in-seconds", $ExpiresInSeconds,
        "--confirm-broker-simulation-order"
    )
    if ($IntentId) {
        $arguments += @("--intent-id", $IntentId)
    }
    if ($RunLabel) {
        $arguments += @("--run-label", $RunLabel)
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
    throw "QMT broker-simulation intent creation failed validation (exit $exitCode)."
}
