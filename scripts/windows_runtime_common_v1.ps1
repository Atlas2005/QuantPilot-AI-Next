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

function Assert-QPBridgeRootOutsideRepository([string]$BridgeRoot) {
    if ([string]::IsNullOrWhiteSpace($BridgeRoot)) {
        throw "QMT built-in bridge root must be configured."
    }
    $trimCharacters = [char[]]@("\", "/")
    $repository = [IO.Path]::GetFullPath((Get-QPRepositoryRoot)).TrimEnd($trimCharacters)
    $bridgeRootPath = [IO.Path]::GetFullPath($BridgeRoot).TrimEnd($trimCharacters)
    $repositoryPrefix = $repository + [IO.Path]::DirectorySeparatorChar
    if ($bridgeRootPath.Equals($repository, [StringComparison]::OrdinalIgnoreCase) -or
        $bridgeRootPath.StartsWith($repositoryPrefix, [StringComparison]::OrdinalIgnoreCase)) {
        throw "QMT built-in bridge root must be outside the Git repository."
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
    if ([string]::IsNullOrWhiteSpace($TemporaryPath) -or [string]::IsNullOrWhiteSpace($DestinationPath)) {
        throw "Atomic runtime file replacement requires non-empty temporary and destination paths."
    }
    try {
        $fullTemporaryPath = [IO.Path]::GetFullPath($TemporaryPath)
        $fullDestinationPath = [IO.Path]::GetFullPath($DestinationPath)
    }
    catch {
        throw "Atomic runtime file replacement received an invalid path: $($_.Exception.Message)"
    }
    if (-not (Test-Path $fullTemporaryPath -PathType Leaf)) {
        throw "Atomic runtime file replacement temporary source does not exist."
    }
    if (-not [string]::Equals([IO.Path]::GetPathRoot($fullTemporaryPath), [IO.Path]::GetPathRoot($fullDestinationPath), [StringComparison]::OrdinalIgnoreCase)) {
        throw "Atomic runtime file replacement requires temporary and destination paths on the same volume."
    }
    $destinationDirectory = Split-Path -Parent $fullDestinationPath
    if (-not (Test-Path $destinationDirectory -PathType Container)) {
        throw "Atomic runtime file replacement destination directory does not exist."
    }
    if (Test-Path $fullDestinationPath -PathType Container) {
        throw "Atomic runtime file replacement destination must be a file."
    }
    if (Test-Path $fullDestinationPath -PathType Leaf) {
        $backupFileName = "." + [IO.Path]::GetFileName($fullDestinationPath) + "." + [Guid]::NewGuid().ToString("N") + ".bak"
        $backupPath = Join-Path $destinationDirectory $backupFileName
        try {
            [IO.File]::Replace($fullTemporaryPath, $fullDestinationPath, $backupPath)
        }
        catch {
            throw "Atomic runtime file replacement failed; the existing destination was preserved. $($_.Exception.Message)"
        }
        try {
            if (Test-Path $backupPath -PathType Leaf) {
                Remove-Item -LiteralPath $backupPath -Force -ErrorAction Stop
            }
        }
        catch {
            throw "Atomic runtime file replacement succeeded, but backup cleanup failed: $backupPath. $($_.Exception.Message)"
        }
    }
    else {
        [IO.File]::Move($fullTemporaryPath, $fullDestinationPath)
    }
}

function New-QPDefaultRuntimeConfigPayload {
    $runtimeHome = [IO.Path]::GetFullPath((Get-QPRuntimeHome))
    return [pscustomobject][ordered]@{
        schema_version = 2
        platform = "windows"
        timezone = "Asia/Shanghai"
        broker_provider = "none"
        qmt_builtin_bridge = [pscustomobject][ordered]@{
            bridge_root = (Join-Path $runtimeHome "qmt_builtin_bridge")
            max_snapshot_age_seconds = 120.0
            expected_account_type = "STOCK"
            expected_redacted_account_id = $null
            polling_interval_seconds = 5.0
            heartbeat_interval_seconds = 30.0
            provider_mode = "simulation_signal"
        }
        reporting_enabled = $true
        grafana_enabled = $true
        deepseek_live_calls_enabled = $false
        runtime_home = $runtimeHome
        postgres_dsn_env_var = "QUANTPILOT_POSTGRES_DSN"
        grafana_url = "http://localhost:3000"
        paths = [pscustomobject][ordered]@{
            config = (Join-Path $runtimeHome "config")
            secrets = (Join-Path $runtimeHome "secrets")
            logs = (Join-Path $runtimeHome "logs")
            state = (Join-Path $runtimeHome "state")
            reports = (Join-Path $runtimeHome "reports")
            cache = (Join-Path $runtimeHome "cache")
        }
    }
}

function Read-QPRuntimeConfigDocument([switch]$AllowMissing) {
    Assert-QPRuntimeHomeOutsideRepository
    $configPath = Get-QPRuntimeConfigPath
    if (-not (Test-Path $configPath -PathType Leaf)) {
        if ($AllowMissing -and -not (Test-Path $configPath)) {
            return $null
        }
        throw "Runtime configuration not found or is not a file: $configPath."
    }
    try {
        $document = Get-Content -LiteralPath $configPath -Raw -ErrorAction Stop | ConvertFrom-Json -ErrorAction Stop
        if ($null -eq $document) {
            throw "Runtime configuration JSON must contain an object."
        }
        return $document
    }
    catch {
        throw "Runtime configuration is malformed and was not changed: $configPath."
    }
}

function ConvertTo-QPPositiveFiniteNumber([object]$Value, [string]$Name) {
    if ($null -eq $Value -or $Value -is [bool] -or $Value -is [string]) {
        throw "Runtime configuration field '$Name' must be a positive finite number."
    }
    try {
        $number = [Convert]::ToDouble($Value, [Globalization.CultureInfo]::InvariantCulture)
    }
    catch {
        throw "Runtime configuration field '$Name' must be a positive finite number."
    }
    if ([double]::IsNaN($number) -or [double]::IsInfinity($number) -or $number -le 0) {
        throw "Runtime configuration field '$Name' must be a positive finite number."
    }
    return $number
}

function Assert-QPRuntimeConfigBase([object]$Config, [int]$SchemaVersion) {
    if ($null -eq $Config) {
        throw "Runtime configuration is empty."
    }
    foreach ($name in @("schema_version", "platform", "timezone", "broker_provider", "reporting_enabled", "grafana_enabled", "deepseek_live_calls_enabled", "runtime_home", "postgres_dsn_env_var", "grafana_url", "paths")) {
        if ($Config.PSObject.Properties.Name -notcontains $name) {
            throw "Runtime configuration contract is incomplete: missing $name."
        }
    }
    if (($Config.schema_version -isnot [int]) -and ($Config.schema_version -isnot [long])) {
        throw "Runtime configuration schema_version must be an integer."
    }
    if ([int]$Config.schema_version -ne $SchemaVersion) {
        throw "Runtime configuration schema version is unsupported."
    }
    $expectedHome = [IO.Path]::GetFullPath((Get-QPRuntimeHome))
    try {
        $configuredHome = [IO.Path]::GetFullPath([string]$Config.runtime_home)
    }
    catch {
        throw "Runtime configuration runtime_home is invalid."
    }
    if ([string]$Config.platform -cne "windows" -or
        [string]$Config.timezone -cne "Asia/Shanghai" -or
        -not ($Config.reporting_enabled -is [bool]) -or
        -not ($Config.grafana_enabled -is [bool]) -or
        -not ($Config.deepseek_live_calls_enabled -is [bool]) -or
        [bool]$Config.deepseek_live_calls_enabled -or
        [string]$Config.postgres_dsn_env_var -cne "QUANTPILOT_POSTGRES_DSN" -or
        [string]$Config.grafana_url -cne "http://localhost:3000" -or
        -not $configuredHome.Equals($expectedHome, [StringComparison]::OrdinalIgnoreCase)) {
        throw "Runtime configuration contains unsafe or incompatible base settings."
    }
    if ($SchemaVersion -eq 1 -and [string]$Config.broker_provider -cne "none") {
        throw "Schema-v1 runtime configuration must use provider=none before migration."
    }
    if ($SchemaVersion -eq 2 -and @("none", "qmt_builtin_bridge") -notcontains [string]$Config.broker_provider) {
        throw "Runtime configuration broker provider is unsupported."
    }
    if ($null -eq $Config.paths) {
        throw "Runtime configuration paths are missing."
    }
    foreach ($name in @("config", "secrets", "logs", "state", "reports", "cache")) {
        if ($Config.paths.PSObject.Properties.Name -notcontains $name) {
            throw "Runtime configuration paths are incomplete."
        }
        $expectedPath = [IO.Path]::GetFullPath((Join-Path $expectedHome $name))
        try {
            $configuredPath = [IO.Path]::GetFullPath([string]$Config.paths.$name)
        }
        catch {
            throw "Runtime configuration path '$name' is invalid."
        }
        if (-not $configuredPath.Equals($expectedPath, [StringComparison]::OrdinalIgnoreCase)) {
            throw "Runtime configuration path '$name' does not match runtime_home."
        }
    }
}

function Assert-QPRuntimeConfigV2([object]$Config) {
    Assert-QPRuntimeConfigBase -Config $Config -SchemaVersion 2
    if ($Config.PSObject.Properties.Name -notcontains "qmt_builtin_bridge" -or $null -eq $Config.qmt_builtin_bridge) {
        throw "QMT built-in bridge configuration is missing."
    }
    $bridgeConfig = $Config.qmt_builtin_bridge
    foreach ($name in @("bridge_root", "max_snapshot_age_seconds", "expected_account_type", "expected_redacted_account_id", "polling_interval_seconds", "heartbeat_interval_seconds", "provider_mode")) {
        if ($bridgeConfig.PSObject.Properties.Name -notcontains $name) {
            throw "QMT built-in bridge configuration is incomplete: missing $name."
        }
    }
    $configuredBridgeRoot = [string]$bridgeConfig.bridge_root
    Assert-QPBridgeRootOutsideRepository -BridgeRoot $configuredBridgeRoot
    $maximumSnapshotAge = ConvertTo-QPPositiveFiniteNumber -Value $bridgeConfig.max_snapshot_age_seconds -Name "max_snapshot_age_seconds"
    $pollingInterval = ConvertTo-QPPositiveFiniteNumber -Value $bridgeConfig.polling_interval_seconds -Name "polling_interval_seconds"
    $heartbeatInterval = ConvertTo-QPPositiveFiniteNumber -Value $bridgeConfig.heartbeat_interval_seconds -Name "heartbeat_interval_seconds"
    if ($heartbeatInterval -lt $pollingInterval) {
        throw "QMT heartbeat interval must be at least the polling interval."
    }
    if ($null -ne $bridgeConfig.expected_account_type) {
        if ($bridgeConfig.expected_account_type -isnot [string] -or
            [string]::IsNullOrWhiteSpace([string]$bridgeConfig.expected_account_type) -or
            [string]$bridgeConfig.expected_account_type -cne ([string]$bridgeConfig.expected_account_type).Trim().ToUpperInvariant() -or
            ([string]$bridgeConfig.expected_account_type).Length -gt 32) {
            throw "Expected QMT account type must be a short uppercase value or null."
        }
    }
    if ($null -ne $bridgeConfig.expected_redacted_account_id -and
        [string]$bridgeConfig.expected_redacted_account_id -cnotmatch "^qmtacct-v1-[0-9a-f]{24}$") {
        throw "Expected QMT account binding must use the redacted qmtacct-v1 format."
    }
    if ([string]$bridgeConfig.provider_mode -cne "simulation_signal") {
        throw "QMT provider mode must be simulation_signal."
    }
}

function ConvertTo-QPRuntimeConfigV2([object]$Config) {
    $schemaVersion = $Config.schema_version
    if (($schemaVersion -isnot [int]) -and ($schemaVersion -isnot [long])) {
        throw "Runtime configuration schema_version must be an integer."
    }
    if ([int]$schemaVersion -eq 1) {
        Assert-QPRuntimeConfigBase -Config $Config -SchemaVersion 1
        $migrated = New-QPDefaultRuntimeConfigPayload
        $migrated.runtime_home = [string]$Config.runtime_home
        $migrated.reporting_enabled = [bool]$Config.reporting_enabled
        $migrated.grafana_enabled = [bool]$Config.grafana_enabled
        foreach ($name in @("config", "secrets", "logs", "state", "reports", "cache")) {
            $migrated.paths.$name = [string]$Config.paths.$name
        }
        return $migrated
    }
    if ([int]$schemaVersion -ne 2) {
        throw "Runtime configuration schema version is unsupported."
    }
    Assert-QPRuntimeConfigV2 -Config $Config
    $copy = New-QPDefaultRuntimeConfigPayload
    $copy.runtime_home = [string]$Config.runtime_home
    $copy.broker_provider = [string]$Config.broker_provider
    $copy.reporting_enabled = [bool]$Config.reporting_enabled
    $copy.grafana_enabled = [bool]$Config.grafana_enabled
    $copy.qmt_builtin_bridge.bridge_root = [string]$Config.qmt_builtin_bridge.bridge_root
    $copy.qmt_builtin_bridge.max_snapshot_age_seconds = [double]$Config.qmt_builtin_bridge.max_snapshot_age_seconds
    $copy.qmt_builtin_bridge.expected_account_type = $Config.qmt_builtin_bridge.expected_account_type
    $copy.qmt_builtin_bridge.expected_redacted_account_id = $Config.qmt_builtin_bridge.expected_redacted_account_id
    $copy.qmt_builtin_bridge.polling_interval_seconds = [double]$Config.qmt_builtin_bridge.polling_interval_seconds
    $copy.qmt_builtin_bridge.heartbeat_interval_seconds = [double]$Config.qmt_builtin_bridge.heartbeat_interval_seconds
    $copy.qmt_builtin_bridge.provider_mode = [string]$Config.qmt_builtin_bridge.provider_mode
    foreach ($name in @("config", "secrets", "logs", "state", "reports", "cache")) {
        $copy.paths.$name = [string]$Config.paths.$name
    }
    return $copy
}

function Resolve-QPRuntimeConfigPayload([hashtable]$Overrides = @{}) {
    $existingConfig = Read-QPRuntimeConfigDocument -AllowMissing
    if ($null -eq $existingConfig) {
        $candidate = New-QPDefaultRuntimeConfigPayload
    }
    else {
        $candidate = ConvertTo-QPRuntimeConfigV2 -Config $existingConfig
    }
    if ($Overrides.ContainsKey("BrokerProvider")) {
        $candidate.broker_provider = [string]$Overrides["BrokerProvider"]
    }
    if ($Overrides.ContainsKey("QmtBridgeRoot")) {
        if ([string]::IsNullOrWhiteSpace([string]$Overrides["QmtBridgeRoot"])) {
            throw "An explicitly supplied QMT bridge root cannot be empty."
        }
        $candidate.qmt_builtin_bridge.bridge_root = [IO.Path]::GetFullPath([string]$Overrides["QmtBridgeRoot"])
    }
    if ($Overrides.ContainsKey("QmtMaxSnapshotAgeSeconds")) {
        $candidate.qmt_builtin_bridge.max_snapshot_age_seconds = [double]$Overrides["QmtMaxSnapshotAgeSeconds"]
    }
    if ($Overrides.ContainsKey("QmtExpectedAccountType")) {
        $accountType = [string]$Overrides["QmtExpectedAccountType"]
        $candidate.qmt_builtin_bridge.expected_account_type = if ([string]::IsNullOrWhiteSpace($accountType)) { $null } else { $accountType.Trim().ToUpperInvariant() }
    }
    if ($Overrides.ContainsKey("QmtExpectedRedactedAccountId")) {
        $accountBinding = [string]$Overrides["QmtExpectedRedactedAccountId"]
        $candidate.qmt_builtin_bridge.expected_redacted_account_id = if ([string]::IsNullOrWhiteSpace($accountBinding)) { $null } else { $accountBinding.Trim() }
    }
    if ($Overrides.ContainsKey("QmtPollingIntervalSeconds")) {
        $candidate.qmt_builtin_bridge.polling_interval_seconds = [double]$Overrides["QmtPollingIntervalSeconds"]
    }
    if ($Overrides.ContainsKey("QmtHeartbeatIntervalSeconds")) {
        $candidate.qmt_builtin_bridge.heartbeat_interval_seconds = [double]$Overrides["QmtHeartbeatIntervalSeconds"]
    }
    if ($Overrides.ContainsKey("QmtProviderMode")) {
        $candidate.qmt_builtin_bridge.provider_mode = [string]$Overrides["QmtProviderMode"]
    }
    Assert-QPRuntimeConfigV2 -Config $candidate
    return $candidate
}

function Write-QPRuntimeConfig(
    [ValidateSet("none", "qmt_builtin_bridge")][string]$BrokerProvider = "none",
    [AllowNull()][string]$QmtBridgeRoot = $null,
    [double]$QmtMaxSnapshotAgeSeconds = 120,
    [AllowNull()][string]$QmtExpectedAccountType = "STOCK",
    [AllowNull()][string]$QmtExpectedRedactedAccountId = $null,
    [double]$QmtPollingIntervalSeconds = 5,
    [double]$QmtHeartbeatIntervalSeconds = 30,
    [ValidateSet("simulation_signal")][string]$QmtProviderMode = "simulation_signal"
) {
    $overrides = @{}
    foreach ($name in $PSBoundParameters.Keys) {
        $overrides[$name] = $PSBoundParameters[$name]
    }
    $payload = Resolve-QPRuntimeConfigPayload -Overrides $overrides
    Initialize-QPRuntimeDirectories
    $configPath = Get-QPRuntimeConfigPath
    $temporaryPath = "$configPath.tmp"
    $json = $payload | ConvertTo-Json -Depth 4
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

function Get-QPAccountBindingKeyPath([string]$BridgeRoot) {
    Assert-QPBridgeRootOutsideRepository -BridgeRoot $BridgeRoot
    return (Join-Path ([IO.Path]::GetFullPath($BridgeRoot)) "state\account_binding_key_v1.hex")
}

function Assert-QPAccountBindingKeyState([string]$BridgeRoot, [switch]$AllowMissing) {
    $keyPath = Get-QPAccountBindingKeyPath -BridgeRoot $BridgeRoot
    if (-not (Test-Path $keyPath -PathType Leaf)) {
        if ($AllowMissing -and -not (Test-Path $keyPath)) {
            return
        }
        throw "QMT account-binding key is missing or is not a file."
    }
    try {
        $keyText = [IO.File]::ReadAllText($keyPath)
    }
    catch {
        throw "QMT account-binding key cannot be read by the current Windows user."
    }
    if ($keyText -cnotmatch "^[0-9a-f]{64}$") {
        throw "QMT account-binding key must contain exactly 32 bytes encoded as 64 lowercase hexadecimal characters."
    }
}

function Protect-QPAccountBindingKeyForCurrentUser([string]$KeyPath) {
    $currentWindowsIdentity = [Security.Principal.WindowsIdentity]::GetCurrent()
    if ($null -eq $currentWindowsIdentity -or [string]::IsNullOrWhiteSpace($currentWindowsIdentity.Name)) {
        throw "Current Windows identity is unavailable for QMT account-binding key protection."
    }
    $currentAccountName = $currentWindowsIdentity.Name
    $currentWindowsIdentity.Dispose()
    $currentAccount = New-Object -TypeName Security.Principal.NTAccount -ArgumentList @($currentAccountName)
    $fileSecurity = Get-Acl -LiteralPath $KeyPath -ErrorAction Stop
    $fileSecurity.SetAccessRuleProtection($true, $false)
    foreach ($existingAccessRule in @($fileSecurity.Access)) {
        $fileSecurity.RemoveAccessRuleAll($existingAccessRule)
    }
    $fileSecurity.SetOwner($currentAccount)
    $accessRule = New-Object -TypeName Security.AccessControl.FileSystemAccessRule -ArgumentList @(
        $currentAccountName,
        [Security.AccessControl.FileSystemRights]::FullControl,
        [Security.AccessControl.AccessControlType]::Allow
    )
    $fileSecurity.SetAccessRule($accessRule)
    Set-Acl -LiteralPath $KeyPath -AclObject $fileSecurity -ErrorAction Stop | Out-Null
}

function Initialize-QPAccountBindingKey([string]$BridgeRoot) {
    $keyPath = Get-QPAccountBindingKeyPath -BridgeRoot $BridgeRoot
    if (Test-Path $keyPath -PathType Leaf) {
        Assert-QPAccountBindingKeyState -BridgeRoot $BridgeRoot
        Protect-QPAccountBindingKeyForCurrentUser -KeyPath $keyPath
        return
    }
    if (Test-Path $keyPath) {
        throw "QMT account-binding key path exists but is not a file."
    }
    $stateDirectory = Split-Path -Parent $keyPath
    New-Item -ItemType Directory -Force -Path $stateDirectory | Out-Null
    $randomBytes = New-Object byte[] 32
    $generator = [Security.Cryptography.RandomNumberGenerator]::Create()
    try {
        $generator.GetBytes($randomBytes)
    }
    finally {
        $generator.Dispose()
    }
    $keyText = -join ($randomBytes | ForEach-Object { $_.ToString("x2") })
    [Array]::Clear($randomBytes, 0, $randomBytes.Length)
    $temporaryPath = Join-Path $stateDirectory (".account_binding_key_v1." + [Guid]::NewGuid().ToString("N") + ".tmp")
    try {
        [IO.File]::WriteAllText($temporaryPath, $keyText, (New-Object Text.UTF8Encoding($false)))
        Protect-QPAccountBindingKeyForCurrentUser -KeyPath $temporaryPath
        [IO.File]::Move($temporaryPath, $keyPath)
    }
    catch [IO.IOException] {
        if (Test-Path $temporaryPath -PathType Leaf) {
            Remove-Item -LiteralPath $temporaryPath -Force -ErrorAction SilentlyContinue
        }
        if (-not (Test-Path $keyPath -PathType Leaf)) {
            throw
        }
    }
    finally {
        $keyText = $null
        if (Test-Path $temporaryPath -PathType Leaf) {
            Remove-Item -LiteralPath $temporaryPath -Force -ErrorAction SilentlyContinue
        }
    }
    Assert-QPAccountBindingKeyState -BridgeRoot $BridgeRoot
    Protect-QPAccountBindingKeyForCurrentUser -KeyPath $keyPath
}

function Read-QPRuntimeConfig {
    $config = Read-QPRuntimeConfigDocument
    if ([int]$config.schema_version -ne 2) {
        throw "Runtime configuration must be migrated to schema version 2 by bootstrap_windows_runtime_v1.ps1."
    }
    Assert-QPRuntimeConfigV2 -Config $config
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
    Set-QPProcessEnvironmentValue "QUANTPILOT_QMT_BRIDGE_ROOT" ([string]$config.qmt_builtin_bridge.bridge_root)
    Set-QPProcessEnvironmentValue "QUANTPILOT_QMT_MAX_SNAPSHOT_AGE_SECONDS" ([string]$config.qmt_builtin_bridge.max_snapshot_age_seconds)
    Set-QPProcessEnvironmentValue "QUANTPILOT_QMT_EXPECTED_ACCOUNT_TYPE" ([string]$config.qmt_builtin_bridge.expected_account_type)
    Set-QPProcessEnvironmentValue "QUANTPILOT_QMT_EXPECTED_REDACTED_ACCOUNT_ID" ([string]$config.qmt_builtin_bridge.expected_redacted_account_id)
    Set-QPProcessEnvironmentValue "QUANTPILOT_QMT_POLL_INTERVAL_SECONDS" ([string]$config.qmt_builtin_bridge.polling_interval_seconds)
    Set-QPProcessEnvironmentValue "QUANTPILOT_QMT_HEARTBEAT_INTERVAL_SECONDS" ([string]$config.qmt_builtin_bridge.heartbeat_interval_seconds)
    Set-QPProcessEnvironmentValue "QUANTPILOT_QMT_PROVIDER_MODE" ([string]$config.qmt_builtin_bridge.provider_mode)
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
        "QUANTPILOT_QMT_BRIDGE_ROOT", "QUANTPILOT_QMT_MAX_SNAPSHOT_AGE_SECONDS", "QUANTPILOT_QMT_EXPECTED_ACCOUNT_TYPE",
        "QUANTPILOT_QMT_EXPECTED_REDACTED_ACCOUNT_ID", "QUANTPILOT_QMT_POLL_INTERVAL_SECONDS",
        "QUANTPILOT_QMT_HEARTBEAT_INTERVAL_SECONDS", "QUANTPILOT_QMT_PROVIDER_MODE",
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
