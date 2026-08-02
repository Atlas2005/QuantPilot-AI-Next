[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)][string]$ProductionInput,
    [string]$TdxUserDir = "D:\tongdaxin\PYPlugins\user",
    [string]$SystemDir = ".cache\quantpilot_manual_system_v1",
    [ValidateRange(0, 86400)][double]$Duration = 14400,
    [string]$Holdings = ""
)
. (Join-Path $PSScriptRoot "manual_system_common_v1.ps1")
$arguments = @(
    "run-day", "--production-input", $ProductionInput,
    "--tdx-user-dir", $TdxUserDir, "--system-dir", $SystemDir,
    "--duration", [string]$Duration,
    "--tq-block-code", "QPTY", "--tq-block-name", "QP候选"
)
if ($Holdings) { $arguments += @("--holdings", $Holdings) }
Invoke-QPManualSystem $arguments
