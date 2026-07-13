[CmdletBinding()]
param()
. (Join-Path $PSScriptRoot "windows_runtime_common_v1.ps1")

if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
    throw "Docker is unavailable, so service stop could not be confirmed. Start Docker Desktop and retry."
}

$runtimeEnvironment = $null
try {
    $runtimeEnvironment = Push-QPRuntimeEnvironment
    Invoke-QPCompose -ComposeArguments @("stop")
    Write-Host "QuantPilot runtime services stopped. Docker volumes and local runtime data were preserved."
}
finally {
    if ($null -ne $runtimeEnvironment) {
        Restore-QPRuntimeEnvironment -Snapshot $runtimeEnvironment.Snapshot
    }
}
