[CmdletBinding()]
param(
    [string]$SystemDir = ""
)
Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$root = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot "..\.."))
$python = Join-Path $root ".venv\Scripts\python.exe"
if (-not (Test-Path $python -PathType Leaf)) {
    throw "QuantPilot Python environment is missing: $python"
}
if (-not $SystemDir) {
    $SystemDir = Join-Path $env:TEMP ("qp-single-instance-smoke-" + [guid]::NewGuid().ToString("N"))
}
New-Item -ItemType Directory -Path $SystemDir -Force | Out-Null
$lockFile = Join-Path $SystemDir ".qp_intraday.lock"
$helperA = Join-Path $SystemDir "smoke_owner_a.py"
$helperB = Join-Path $SystemDir "smoke_owner_b.py"
$outA = Join-Path $SystemDir "owner_a.out"
$errA = Join-Path $SystemDir "owner_a.err"

$codeA = @"
import sys, time
sys.path.insert(0, r'$root\src')
from quantpilot_core.manual_trading_system import SystemDirLock
lock = SystemDirLock(r'$SystemDir')
lock.acquire()
print('ACQUIRED', flush=True)
time.sleep(20)
lock.release()
print('RELEASED', flush=True)
"@

$codeB = @"
import sys
sys.path.insert(0, r'$root\src')
from quantpilot_core.manual_trading_system import RuntimeLockError, SystemDirLock
try:
    SystemDirLock(r'$SystemDir').acquire()
except RuntimeLockError as exc:
    print('REJECTED:' + type(exc).__name__, flush=True)
    sys.exit(3)
except Exception as exc:
    print('REJECTED:' + type(exc).__name__, flush=True)
    sys.exit(4)
print('UNEXPECTED_ACQUIRE', flush=True)
sys.exit(2)
"@

Set-Content -LiteralPath $helperA -Value $codeA -Encoding ASCII
Set-Content -LiteralPath $helperB -Value $codeB -Encoding ASCII

$procA = $null
try {
    $procA = Start-Process -FilePath $python -ArgumentList $helperA `
        -PassThru -RedirectStandardOutput $outA -RedirectStandardError $errA

    $acquired = $false
    $deadline = (Get-Date).AddSeconds(30)
    while ((Get-Date) -lt $deadline) {
        if ($procA.HasExited) {
            $stderr = if (Test-Path $errA) { [IO.File]::ReadAllText($errA) } else { "" }
            throw "owner process A exited before acquiring the lock: $stderr"
        }
        if (Test-Path $outA) {
            $text = [IO.File]::ReadAllText($outA)
            if ($text.Contains("ACQUIRED")) {
                $acquired = $true
                break
            }
        }
        Start-Sleep -Milliseconds 200
    }
    if (-not $acquired) {
        throw "owner process A never reported ACQUIRED"
    }

    $outputB = & $python $helperB 2>&1 | Out-String
    $exitB = $LASTEXITCODE
    if ($exitB -ne 3 -or -not $outputB.Contains("REJECTED:RuntimeLockError")) {
        throw "process B did not fail with RuntimeLockError (exit=$exitB output=$outputB)"
    }

    if ($procA.HasExited) {
        throw "owner process A was terminated while holding the lock"
    }

    Wait-Process -Id $procA.Id -Timeout 40
    $outputA = if (Test-Path $outA) { [IO.File]::ReadAllText($outA) } else { "" }
    if (-not $outputA.Contains("RELEASED")) {
        throw "owner process A did not release the lock normally"
    }
    if (Test-Path $lockFile) {
        throw "lock file still exists after owner A exited: $lockFile"
    }

    Write-Host "[PASS] single-instance smoke:"
    Write-Host "  A acquired the lock and stayed alive (not terminated)."
    Write-Host "  B failed fast with RuntimeLockError (exit=3)."
    Write-Host "  A released the lock on normal exit; lock file removed."
}
finally {
    if ($procA -ne $null -and -not $procA.HasExited) {
        Stop-Process -Id $procA.Id -Force -ErrorAction SilentlyContinue
    }
}
