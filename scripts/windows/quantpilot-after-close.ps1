[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)][string]$ProductionInput,
    [string]$TdxUserDir = "D:\tongdaxin\PYPlugins\user",
    [string]$SystemDir = ".cache\quantpilot_manual_system_v1",
    [string]$DeepSeekModel = ""
)
. (Join-Path $PSScriptRoot "manual_system_common_v1.ps1")
$arguments = @(
    "after-close", "--production-input", $ProductionInput,
    "--tdx-user-dir", $TdxUserDir, "--system-dir", $SystemDir,
    "--tq-block-code", "QPTY", "--tq-block-name", "QP候选"
)
if ($DeepSeekModel) { $arguments += @("--deepseek-model", $DeepSeekModel) }
Invoke-QPManualSystem $arguments
