param(
    [Parameter(Mandatory = $true)]
    [string]$Name
)

if ([string]::IsNullOrWhiteSpace($Name)) {
    Write-Error "Prototype environment name is required."
    exit 1
}

$repoRoot = Resolve-Path (Join-Path $PSScriptRoot "..\..")
$envRoot = Join-Path $repoRoot ".venv-prototypes"
$envPath = Join-Path $envRoot $Name

New-Item -ItemType Directory -Force -Path $envRoot | Out-Null

if (Test-Path $envPath) {
    Write-Host "Prototype environment already exists: $envPath"
} else {
    python -m venv $envPath
    Write-Host "Created prototype environment: $envPath"
}

Write-Host ""
Write-Host "Activate with:"
Write-Host ".\.venv-prototypes\$Name\Scripts\Activate.ps1"
Write-Host ""
Write-Host "Package installation must be separately approved."
Write-Host "This helper does not install packages, modify pyproject.toml, or run prototypes."
