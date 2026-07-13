Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

function Get-QPRepositoryRoot {
    return (Split-Path -Parent $PSScriptRoot)
}

function Get-QPRuntimeHome {
    if ($env:QUANTPILOT_RUNTIME_HOME) {
        return [IO.Path]::GetFullPath($env:QUANTPILOT_RUNTIME_HOME)
    }
    if (-not $env:LOCALAPPDATA) {
        throw "LOCALAPPDATA is required for the Windows QuantPilot runtime."
    }
    return (Join-Path $env:LOCALAPPDATA "QuantPilot\runtime")
}

function Assert-QPRuntimeHomeOutsideRepository {
    $trimCharacters = [char[]]@("\", "/")
    $repository = [IO.Path]::GetFullPath((Get-QPRepositoryRoot)).TrimEnd($trimCharacters)
    $runtimeHome = [IO.Path]::GetFullPath((Get-QPRuntimeHome)).TrimEnd($trimCharacters)
    $repositoryPrefix = $repository + [IO.Path]::DirectorySeparatorChar
    if ($runtimeHome.Equals($repository, [StringComparison]::OrdinalIgnoreCase) -or
        $runtimeHome.StartsWith($repositoryPrefix, [StringComparison]::OrdinalIgnoreCase)) {
        throw "QUANTPILOT_RUNTIME_HOME must be outside the Git repository."
    }
}

function Get-QPRuntimeConfigPath {
    return (Join-Path (Get-QPRuntimeHome) "config\runtime.json")
}

function Get-QPDeepSeekSkipMarkerPath {
    return (Join-Path (Get-QPRuntimeHome) "config\deepseek_optional_skipped")
}

function Get-QPSecretPath([string]$Name) {
    if ($Name -notmatch "^[a-z0-9_]+$") {
        throw "Invalid runtime secret name."
    }
    return (Join-Path (Get-QPRuntimeHome) "secrets\$Name.secret")
}

function Initialize-QPRuntimeDirectories {
    Assert-QPRuntimeHomeOutsideRepository
    $runtimeHome = Get-QPRuntimeHome
    foreach ($name in @("config", "secrets", "logs", "state", "reports", "cache")) {
        New-Item -ItemType Directory -Force -Path (Join-Path $runtimeHome $name) | Out-Null
    }
}

function Move-QPFileAtomically([string]$TemporaryPath, [string]$DestinationPath) {
    if (Test-Path $DestinationPath -PathType Leaf) {
        [IO.File]::Replace($TemporaryPath, $DestinationPath, $null)
    }
    else {
        [IO.File]::Move($TemporaryPath, $DestinationPath)
    }
}

function Write-QPRuntimeConfig {
    Initialize-QPRuntimeDirectories
    $runtimeHome = Get-QPRuntimeHome
    $payload = [ordered]@{
        schema_version = 1
        platform = "windows"
        timezone = "Asia/Shanghai"
        broker_provider = "none"
        reporting_enabled = $true
        grafana_enabled = $true
        deepseek_live_calls_enabled = $false
        runtime_home = $runtimeHome
        postgres_dsn_env_var = "QUANTPILOT_POSTGRES_DSN"
        grafana_url = "http://localhost:3000"
        paths = [ordered]@{
            config = (Join-Path $runtimeHome "config")
            secrets = (Join-Path $runtimeHome "secrets")
            logs = (Join-Path $runtimeHome "logs")
            state = (Join-Path $runtimeHome "state")
            reports = (Join-Path $runtimeHome "reports")
            cache = (Join-Path $runtimeHome "cache")
        }
    }
    $configPath = Get-QPRuntimeConfigPath
    $temporaryPath = "$configPath.tmp"
    $json = $payload | ConvertTo-Json -Depth 3
    [IO.File]::WriteAllText($temporaryPath, $json, (New-Object Text.UTF8Encoding($false)))
    Move-QPFileAtomically -TemporaryPath $temporaryPath -DestinationPath $configPath
}

function Save-QPSecureSecret([string]$Name, [Security.SecureString]$SecureValue) {
    if ($null -eq $SecureValue -or $SecureValue.Length -eq 0) {
        throw "Refusing to store an empty runtime secret: $Name."
    }
    $path = Get-QPSecretPath $Name
    $temporaryPath = "$path.tmp"
    ConvertFrom-SecureString -SecureString $SecureValue | Set-Content -Path $temporaryPath -Encoding ASCII -NoNewline
    Move-QPFileAtomically -TemporaryPath $temporaryPath -DestinationPath $path
}

function Save-QPSecret([string]$Name, [string]$Value) {
    if ([string]::IsNullOrWhiteSpace($Value)) {
        throw "Refusing to store an empty runtime secret: $Name."
    }
    $secure = ConvertTo-SecureString -String $Value -AsPlainText -Force
    Save-QPSecureSecret -Name $Name -SecureValue $secure
}

function Test-QPSecret([string]$Name) {
    $path = Get-QPSecretPath $Name
    if (-not (Test-Path $path -PathType Leaf)) {
        return $false
    }
    try {
        $null = ConvertTo-SecureString -String (Get-Content -Path $path -Raw) -ErrorAction Stop
    }
    catch {
        throw "Encrypted runtime secret '$Name' cannot be decrypted by the current Windows user. Refresh or restore that secret, then retry."
    }
    return $true
}

function Get-QPSecret([string]$Name) {
    if (-not (Test-QPSecret $Name)) {
        return $null
    }
    $secure = ConvertTo-SecureString -String (Get-Content -Path (Get-QPSecretPath $Name) -Raw) -ErrorAction Stop
    return (New-Object System.Net.NetworkCredential "", $secure).Password
}

function Remove-QPSecret([string]$Name) {
    $path = Get-QPSecretPath $Name
    if (Test-Path $path -PathType Leaf) {
        Remove-Item -Force -Path $path
    }
}

function Set-QPDeepSeekSkipMarker([bool]$Skipped) {
    $path = Get-QPDeepSeekSkipMarkerPath
    if ($Skipped) {
        [IO.File]::WriteAllText($path, "optional DeepSeek secret intentionally not configured", (New-Object Text.UTF8Encoding($false)))
    }
    elseif (Test-Path $path -PathType Leaf) {
        Remove-Item -Force -Path $path
    }
}

function New-QPRandomSecret {
    $bytes = New-Object byte[] 32
    $generator = [Security.Cryptography.RandomNumberGenerator]::Create()
    try {
        $generator.GetBytes($bytes)
    }
    finally {
        $generator.Dispose()
    }
    return ([Convert]::ToBase64String($bytes)).Replace("+", "A").Replace("/", "B").Replace("=", "C")
}

function Read-QPRuntimeConfig {
    Assert-QPRuntimeHomeOutsideRepository
    $configPath = Get-QPRuntimeConfigPath
    if (-not (Test-Path $configPath -PathType Leaf)) {
        throw "Runtime configuration not found: $configPath. Run bootstrap_windows_runtime_v1.ps1 first."
    }
    try {
        $config = Get-Content -Path $configPath -Raw | ConvertFrom-Json
    }
    catch {
        throw "Runtime configuration is invalid: $configPath. Rerun bootstrap_windows_runtime_v1.ps1 to repair it."
    }
    foreach ($name in @("schema_version", "platform", "timezone", "broker_provider", "reporting_enabled", "grafana_enabled", "deepseek_live_calls_enabled", "runtime_home", "grafana_url")) {
        if ($config.PSObject.Properties.Name -notcontains $name) {
            throw "Runtime configuration contract is incomplete. Rerun bootstrap_windows_runtime_v1.ps1 to repair safe settings."
        }
    }
    $expectedHome = [IO.Path]::GetFullPath((Get-QPRuntimeHome))
    $configuredHome = [IO.Path]::GetFullPath([string]$config.runtime_home)
    if ([int]$config.schema_version -ne 1 -or
        [string]$config.platform -ne "windows" -or
        [string]$config.timezone -ne "Asia/Shanghai" -or
        [string]$config.broker_provider -ne "none" -or
        -not ($config.reporting_enabled -is [bool]) -or
        -not [bool]$config.reporting_enabled -or
        -not ($config.grafana_enabled -is [bool]) -or
        -not [bool]$config.grafana_enabled -or
        -not ($config.deepseek_live_calls_enabled -is [bool]) -or
        [bool]$config.deepseek_live_calls_enabled -or
        [string]$config.grafana_url -ne "http://localhost:3000" -or
        -not $configuredHome.Equals($expectedHome, [StringComparison]::OrdinalIgnoreCase)) {
        throw "Runtime configuration contract is invalid. Rerun bootstrap_windows_runtime_v1.ps1 to repair safe settings."
    }
    return $config
}

function Set-QPProcessEnvironmentValue([string]$Name, [AllowNull()][string]$Value) {
    $path = "Env:$Name"
    if ($null -eq $Value -or $Value.Length -eq 0) {
        Remove-Item -Path $path -ErrorAction SilentlyContinue
    }
    else {
        Set-Item -Path $path -Value $Value | Out-Null
    }
}

function Import-QPRuntimeEnvironment {
    $config = Read-QPRuntimeConfig
    $postgresPassword = Get-QPSecret "postgres_password"
    $grafanaPassword = Get-QPSecret "grafana_password"
    if (-not $postgresPassword -or -not $grafanaPassword) {
        throw "Required local database or Grafana credential is missing. Rerun bootstrap_windows_runtime_v1.ps1."
    }
    Set-QPProcessEnvironmentValue "QUANTPILOT_RUNTIME_HOME" ([string]$config.runtime_home)
    Set-QPProcessEnvironmentValue "QUANTPILOT_REPOSITORY_ROOT" (Get-QPRepositoryRoot)
    Set-QPProcessEnvironmentValue "QUANTPILOT_RUNTIME_PLATFORM" ([string]$config.platform)
    Set-QPProcessEnvironmentValue "QUANTPILOT_TIMEZONE" ([string]$config.timezone)
    Set-QPProcessEnvironmentValue "QUANTPILOT_BROKER_PROVIDER" ([string]$config.broker_provider)
    Set-QPProcessEnvironmentValue "QUANTPILOT_REPORTING_ENABLED" ([string]$config.reporting_enabled)
    Set-QPProcessEnvironmentValue "QUANTPILOT_GRAFANA_ENABLED" ([string]$config.grafana_enabled)
    Set-QPProcessEnvironmentValue "QUANTPILOT_DEEPSEEK_LIVE_CALLS_ENABLED" ([string]$config.deepseek_live_calls_enabled)
    Set-QPProcessEnvironmentValue "QUANTPILOT_GRAFANA_URL" ([string]$config.grafana_url)
    Set-QPProcessEnvironmentValue "QUANTPILOT_CONTROL_CENTER_URL" ([string]$config.grafana_url)
    Set-QPProcessEnvironmentValue "POSTGRES_PASSWORD" $postgresPassword
    Set-QPProcessEnvironmentValue "GF_SECURITY_ADMIN_USER" "admin"
    Set-QPProcessEnvironmentValue "GF_SECURITY_ADMIN_PASSWORD" $grafanaPassword
    Set-QPProcessEnvironmentValue "TUSHARE_TOKEN" (Get-QPSecret "tushare_token")
    Set-QPProcessEnvironmentValue "DEEPSEEK_API_KEY" (Get-QPSecret "deepseek_api_key")
    Set-QPProcessEnvironmentValue "QUANTPILOT_POSTGRES_DSN" "postgresql://quantpilot:$postgresPassword@localhost:5432/quantpilot"
    return $config
}

function Push-QPRuntimeEnvironment {
    $names = @(
        "QUANTPILOT_RUNTIME_HOME", "QUANTPILOT_REPOSITORY_ROOT", "QUANTPILOT_RUNTIME_PLATFORM", "QUANTPILOT_TIMEZONE",
        "QUANTPILOT_BROKER_PROVIDER", "QUANTPILOT_REPORTING_ENABLED", "QUANTPILOT_GRAFANA_ENABLED",
        "QUANTPILOT_DEEPSEEK_LIVE_CALLS_ENABLED", "QUANTPILOT_GRAFANA_URL", "QUANTPILOT_CONTROL_CENTER_URL",
        "POSTGRES_PASSWORD", "GF_SECURITY_ADMIN_USER", "GF_SECURITY_ADMIN_PASSWORD", "TUSHARE_TOKEN",
        "DEEPSEEK_API_KEY", "QUANTPILOT_POSTGRES_DSN", "PYTHONPATH"
    )
    $snapshot = @{}
    foreach ($name in $names) {
        $item = Get-Item -Path "Env:$name" -ErrorAction SilentlyContinue
        if ($null -eq $item) {
            $snapshot[$name] = @{ Exists = $false; Value = $null }
        }
        else {
            $snapshot[$name] = @{ Exists = $true; Value = [string]$item.Value }
        }
    }
    try {
        $config = Import-QPRuntimeEnvironment
    }
    catch {
        Restore-QPRuntimeEnvironment -Snapshot $snapshot
        throw
    }
    return @{ Config = $config; Snapshot = $snapshot }
}

function Restore-QPRuntimeEnvironment([hashtable]$Snapshot) {
    foreach ($name in $Snapshot.Keys) {
        if ([bool]$Snapshot[$name].Exists) {
            Set-QPProcessEnvironmentValue -Name $name -Value ([string]$Snapshot[$name].Value)
        }
        else {
            Set-QPProcessEnvironmentValue -Name $name -Value $null
        }
    }
}

function Get-QPComposeLocation {
    $root = Get-QPRepositoryRoot
    $compose = Join-Path $root "infra\control_center\docker-compose.yml"
    return @{ File = $compose; Directory = (Split-Path -Parent $compose) }
}

function Invoke-QPCompose([string[]]$ComposeArguments) {
    $location = Get-QPComposeLocation
    & docker compose --project-name control_center --project-directory $location.Directory -f $location.File @ComposeArguments
    if ($LASTEXITCODE -ne 0) {
        throw "Docker Compose failed (exit $LASTEXITCODE)."
    }
}

function Test-QPPostgreSQLReady {
    $location = Get-QPComposeLocation
    & docker compose --project-name control_center --project-directory $location.Directory -f $location.File exec -T postgres pg_isready -U quantpilot -d quantpilot 1>$null 2>$null
    return ($LASTEXITCODE -eq 0)
}

function Test-QPGrafanaReady {
    try {
        $response = Invoke-WebRequest -UseBasicParsing -Uri "http://localhost:3000/api/health" -TimeoutSec 3
        return ($response.StatusCode -eq 200)
    }
    catch {
        return $false
    }
}

function Wait-QPControlCenter([int]$Attempts = 45) {
    for ($attempt = 1; $attempt -le $Attempts; $attempt++) {
        if ((Test-QPPostgreSQLReady) -and (Test-QPGrafanaReady)) {
            return
        }
        Start-Sleep -Seconds 2
    }
    throw "PostgreSQL and Grafana did not become ready within $($Attempts * 2) seconds. Run status_windows_runtime_v1.ps1 for diagnostics."
}
