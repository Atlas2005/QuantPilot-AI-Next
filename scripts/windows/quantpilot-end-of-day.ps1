[CmdletBinding()]
param([string]$SystemDir = ".cache\quantpilot_manual_system_v1")
. (Join-Path $PSScriptRoot "manual_system_common_v1.ps1")
Invoke-QPManualSystem @("end-of-day", "--system-dir", $SystemDir)
