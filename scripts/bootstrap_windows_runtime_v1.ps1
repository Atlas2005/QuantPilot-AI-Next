[CmdletBinding()]
param(
    [switch]$NonInteractive,
    [switch]$SkipDocker,
    [switch]$ValidateOnly,
    [switch]$ForceSecretRefresh
)
. (Join-Path $PSScriptRoot "windows_runtime_common_v1.ps1")

function Assert-QPPrerequisites {
    if ([Environment]::OSVersion.Platform -ne [PlatformID]::Win32NT) {
        throw "QuantPilot Runtime bootstrap must run on Windows."
    }
    if (-not [Environment]::Is64BitOperatingSystem) {
        throw "QuantPilot Windows runtime requires 64-bit Windows."
    }
    if ($PSVersionTable.PSVersion -lt [Version]"5.1") {
        throw "Windows PowerShell 5.1 or newer is required."
    }
    if (-not (Get-Command git -ErrorAction SilentlyContinue)) {
        throw "Git is required. Install Git for Windows, then rerun this script."
    }
    & git --version 1>$null
    if ($LASTEXITCODE -ne 0) {
        throw "Git was found but 'git --version' failed (exit $LASTEXITCODE)."
    }
    if (-not $SkipDocker) {
        if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
            throw "Docker Desktop (including Docker CLI and Compose) is required. Install and start Docker Desktop, then rerun this script."
        }
        & docker compose version 1>$null
        if ($LASTEXITCODE -ne 0) {
            throw "Docker Compose is required. Update and start Docker Desktop so 'docker compose version' succeeds, then rerun this script."
        }
    }
    if (Get-Command py -ErrorAction SilentlyContinue) {
        & py -3.12 -c "import struct, sys; assert sys.version_info[:2] == (3, 12) and struct.calcsize('P') * 8 == 64" 2>$null
        if ($LASTEXITCODE -eq 0) {
            return @{ Command = "py"; Arguments = @("-3.12") }
        }
    }
    if (Get-Command python -ErrorAction SilentlyContinue) {
        & python -c "import struct, sys; assert sys.version_info[:2] == (3, 12) and struct.calcsize('P') * 8 == 64" 2>$null
        if ($LASTEXITCODE -eq 0) {
            return @{ Command = "python"; Arguments = @() }
        }
    }
    throw "64-bit Python 3.12 is required. Install it from python.org, then rerun this script."
}

function Test-QPPersistentComposeVolume([string]$VolumeName) {
    if ($SkipDocker) {
        return $false
    }
    $volumeMatches = & docker volume ls --quiet --filter "label=com.docker.compose.project=control_center" --filter "label=com.docker.compose.volume=$VolumeName" 2>$null
    if ($LASTEXITCODE -ne 0) {
        throw "Docker could not inspect existing QuantPilot volumes (exit $LASTEXITCODE). Ensure Docker Desktop is running."
    }
    return -not [string]::IsNullOrWhiteSpace(($volumeMatches | Out-String))
}

function Initialize-QPLocalServiceSecret([string]$Name, [string]$VolumeName) {
    if (Test-QPSecret $Name) {
        return
    }
    if (Test-QPPersistentComposeVolume $VolumeName) {
        throw "Encrypted credential '$Name' is missing while persistent Docker data exists. Restore the runtime secrets backup; automatic credential replacement is unsafe."
    }
    Save-QPSecret -Name $Name -Value (New-QPRandomSecret)
}

function Initialize-QPApiSecrets {
    $refreshTushare = $ForceSecretRefresh -or -not (Test-QPSecret "tushare_token")
    if ($refreshTushare) {
        if ($NonInteractive) {
            if (-not $env:QUANTPILOT_BOOTSTRAP_TUSHARE_TOKEN) {
                throw "Noninteractive bootstrap requires QUANTPILOT_BOOTSTRAP_TUSHARE_TOKEN when the TuShare secret is missing or refreshed."
            }
            Save-QPSecret -Name "tushare_token" -Value $env:QUANTPILOT_BOOTSTRAP_TUSHARE_TOKEN
        }
        else {
            $secureTushare = Read-Host "TUSHARE_TOKEN (input hidden)" -AsSecureString
            Save-QPSecureSecret -Name "tushare_token" -SecureValue $secureTushare
        }
    }

    $deepSeekSkipped = Test-Path (Get-QPDeepSeekSkipMarkerPath) -PathType Leaf
    $refreshDeepSeek = $ForceSecretRefresh -or (-not (Test-QPSecret "deepseek_api_key") -and -not $deepSeekSkipped)
    if ($refreshDeepSeek) {
        if ($NonInteractive) {
            if ($env:QUANTPILOT_BOOTSTRAP_DEEPSEEK_API_KEY) {
                Save-QPSecret -Name "deepseek_api_key" -Value $env:QUANTPILOT_BOOTSTRAP_DEEPSEEK_API_KEY
                Set-QPDeepSeekSkipMarker $false
            }
            else {
                Remove-QPSecret "deepseek_api_key"
                Set-QPDeepSeekSkipMarker $true
            }
        }
        else {
            $secureDeepSeek = Read-Host "DEEPSEEK_API_KEY optional; Enter to skip (input hidden)" -AsSecureString
            if ($secureDeepSeek.Length -eq 0) {
                Remove-QPSecret "deepseek_api_key"
                Set-QPDeepSeekSkipMarker $true
            }
            else {
                Save-QPSecureSecret -Name "deepseek_api_key" -SecureValue $secureDeepSeek
                Set-QPDeepSeekSkipMarker $false
            }
        }
    }
}

$python = Assert-QPPrerequisites
if ($ValidateOnly) {
    Write-Host "Validation succeeded: required Windows, Git, Python, and requested Docker prerequisites are available. No runtime state or services were changed."
    exit 0
}
if ($NonInteractive -and -not $SkipDocker) {
    throw "NonInteractive mode requires SkipDocker so automation cannot modify persistent Docker state."
}

$originalRuntimeHome = Get-Item -Path "Env:QUANTPILOT_RUNTIME_HOME" -ErrorAction SilentlyContinue
$generatedTemporaryRuntimeHome = $null
if ($NonInteractive) {
    $tempRoot = [IO.Path]::GetFullPath([IO.Path]::GetTempPath())
    if ($env:QUANTPILOT_RUNTIME_HOME) {
        $candidate = [IO.Path]::GetFullPath($env:QUANTPILOT_RUNTIME_HOME)
        $tempSeparators = [char[]]@([IO.Path]::DirectorySeparatorChar, [IO.Path]::AltDirectorySeparatorChar)
        $tempPrefix = $tempRoot.TrimEnd($tempSeparators) + [IO.Path]::DirectorySeparatorChar
        if (-not $candidate.StartsWith($tempPrefix, [StringComparison]::OrdinalIgnoreCase)) {
            throw "NonInteractive QUANTPILOT_RUNTIME_HOME must be an isolated path under the system temporary directory."
        }
    }
    else {
        $generatedTemporaryRuntimeHome = Join-Path $tempRoot ("QuantPilot-runtime-" + [Guid]::NewGuid().ToString("N"))
        $env:QUANTPILOT_RUNTIME_HOME = $generatedTemporaryRuntimeHome
    }
}

$runtimeEnvironment = $null
try {
    $root = Get-QPRepositoryRoot
    Initialize-QPRuntimeDirectories
    $venv = Join-Path $root ".venv"
    if ($NonInteractive) {
        $venv = Join-Path (Get-QPRuntimeHome) "cache\venv"
    }
    $venvPython = Join-Path $venv "Scripts\python.exe"
    if (-not (Test-Path $venvPython -PathType Leaf)) {
        $pythonCommand = [string]$python.Command
        $interpreterArguments = @($python.Arguments) + @("-m", "venv", $venv)
        & $pythonCommand @interpreterArguments
        if ($LASTEXITCODE -ne 0) {
            throw "Failed to create the selected runtime virtual environment with 64-bit Python 3.12 (exit $LASTEXITCODE)."
        }
    }
    & $venvPython -c "import struct, sys; assert sys.version_info[:2] == (3, 12) and struct.calcsize('P') * 8 == 64" 2>$null
    if ($LASTEXITCODE -ne 0) {
        throw "The selected runtime virtual environment is not a working 64-bit Python 3.12 environment. Move it aside and rerun bootstrap."
    }
    & $venvPython -m pip install -e "$root[windows-runtime]"
    if ($LASTEXITCODE -ne 0) {
        throw "Failed to install the QuantPilot Windows runtime project extra (exit $LASTEXITCODE)."
    }

    Write-QPRuntimeConfig
    Initialize-QPLocalServiceSecret -Name "postgres_password" -VolumeName "pgdata"
    Initialize-QPLocalServiceSecret -Name "grafana_password" -VolumeName "grafana_data"
    Initialize-QPApiSecrets

    $runtimeEnvironment = Push-QPRuntimeEnvironment
    $env:PYTHONPATH = Join-Path $root "src"
    if (-not $SkipDocker) {
        Invoke-QPCompose -ComposeArguments @("up", "-d")
        Wait-QPControlCenter
        & $venvPython -c "from quantpilot_core.continuous_paper.store import PostgreSQLReportingStore; import os; PostgreSQLReportingStore(os.environ['QUANTPILOT_POSTGRES_DSN']).initialize()"
        if ($LASTEXITCODE -ne 0) {
            throw "PostgreSQL schema initialization failed (exit $LASTEXITCODE). Run status_windows_runtime_v1.ps1 for diagnostics."
        }
    }
    $doctorArguments = @((Join-Path $root "scripts\runtime_doctor_v1.py"), "--strict")
    if ($SkipDocker) {
        $doctorArguments += "--skip-services"
    }
    & $venvPython @doctorArguments
    if ($LASTEXITCODE -ne 0) {
        throw "Runtime Doctor found a missing required runtime component (exit $LASTEXITCODE)."
    }

    if ($NonInteractive) {
        Write-Host "Noninteractive runtime validation succeeded with isolated local state; Docker and provider requests were skipped."
    }
    else {
        Write-Host "QuantPilot Windows runtime is ready. Grafana: http://localhost:3000"
        Write-Host "Next: powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\status_windows_runtime_v1.ps1"
    }
}
finally {
    if ($null -ne $runtimeEnvironment) {
        Restore-QPRuntimeEnvironment -Snapshot $runtimeEnvironment.Snapshot
    }
    Remove-Item -Path "Env:QUANTPILOT_BOOTSTRAP_TUSHARE_TOKEN" -ErrorAction SilentlyContinue
    Remove-Item -Path "Env:QUANTPILOT_BOOTSTRAP_DEEPSEEK_API_KEY" -ErrorAction SilentlyContinue
    if ($generatedTemporaryRuntimeHome -and (Test-Path $generatedTemporaryRuntimeHome)) {
        Remove-Item -Recurse -Force -Path $generatedTemporaryRuntimeHome
    }
    if ($null -eq $originalRuntimeHome) {
        Remove-Item -Path "Env:QUANTPILOT_RUNTIME_HOME" -ErrorAction SilentlyContinue
    }
    else {
        $env:QUANTPILOT_RUNTIME_HOME = [string]$originalRuntimeHome.Value
    }
}
