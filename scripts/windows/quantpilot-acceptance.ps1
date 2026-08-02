[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)][string]$ProductionInput,
    [string]$TdxUserDir = "D:\tongdaxin\PYPlugins\user",
    [string]$SystemDir = ".cache\quantpilot_manual_acceptance_v1",
    [ValidateRange(0, 60)][double]$Duration = 5
)
. (Join-Path $PSScriptRoot "manual_system_common_v1.ps1")
Invoke-QPManualSystem @(
    "acceptance", "--production-input", $ProductionInput,
    "--tdx-user-dir", $TdxUserDir, "--system-dir", $SystemDir,
    "--duration", [string]$Duration,
    "--tq-block-code", "QPTY", "--tq-block-name", "QP候选"
)
