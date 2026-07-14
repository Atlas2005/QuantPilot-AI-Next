from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from quantpilot_core.runtime_node import (
    BrokerProvider,
    QmtBuiltinBridgeConfig,
    QmtProviderMode,
    RuntimeConfig,
    RuntimePaths,
    ServiceReadiness,
    collect_runtime_diagnostics,
)
from quantpilot_core.runtime_node.doctor import DoctorCheck, diagnostics_payload
from scripts.runtime_doctor_v1 import diagnostics_payload as runtime_diagnostics_payload
from scripts.runtime_doctor_v1 import main

RESERVED_POWERSHELL_AUTOMATIC_VARIABLES = {
    "home",
    "pid",
    "host",
    "error",
    "input",
    "args",
    "matches",
    "myinvocation",
    "psscriptroot",
    "lastexitcode",
    "pwd",
    "psversiontable",
}


def _create_runtime_layout(home: Path) -> None:
    for name in ("config", "secrets", "logs", "state", "reports", "cache"):
        (home / name).mkdir(parents=True, exist_ok=True)


def test_runtime_config_supports_only_none_and_qmt_builtin_bridge(monkeypatch) -> None:
    monkeypatch.delenv("QUANTPILOT_BROKER_PROVIDER", raising=False)
    assert RuntimeConfig.from_environment().broker_provider is BrokerProvider.NONE

    monkeypatch.setenv("QUANTPILOT_BROKER_PROVIDER", "qmt_builtin_bridge")
    assert RuntimeConfig.from_environment().broker_provider is BrokerProvider.QMT_BUILTIN_BRIDGE
    assert {provider.value for provider in BrokerProvider} == {"none", "qmt_builtin_bridge"}

    monkeypatch.setenv("QUANTPILOT_BROKER_PROVIDER", "qmt")
    with pytest.raises(ValueError):
        RuntimeConfig.from_environment()


def test_runtime_diagnostics_require_no_broker_and_skip_bounded_service_probes(monkeypatch, tmp_path: Path) -> None:
    runtime = tmp_path / "runtime"
    _create_runtime_layout(runtime)
    monkeypatch.setenv("QUANTPILOT_POSTGRES_DSN", "postgresql://configured")
    monkeypatch.setenv("QUANTPILOT_GRAFANA_URL", "http://localhost:3000")
    monkeypatch.setenv("TUSHARE_TOKEN", "synthetic-placeholder")
    config = RuntimeConfig(
        platform="windows",
        timezone="Asia/Shanghai",
        broker_provider=BrokerProvider.QMT_BUILTIN_BRIDGE,
        qmt_builtin_bridge=QmtBuiltinBridgeConfig(bridge_root=tmp_path / "missing-bridge"),
        runtime_home=runtime,
        services=ServiceReadiness(postgres_configured=True, grafana_configured=True),
    )
    checks = {check.name: check for check in collect_runtime_diagnostics(config, probe_services=False)}
    delegated = {check.name: check for check in collect_runtime_diagnostics(config, probe_services=True)}

    assert checks["postgresql"].status == "CONFIGURED"
    assert checks["grafana"].status == "CONFIGURED"
    assert checks["docker"].status == "SKIPPED"
    assert delegated["postgresql"].status == "NOT_CHECKED"
    assert delegated["grafana"].status == "NOT_CHECKED"
    assert checks["broker"].status == "NOT_READY"
    assert checks["broker"].required is True
    assert "bridge directory is unavailable" in checks["broker"].detail


def test_xtquant_is_not_probed_and_deepseek_absence_is_explicitly_optional(monkeypatch, tmp_path: Path) -> None:
    runtime = tmp_path / "runtime"
    _create_runtime_layout(runtime)
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    config = RuntimeConfig(platform="windows", runtime_home=runtime)
    checks = {check.name: check for check in collect_runtime_diagnostics(config, probe_services=False)}
    runtime_checks = {check["name"]: check for check in runtime_diagnostics_payload(probe_services=False)["checks"]}

    assert "package.xtquant" not in checks
    assert runtime_checks["deepseek_api_key"]["status"] == "OPTIONAL_NOT_CONFIGURED"
    assert runtime_checks["deepseek_api_key"]["required"] is False
    assert checks["broker"].status == "EXPECTED"


def test_required_diagnostic_aggregation_uses_explicit_success_states(monkeypatch) -> None:
    import quantpilot_core.runtime_node.doctor as doctor_module

    monkeypatch.setattr(doctor_module, "collect_runtime_diagnostics", lambda *_args, **_kwargs: (DoctorCheck("required", "ERROR", "failed", True),))
    assert diagnostics_payload(probe_services=False)["ok"] is False

    monkeypatch.setattr(doctor_module, "collect_runtime_diagnostics", lambda *_args, **_kwargs: (DoctorCheck("required", "CONFIGURED", "probe skipped", True), DoctorCheck("optional", "NOT_READY", "optional", False)))
    assert diagnostics_payload(probe_services=False)["ok"] is True


def test_runtime_doctor_json_output_is_ci_friendly(capsys) -> None:
    assert main(["--format", "json", "--skip-services"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert isinstance(payload["ok"], bool)
    assert {check["name"] for check in payload["checks"]} >= {"python", "project_import", "broker", "runtime_layout"}
    assert all(isinstance(check["required"], bool) for check in payload["checks"])


def test_runtime_paths_and_persisted_configuration_never_contain_raw_secrets(tmp_path: Path) -> None:
    repo = tmp_path / "repository"
    runtime = tmp_path / "localappdata" / "QuantPilot" / "runtime"
    config = RuntimeConfig(platform="windows", runtime_home=runtime)
    paths = RuntimePaths.under(runtime)
    serialized = json.dumps(config.as_dict())

    assert paths.secrets.is_relative_to(runtime)
    assert not paths.secrets.is_relative_to(repo)
    assert "TUSHARE_TOKEN" not in serialized
    assert "DEEPSEEK_API_KEY" not in serialized
    assert "postgres_password" not in serialized
    assert "grafana_password" not in serialized


def test_runtime_configuration_serialization_is_idempotent(tmp_path: Path) -> None:
    config = RuntimeConfig(
        platform="windows",
        runtime_home=tmp_path / "runtime",
        qmt_builtin_bridge=QmtBuiltinBridgeConfig(
            bridge_root=tmp_path / "bridge",
            max_snapshot_age_seconds=90,
            expected_account_type="stock",
            expected_redacted_account_id="qmtacct-v1-0123456789abcdef01234567",
            polling_interval_seconds=4,
            heartbeat_interval_seconds=20,
        ),
    )
    restored = RuntimeConfig.from_mapping(config.as_dict())

    assert restored.as_dict() == config.as_dict()
    assert config.as_dict()["schema_version"] == 2
    assert config.as_dict()["broker_provider"] == "none"
    assert config.as_dict()["deepseek_live_calls_enabled"] is False
    assert config.as_dict()["qmt_builtin_bridge"] == {
        "bridge_root": str(tmp_path / "bridge"),
        "max_snapshot_age_seconds": 90.0,
        "expected_account_type": "STOCK",
        "expected_redacted_account_id": "qmtacct-v1-0123456789abcdef01234567",
        "polling_interval_seconds": 4.0,
        "heartbeat_interval_seconds": 20.0,
        "provider_mode": "simulation_signal",
    }


def test_qmt_bridge_configuration_reads_scoped_environment_and_never_accepts_raw_account_id(
    monkeypatch, tmp_path: Path
) -> None:
    runtime_home = tmp_path / "runtime"
    bridge_root = tmp_path / "external bridge"
    monkeypatch.setenv("QUANTPILOT_RUNTIME_HOME", str(runtime_home))
    monkeypatch.setenv("QUANTPILOT_QMT_BRIDGE_ROOT", str(bridge_root))
    monkeypatch.setenv("QUANTPILOT_QMT_MAX_SNAPSHOT_AGE_SECONDS", "45")
    monkeypatch.setenv("QUANTPILOT_QMT_EXPECTED_ACCOUNT_TYPE", "stock")
    monkeypatch.setenv("QUANTPILOT_QMT_EXPECTED_REDACTED_ACCOUNT_ID", "qmtacct-v1-0123456789abcdef01234567")
    monkeypatch.setenv("QUANTPILOT_QMT_POLL_INTERVAL_SECONDS", "3")
    monkeypatch.setenv("QUANTPILOT_QMT_HEARTBEAT_INTERVAL_SECONDS", "15")
    monkeypatch.setenv("QUANTPILOT_QMT_PROVIDER_MODE", "simulation_signal")

    bridge = RuntimeConfig.from_environment().qmt_builtin_bridge

    assert bridge.bridge_root == bridge_root
    assert bridge.max_snapshot_age_seconds == 45
    assert bridge.expected_account_type == "STOCK"
    assert bridge.expected_redacted_account_id == "qmtacct-v1-0123456789abcdef01234567"
    assert bridge.polling_interval_seconds == 3
    assert bridge.heartbeat_interval_seconds == 15
    assert bridge.provider_mode is QmtProviderMode.SIMULATION_SIGNAL

    monkeypatch.setenv(
        "QUANTPILOT_QMT_EXPECTED_REDACTED_ACCOUNT_ID",
        "raw-account-identifiers-are-forbidden",
    )
    with pytest.raises(ValueError, match="redacted binding format"):
        RuntimeConfig.from_environment()


@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        ({"max_snapshot_age_seconds": float("inf")}, "positive finite"),
        ({"polling_interval_seconds": -1}, "positive finite"),
        ({"polling_interval_seconds": 10, "heartbeat_interval_seconds": 5}, "at least polling"),
        ({"provider_mode": "live"}, "live"),
    ],
)
def test_qmt_bridge_configuration_rejects_unsafe_values(overrides: dict[str, object], message: str) -> None:
    defaults: dict[str, object] = {
        "bridge_root": Path("bridge"),
        "max_snapshot_age_seconds": 120,
        "expected_account_type": "STOCK",
        "polling_interval_seconds": 5,
        "heartbeat_interval_seconds": 30,
    }
    defaults.update(overrides)
    with pytest.raises(ValueError, match=message):
        QmtBuiltinBridgeConfig(**defaults)  # type: ignore[arg-type]


def test_runtime_layout_rejects_repository_local_state(monkeypatch, tmp_path: Path) -> None:
    repository = tmp_path / "repository"
    runtime = repository / "runtime"
    _create_runtime_layout(runtime)
    monkeypatch.setenv("QUANTPILOT_REPOSITORY_ROOT", str(repository))

    checks = {check.name: check for check in collect_runtime_diagnostics(RuntimeConfig(platform="windows", runtime_home=runtime), probe_services=False)}

    assert checks["runtime_layout"].status == "NOT_READY"
    assert checks["runtime_layout"].required is True


def test_windows_runtime_scripts_are_portable_secret_safe_and_ps51_compatible() -> None:
    root = Path(__file__).parents[2]
    script_paths = [
        root / "scripts" / "bootstrap_windows_runtime_v1.ps1",
        root / "scripts" / "start_windows_runtime_v1.ps1",
        root / "scripts" / "status_windows_runtime_v1.ps1",
        root / "scripts" / "stop_windows_runtime_v1.ps1",
        root / "scripts" / "inspect_qmt_builtin_bridge_v1.ps1",
        root / "scripts" / "windows_runtime_common_v1.ps1",
    ]
    scripts = {path.name: path.read_text(encoding="utf-8") for path in script_paths}
    content = "\n".join(scripts.values())
    parameter_match = re.search(r"param\((.*?)\)\s*\n", scripts["bootstrap_windows_runtime_v1.ps1"], re.DOTALL)
    assert parameter_match is not None
    bootstrap_parameter_block = parameter_match.group(1)

    assert not re.search(r"(?i)(?:atlas|gaoyn|[a-z]:\\code\\|/users/)", content)
    assert all(mode in bootstrap_parameter_block for mode in ("ValidateOnly", "SkipDocker", "NonInteractive", "ForceSecretRefresh"))
    assert not re.search(r"(?i)(tushare|deepseek).*(token|key)\s*[,)]", bootstrap_parameter_block)
    assert "Read-Host \"TUSHARE_TOKEN (input hidden)\" -AsSecureString" in content
    assert "ConvertFrom-SecureString" in content and "ConvertTo-SecureString" in content
    assert "docker compose down -v" not in content.lower()
    assert "winget" not in content.lower()
    assert '[ValidateSet("none", "qmt_builtin_bridge")]' in content
    assert "qmt_builtin_bridge = [pscustomobject][ordered]@{" in content
    assert "SetEnvironmentVariable" not in content and "EnvironmentVariableTarget" not in content
    assert not any(pattern in content for pattern in ("??", "?.", "ForEach-Object -Parallel", "$IsWindows"))


def test_powershell_scripts_do_not_assign_or_declare_automatic_variables() -> None:
    root = Path(__file__).parents[2]
    violations: list[str] = []
    assignment_pattern = re.compile(r"(?im)^\s*\$(?P<name>[A-Za-z_][A-Za-z0-9_]*)\s*=(?!=)")
    parameter_block_pattern = re.compile(r"(?is)\bparam\s*\((?P<body>.*?)\)")
    function_parameter_pattern = re.compile(r"(?is)\bfunction\s+[A-Za-z0-9_-]+\s*\((?P<body>.*?)\)")
    variable_pattern = re.compile(r"\$(?P<name>[A-Za-z_][A-Za-z0-9_]*)")

    for path in sorted((root / "scripts").glob("*.ps1")):
        content = path.read_text(encoding="utf-8")
        for match in assignment_pattern.finditer(content):
            if match.group("name").lower() in RESERVED_POWERSHELL_AUTOMATIC_VARIABLES:
                violations.append(f"{path.name}: assignment to ${match.group('name')}")
        for parameter_match in (*parameter_block_pattern.finditer(content), *function_parameter_pattern.finditer(content)):
            for variable_match in variable_pattern.finditer(parameter_match.group("body")):
                if variable_match.group("name").lower() in RESERVED_POWERSHELL_AUTOMATIC_VARIABLES:
                    violations.append(f"{path.name}: parameter ${variable_match.group('name')}")

    assert violations == []


def test_atomic_replace_script_contract_uses_real_backup_paths() -> None:
    root = Path(__file__).parents[2]
    scripts = {path.name: path.read_text(encoding="utf-8") for path in (root / "scripts").glob("*.ps1")}
    content = scripts["windows_runtime_common_v1.ps1"]
    all_content = "\n".join(scripts.values())

    assert "[IO.File]::Replace($fullTemporaryPath, $fullDestinationPath, $backupPath)" in content
    assert "$backupPath = Join-Path $destinationDirectory $backupFileName" in content
    assert "[Guid]::NewGuid().ToString(\"N\")" in content
    assert "Remove-Item -LiteralPath $backupPath -Force -ErrorAction Stop" in content
    assert "[IO.File]::Move($fullTemporaryPath, $fullDestinationPath)" in content
    assert not re.search(r"(?is)\[(?:IO|System\.IO)\.File\]::Replace\s*\([^)]*,[^)]*,\s*(?:\$null|['\"]\s*['\"])", all_content)
    assert not re.search(r"(?im)^\s*Remove-Item\b[^\n]*(?:\$DestinationPath|\$fullDestinationPath)", all_content)


def test_windows_bootstrap_merges_only_explicit_runtime_config_overrides_before_mutation() -> None:
    root = Path(__file__).parents[2]
    bootstrap = (root / "scripts" / "bootstrap_windows_runtime_v1.ps1").read_text(encoding="utf-8")
    common = (root / "scripts" / "windows_runtime_common_v1.ps1").read_text(encoding="utf-8")

    assert "$PSBoundParameters.ContainsKey($parameterName)" in bootstrap
    assert "$runtimeConfigArguments[$parameterName] = $PSBoundParameters[$parameterName]" in bootstrap
    assert "Write-QPRuntimeConfig @runtimeConfigArguments" in bootstrap
    assert "-BrokerProvider $BrokerProvider" not in bootstrap
    assert "Resolve-QPRuntimeConfigPayload -Overrides $runtimeConfigArguments" in bootstrap
    assert bootstrap.index("Resolve-QPRuntimeConfigPayload -Overrides $runtimeConfigArguments") < bootstrap.index(
        "Initialize-QPRuntimeDirectories"
    )
    assert bootstrap.index("Assert-QPAccountBindingKeyState") < bootstrap.index("Initialize-QPRuntimeDirectories")
    assert "foreach ($name in $PSBoundParameters.Keys)" in common
    assert '$Overrides.ContainsKey("BrokerProvider")' in common
    assert '$Overrides.ContainsKey("QmtMaxSnapshotAgeSeconds")' in common
    assert "$candidate.broker_provider = [string]$Overrides" in common
    assert "$candidate.qmt_builtin_bridge.max_snapshot_age_seconds = [double]$Overrides" in common
    assert "ConvertTo-QPRuntimeConfigV2" in common
    assert "Assert-QPRuntimeConfigBase -Config $Config -SchemaVersion 1" in common
    assert '$migrated.broker_provider = "none"' not in common  # The schema-v2 default already carries provider=none.
    assert "$migrated.runtime_home = [string]$Config.runtime_home" in common
    assert "$migrated.reporting_enabled = [bool]$Config.reporting_enabled" in common
    assert "$migrated.grafana_enabled = [bool]$Config.grafana_enabled" in common


def test_windows_account_binding_key_contract_is_random_atomic_private_and_never_printed() -> None:
    root = Path(__file__).parents[2]
    bootstrap = (root / "scripts" / "bootstrap_windows_runtime_v1.ps1").read_text(encoding="utf-8")
    common = (root / "scripts" / "windows_runtime_common_v1.ps1").read_text(encoding="utf-8")
    key_function_start = common.index("function Initialize-QPAccountBindingKey")
    key_function = common[key_function_start : common.index("function Read-QPRuntimeConfig", key_function_start)]

    assert '"state\\account_binding_key_v1.hex"' in common
    assert "New-Object byte[] 32" in key_function
    assert "[Security.Cryptography.RandomNumberGenerator]::Create()" in key_function
    assert '$_ .ToString("x2")'.replace(" ", "") in key_function.replace(" ", "")
    assert '"^[0-9a-f]{64}$"' in common
    assert "[IO.File]::Move($temporaryPath, $keyPath)" in key_function
    assert "Move-QPFileAtomically -TemporaryPath $temporaryPath -DestinationPath $keyPath" not in key_function
    assert "SetAccessRuleProtection($true, $false)" in common
    assert "Security.AccessControl.FileSystemRights]::FullControl" in common
    assert "Set-Acl -LiteralPath $KeyPath" in common
    assert "Write-Host" not in key_function and "Write-Output" not in key_function
    assert bootstrap.index("Initialize-QPAccountBindingKey") < bootstrap.index(
        'Initialize-QPLocalServiceSecret -Name "postgres_password"'
    )


def _powershell_literal(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


@pytest.mark.skipif(os.name != "nt", reason="requires Windows PowerShell 5.1 file replacement")
def test_windows_powershell_atomic_replacement_preserves_existing_destination(tmp_path: Path) -> None:
    root = Path(__file__).parents[2]
    powershell = shutil.which("powershell.exe") or shutil.which("powershell")
    if not powershell:
        pytest.skip("Windows PowerShell executable is unavailable")

    isolated_home = tmp_path / "runtime home with spaces"
    file_directory = tmp_path / "atomic files with spaces"
    script_path = tmp_path / "exercise atomic replace.ps1"
    common_script = root / "scripts" / "windows_runtime_common_v1.ps1"
    script_path.write_text(
        "\n".join(
            (
                "$ErrorActionPreference = 'Stop'",
                f"$env:QUANTPILOT_RUNTIME_HOME = {_powershell_literal(str(isolated_home))}",
                f". {_powershell_literal(str(common_script))}",
                f"$fileDirectory = {_powershell_literal(str(file_directory))}",
                "New-Item -ItemType Directory -Force -Path $fileDirectory | Out-Null",
                "$destination = Join-Path $fileDirectory 'runtime file.txt'",
                "$temporary = Join-Path $fileDirectory 'runtime file.txt.tmp'",
                "[IO.File]::WriteAllText($destination, 'old content')",
                "[IO.File]::WriteAllText($temporary, 'new content')",
                "Move-QPFileAtomically -TemporaryPath $temporary -DestinationPath $destination",
                "if ([IO.File]::ReadAllText($destination) -ne 'new content') { throw 'first replacement content mismatch' }",
                "if (Test-Path $temporary -PathType Leaf) { throw 'temporary file remained after first replacement' }",
                "if (Get-ChildItem -LiteralPath $fileDirectory -Filter '*.bak') { throw 'backup file remained after first replacement' }",
                "[IO.File]::WriteAllText($temporary, 'newer content')",
                "Move-QPFileAtomically -TemporaryPath $temporary -DestinationPath $destination",
                "if ([IO.File]::ReadAllText($destination) -ne 'newer content') { throw 'second replacement content mismatch' }",
                "if (Test-Path $temporary -PathType Leaf) { throw 'temporary file remained after second replacement' }",
                "if (Get-ChildItem -LiteralPath $fileDirectory -Filter '*.bak') { throw 'backup file remained after second replacement' }",
                "Write-QPRuntimeConfig",
                "Write-QPRuntimeConfig",
                "$configPath = Get-QPRuntimeConfigPath",
                "if (-not (Test-Path $configPath -PathType Leaf)) { throw 'repeated configuration write did not create runtime config' }",
                "if (Get-ChildItem -LiteralPath (Split-Path -Parent $configPath) -Filter '*.bak') { throw 'backup file remained after repeated configuration write' }",
                "$failureRaised = $false",
                "try { Move-QPFileAtomically -TemporaryPath (Join-Path $fileDirectory 'missing.tmp') -DestinationPath $destination } catch { $failureRaised = $true }",
                "if (-not $failureRaised) { throw 'missing temporary source did not fail' }",
                "if ([IO.File]::ReadAllText($destination) -ne 'newer content') { throw 'destination changed after failed replacement' }",
                "$staleTemporary = Join-Path $fileDirectory 'stale temporary.tmp'",
                "$invalidDestination = Join-Path $fileDirectory 'destination directory'",
                "[IO.File]::WriteAllText($staleTemporary, 'recovered content')",
                "New-Item -ItemType Directory -Force -Path $invalidDestination | Out-Null",
                "$invalidDestinationRaised = $false",
                "try { Move-QPFileAtomically -TemporaryPath $staleTemporary -DestinationPath $invalidDestination } catch { $invalidDestinationRaised = $true }",
                "if (-not $invalidDestinationRaised) { throw 'directory destination did not fail' }",
                "if (-not (Test-Path $staleTemporary -PathType Leaf)) { throw 'stale temporary was unexpectedly deleted after failure' }",
                "if ([IO.File]::ReadAllText($destination) -ne 'newer content') { throw 'valid destination changed after invalid destination failure' }",
                "Move-QPFileAtomically -TemporaryPath $staleTemporary -DestinationPath $destination",
                "if ([IO.File]::ReadAllText($destination) -ne 'recovered content') { throw 'stale temporary did not recover on a later write' }",
                "if (Test-Path $staleTemporary -PathType Leaf) { throw 'stale temporary remained after recovery' }",
            )
        ),
        encoding="utf-8",
    )

    result = subprocess.run(
        [powershell, "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(script_path)],
        cwd=root,
        capture_output=True,
        text=True,
        check=False,
        timeout=30,
    )

    assert result.returncode == 0, result.stdout + result.stderr


@pytest.mark.skipif(os.name != "nt", reason="requires Windows PowerShell 5.1 config merge, DPAPI, and ACL behavior")
def test_windows_powershell_runtime_config_migration_and_key_are_idempotent(tmp_path: Path) -> None:
    root = Path(__file__).parents[2]
    powershell = shutil.which("powershell.exe") or shutil.which("powershell")
    if not powershell:
        pytest.skip("Windows PowerShell executable is unavailable")

    runtime_home = tmp_path / "runtime home"
    bridge_root = tmp_path / "external bridge"
    migration_home = tmp_path / "migration runtime"
    malformed_home = tmp_path / "malformed runtime"
    invalid_key_bridge = tmp_path / "invalid key bridge"
    script_path = tmp_path / "exercise runtime config merge and key.ps1"
    common_script = root / "scripts" / "windows_runtime_common_v1.ps1"
    script_path.write_text(
        "\n".join(
            (
                "$ErrorActionPreference = 'Stop'",
                f"$env:QUANTPILOT_RUNTIME_HOME = {_powershell_literal(str(runtime_home))}",
                f". {_powershell_literal(str(common_script))}",
                f"$bridgeRoot = {_powershell_literal(str(bridge_root))}",
                "Write-QPRuntimeConfig -BrokerProvider qmt_builtin_bridge -QmtBridgeRoot $bridgeRoot -QmtMaxSnapshotAgeSeconds 77 -QmtExpectedAccountType STOCK -QmtExpectedRedactedAccountId 'qmtacct-v1-0123456789abcdef01234567' -QmtPollingIntervalSeconds 7 -QmtHeartbeatIntervalSeconds 35 -QmtProviderMode simulation_signal",
                "Initialize-QPAccountBindingKey -BridgeRoot $bridgeRoot",
                "Save-QPSecret -Name 'preserved_probe' -Value 'synthetic-only'",
                "$configBefore = Read-QPRuntimeConfig",
                "$configBeforeJson = $configBefore | ConvertTo-Json -Depth 4 -Compress",
                "$keyPath = Get-QPAccountBindingKeyPath -BridgeRoot $bridgeRoot",
                "$keyBefore = [IO.File]::ReadAllText($keyPath)",
                "$secretPath = Get-QPSecretPath 'preserved_probe'",
                "$secretBefore = [Convert]::ToBase64String([IO.File]::ReadAllBytes($secretPath))",
                "Write-QPRuntimeConfig",
                "$configRepeatedJson = (Read-QPRuntimeConfig) | ConvertTo-Json -Depth 4 -Compress",
                "if ($configRepeatedJson -cne $configBeforeJson) { throw 'omitted bootstrap parameters changed schema-v2 configuration' }",
                "Write-QPRuntimeConfig -QmtMaxSnapshotAgeSeconds 88",
                "$partial = Read-QPRuntimeConfig",
                "if ([string]$partial.broker_provider -cne 'qmt_builtin_bridge') { throw 'partial override reset provider' }",
                "if ([string]$partial.qmt_builtin_bridge.bridge_root -cne [IO.Path]::GetFullPath($bridgeRoot)) { throw 'partial override reset bridge root' }",
                "if ([double]$partial.qmt_builtin_bridge.max_snapshot_age_seconds -ne 88) { throw 'partial override did not change its own field' }",
                "if ([double]$partial.qmt_builtin_bridge.polling_interval_seconds -ne 7 -or [double]$partial.qmt_builtin_bridge.heartbeat_interval_seconds -ne 35) { throw 'partial override reset timing fields' }",
                "if ([string]$partial.qmt_builtin_bridge.expected_account_type -cne 'STOCK' -or [string]$partial.qmt_builtin_bridge.provider_mode -cne 'simulation_signal') { throw 'partial override reset account type or provider mode' }",
                "if ([string]$partial.qmt_builtin_bridge.expected_redacted_account_id -cne 'qmtacct-v1-0123456789abcdef01234567') { throw 'partial override reset account binding' }",
                "$overriddenAge = $partial.qmt_builtin_bridge.max_snapshot_age_seconds",
                "$partial.qmt_builtin_bridge.max_snapshot_age_seconds = $configBefore.qmt_builtin_bridge.max_snapshot_age_seconds",
                "if (($partial | ConvertTo-Json -Depth 4 -Compress) -cne $configBeforeJson) { throw 'age override changed a field other than max_snapshot_age_seconds' }",
                "$partial.qmt_builtin_bridge.max_snapshot_age_seconds = $overriddenAge",
                "$qmtSettingsBeforeDisable = $partial.qmt_builtin_bridge | ConvertTo-Json -Depth 3 -Compress",
                "Write-QPRuntimeConfig -BrokerProvider none",
                "$disabled = Read-QPRuntimeConfig",
                "if ([string]$disabled.broker_provider -cne 'none') { throw 'explicit provider=none did not disable bridge' }",
                "if (($disabled.qmt_builtin_bridge | ConvertTo-Json -Depth 3 -Compress) -cne $qmtSettingsBeforeDisable) { throw 'provider=none erased QMT settings' }",
                "Write-QPRuntimeConfig",
                "$disabledRepeated = Read-QPRuntimeConfig",
                "if ([string]$disabledRepeated.broker_provider -cne 'none') { throw 'omitted provider re-enabled explicitly disabled bridge' }",
                "if (($disabledRepeated.qmt_builtin_bridge | ConvertTo-Json -Depth 3 -Compress) -cne $qmtSettingsBeforeDisable) { throw 'rerun after provider=none changed QMT settings' }",
                "Initialize-QPAccountBindingKey -BridgeRoot $bridgeRoot",
                "if ([IO.File]::ReadAllText($keyPath) -cne $keyBefore) { throw 'repeated bootstrap replaced account-binding key' }",
                "if ([Convert]::ToBase64String([IO.File]::ReadAllBytes($secretPath)) -cne $secretBefore) { throw 'repeated bootstrap changed encrypted secret bytes' }",
                "if ($keyBefore -cnotmatch '^[0-9a-f]{64}$') { throw 'account-binding key format is invalid' }",
                "$keyAcl = Get-Acl -LiteralPath $keyPath",
                "if (-not $keyAcl.AreAccessRulesProtected) { throw 'account-binding key still inherits ACL rules' }",
                "$currentAccountName = [Security.Principal.WindowsIdentity]::GetCurrent().Name",
                "$keyRules = @($keyAcl.Access)",
                "if ($keyRules.Count -ne 1 -or [string]$keyRules[0].IdentityReference.Value -cne $currentAccountName -or [string]$keyRules[0].AccessControlType -cne 'Allow') { throw 'account-binding key ACL is not current-user-only' }",
                f"$env:QUANTPILOT_RUNTIME_HOME = {_powershell_literal(str(migration_home))}",
                "Initialize-QPRuntimeDirectories",
                "Save-QPSecret -Name 'migration_probe' -Value 'migration-synthetic'",
                "$migrationSecretPath = Get-QPSecretPath 'migration_probe'",
                "$migrationSecretBefore = [Convert]::ToBase64String([IO.File]::ReadAllBytes($migrationSecretPath))",
                "$migrationRuntimeHome = Get-QPRuntimeHome",
                "$schemaOne = [ordered]@{ schema_version = 1; platform = 'windows'; timezone = 'Asia/Shanghai'; broker_provider = 'none'; reporting_enabled = $false; grafana_enabled = $false; deepseek_live_calls_enabled = $false; runtime_home = $migrationRuntimeHome; postgres_dsn_env_var = 'QUANTPILOT_POSTGRES_DSN'; grafana_url = 'http://localhost:3000'; paths = [ordered]@{ config = (Join-Path $migrationRuntimeHome 'config'); secrets = (Join-Path $migrationRuntimeHome 'secrets'); logs = (Join-Path $migrationRuntimeHome 'logs'); state = (Join-Path $migrationRuntimeHome 'state'); reports = (Join-Path $migrationRuntimeHome 'reports'); cache = (Join-Path $migrationRuntimeHome 'cache') } }",
                "$schemaOnePath = Get-QPRuntimeConfigPath",
                "[IO.File]::WriteAllText($schemaOnePath, ($schemaOne | ConvertTo-Json -Depth 3), (New-Object Text.UTF8Encoding($false)))",
                "$migrationCandidate = Resolve-QPRuntimeConfigPayload",
                "if ([int]$migrationCandidate.schema_version -ne 2 -or [string]$migrationCandidate.broker_provider -cne 'none') { throw 'schema-v1 migration candidate is invalid' }",
                "if ([bool]$migrationCandidate.reporting_enabled -or [bool]$migrationCandidate.grafana_enabled) { throw 'schema-v1 safe service settings were not preserved' }",
                "if ([string]$migrationCandidate.qmt_builtin_bridge.bridge_root -cne (Join-Path $migrationRuntimeHome 'qmt_builtin_bridge')) { throw 'schema-v1 migration did not create default QMT block' }",
                "Write-QPRuntimeConfig",
                "$migrated = Read-QPRuntimeConfig",
                "if ([int]$migrated.schema_version -ne 2 -or [string]$migrated.broker_provider -cne 'none') { throw 'schema-v1 migration was not persisted' }",
                "if ([Convert]::ToBase64String([IO.File]::ReadAllBytes($migrationSecretPath)) -cne $migrationSecretBefore) { throw 'schema migration changed encrypted secret bytes' }",
                "Initialize-QPAccountBindingKey -BridgeRoot ([string]$migrated.qmt_builtin_bridge.bridge_root)",
                "if (-not (Test-Path (Get-QPAccountBindingKeyPath -BridgeRoot ([string]$migrated.qmt_builtin_bridge.bridge_root)) -PathType Leaf)) { throw 'migrated default bridge key was not created' }",
                f"$env:QUANTPILOT_RUNTIME_HOME = {_powershell_literal(str(malformed_home))}",
                "Initialize-QPRuntimeDirectories",
                "Save-QPSecret -Name 'malformed_probe' -Value 'malformed-synthetic'",
                "$malformedSecretPath = Get-QPSecretPath 'malformed_probe'",
                "$malformedSecretBefore = [Convert]::ToBase64String([IO.File]::ReadAllBytes($malformedSecretPath))",
                "$malformedConfigPath = Get-QPRuntimeConfigPath",
                "[IO.File]::WriteAllText($malformedConfigPath, '{ malformed', (New-Object Text.UTF8Encoding($false)))",
                "$malformedBefore = [IO.File]::ReadAllBytes($malformedConfigPath)",
                "$malformedRaised = $false",
                "try { $null = Resolve-QPRuntimeConfigPayload } catch { $malformedRaised = $true }",
                "if (-not $malformedRaised) { throw 'malformed existing config did not fail preflight' }",
                "if ([Convert]::ToBase64String([IO.File]::ReadAllBytes($malformedConfigPath)) -cne [Convert]::ToBase64String($malformedBefore)) { throw 'malformed config was changed during preflight' }",
                "if ([Convert]::ToBase64String([IO.File]::ReadAllBytes($malformedSecretPath)) -cne $malformedSecretBefore) { throw 'malformed config preflight changed secret bytes' }",
                "if (Test-Path (Join-Path (Get-QPRuntimeHome) 'qmt_builtin_bridge\\state\\account_binding_key_v1.hex')) { throw 'malformed config preflight generated a key' }",
                f"$invalidKeyBridge = {_powershell_literal(str(invalid_key_bridge))}",
                "$invalidKeyPath = Get-QPAccountBindingKeyPath -BridgeRoot $invalidKeyBridge",
                "New-Item -ItemType Directory -Force -Path (Split-Path -Parent $invalidKeyPath) | Out-Null",
                "[IO.File]::WriteAllText($invalidKeyPath, ('A' * 64), (New-Object Text.UTF8Encoding($false)))",
                "$invalidKeyBefore = [IO.File]::ReadAllBytes($invalidKeyPath)",
                "$invalidKeyRaised = $false",
                "try { Initialize-QPAccountBindingKey -BridgeRoot $invalidKeyBridge } catch { $invalidKeyRaised = $true }",
                "if (-not $invalidKeyRaised) { throw 'malformed existing key did not fail' }",
                "if ([Convert]::ToBase64String([IO.File]::ReadAllBytes($invalidKeyPath)) -cne [Convert]::ToBase64String($invalidKeyBefore)) { throw 'malformed existing key bytes changed' }",
            )
        ),
        encoding="utf-8",
    )

    result = subprocess.run(
        [powershell, "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(script_path)],
        cwd=root,
        capture_output=True,
        text=True,
        check=False,
        timeout=45,
    )

    assert result.returncode == 0, result.stdout + result.stderr


def test_windows_lifecycle_uses_scoped_environment_and_read_only_status() -> None:
    root = Path(__file__).parents[2]
    start = (root / "scripts" / "start_windows_runtime_v1.ps1").read_text(encoding="utf-8")
    status = (root / "scripts" / "status_windows_runtime_v1.ps1").read_text(encoding="utf-8")
    stop = (root / "scripts" / "stop_windows_runtime_v1.ps1").read_text(encoding="utf-8")
    bootstrap = (root / "scripts" / "bootstrap_windows_runtime_v1.ps1").read_text(encoding="utf-8")
    inspect_bridge = (root / "scripts" / "inspect_qmt_builtin_bridge_v1.ps1").read_text(encoding="utf-8")

    for content in (start, status, stop, bootstrap, inspect_bridge):
        assert "Push-QPRuntimeEnvironment" in content
        assert "finally" in content
        assert "Restore-QPRuntimeEnvironment" in content
    assert 'Invoke-QPCompose -ComposeArguments @("stop")' in stop
    assert not re.search(r'Invoke-QPCompose[^\n]*@\("(?:up|start|stop|down)', status)
    assert "Save-QPSecret" not in status and "Write-QPRuntimeConfig" not in status
    assert "inspect_qmt_builtin_bridge_v1.py" in inspect_bridge
    assert "Save-QPSecret" not in inspect_bridge and "Write-QPRuntimeConfig" not in inspect_bridge
    assert 'if ($NonInteractive -and -not $SkipDocker)' in bootstrap
    assert '"--skip-services"' in bootstrap


def test_missing_qmt_snapshot_provisioning_flag_is_bootstrap_only() -> None:
    root = Path(__file__).parents[2]
    flag = "--allow-missing-qmt-snapshot-during-provisioning"
    bootstrap = (root / "scripts" / "bootstrap_windows_runtime_v1.ps1").read_text(encoding="utf-8")
    start = (root / "scripts" / "start_windows_runtime_v1.ps1").read_text(encoding="utf-8")
    status = (root / "scripts" / "status_windows_runtime_v1.ps1").read_text(encoding="utf-8")
    inspect_powershell = (root / "scripts" / "inspect_qmt_builtin_bridge_v1.ps1").read_text(encoding="utf-8")
    inspect_python = (root / "scripts" / "inspect_qmt_builtin_bridge_v1.py").read_text(encoding="utf-8")
    doctor_python = (root / "scripts" / "runtime_doctor_v1.py").read_text(encoding="utf-8")
    docs = (root / "docs" / "windows_runtime.md").read_text(encoding="utf-8")

    assert bootstrap.count(flag) == 1
    provisioning_sequence = (
        "Resolve-QPRuntimeConfigPayload -Overrides $runtimeConfigArguments",
        "Write-QPRuntimeConfig @runtimeConfigArguments",
        "    Initialize-QPAccountBindingKey -BridgeRoot",
        '    Initialize-QPLocalServiceSecret -Name "postgres_password"',
        "    Initialize-QPApiSecrets\n",
        '        Invoke-QPCompose -ComposeArguments @("up", "-d")',
        flag,
        "& $venvPython @doctorArguments",
    )
    assert [bootstrap.index(marker) for marker in provisioning_sequence] == sorted(
        bootstrap.index(marker) for marker in provisioning_sequence
    )
    assert flag in doctor_python
    assert all(flag not in content for content in (start, status, inspect_powershell, inspect_python))
    assert "provisioning exception is bootstrap-only" in docs.lower()
    assert "provider=none` is unchanged" in docs
    assert "malformed, stale, or unsafe snapshot" in docs


@pytest.mark.skipif(os.name != "nt", reason="requires Windows PowerShell 5.1 bootstrap diagnostic invocation")
def test_windows_bootstrap_diagnostic_allows_only_missing_first_qmt_snapshot(tmp_path: Path) -> None:
    root = Path(__file__).parents[2]
    powershell = shutil.which("powershell.exe") or shutil.which("powershell")
    if not powershell:
        pytest.skip("Windows PowerShell executable is unavailable")

    runtime_home = tmp_path / "provisioning runtime"
    bridge_root = tmp_path / "provisioning bridge"
    stub_root = tmp_path / "required package stubs"
    for package_name in ("prefect", "psycopg", "pandas", "tushare", "pyarrow"):
        package = stub_root / package_name
        package.mkdir(parents=True)
        (package / "__init__.py").write_text('__version__ = "offline-windows-test"\n', encoding="utf-8")
    script_path = tmp_path / "exercise provisioning doctor boundary.ps1"
    common_script = root / "scripts" / "windows_runtime_common_v1.ps1"
    doctor_script = root / "scripts" / "runtime_doctor_v1.py"
    script_path.write_text(
        "\n".join(
            (
                "$ErrorActionPreference = 'Stop'",
                f"$pythonExecutable = {_powershell_literal(sys.executable)}",
                f"$doctorScript = {_powershell_literal(str(doctor_script))}",
                f"$repositoryRoot = {_powershell_literal(str(root))}",
                f"$env:QUANTPILOT_RUNTIME_HOME = {_powershell_literal(str(runtime_home))}",
                f"$bridgeRoot = {_powershell_literal(str(bridge_root))}",
                f"$stubRoot = {_powershell_literal(str(stub_root))}",
                f". {_powershell_literal(str(common_script))}",
                "Initialize-QPRuntimeDirectories",
                "Initialize-QPAccountBindingKey -BridgeRoot $bridgeRoot",
                "$env:PYTHONPATH = $stubRoot + [IO.Path]::PathSeparator + (Join-Path $repositoryRoot 'src')",
                "$env:QUANTPILOT_REPOSITORY_ROOT = $repositoryRoot",
                "$env:QUANTPILOT_RUNTIME_PLATFORM = 'windows'",
                "$env:QUANTPILOT_TIMEZONE = 'Asia/Shanghai'",
                "$env:QUANTPILOT_BROKER_PROVIDER = 'qmt_builtin_bridge'",
                "$env:QUANTPILOT_QMT_BRIDGE_ROOT = $bridgeRoot",
                "$env:QUANTPILOT_QMT_MAX_SNAPSHOT_AGE_SECONDS = '120'",
                "$env:QUANTPILOT_QMT_EXPECTED_ACCOUNT_TYPE = 'STOCK'",
                "$env:QUANTPILOT_QMT_POLL_INTERVAL_SECONDS = '5'",
                "$env:QUANTPILOT_QMT_HEARTBEAT_INTERVAL_SECONDS = '30'",
                "$env:QUANTPILOT_QMT_PROVIDER_MODE = 'simulation_signal'",
                "$env:QUANTPILOT_REPORTING_ENABLED = 'false'",
                "$env:QUANTPILOT_GRAFANA_ENABLED = 'false'",
                "$env:QUANTPILOT_DEEPSEEK_LIVE_CALLS_ENABLED = 'false'",
                "$env:TUSHARE_TOKEN = 'synthetic-offline-token'",
                "Remove-Item Env:QUANTPILOT_QMT_EXPECTED_REDACTED_ACCOUNT_ID -ErrorAction SilentlyContinue",
                "function Invoke-QPDoctor([string[]]$CommandArguments) {",
                "    $doctorOutput = @(& $pythonExecutable $doctorScript @CommandArguments 2>&1)",
                "    $doctorExitCode = $LASTEXITCODE",
                "    $doctorPayload = (($doctorOutput -join [Environment]::NewLine) | ConvertFrom-Json)",
                "    return [pscustomobject]@{ ExitCode = $doctorExitCode; Payload = $doctorPayload }",
                "}",
                "$provisioningArguments = @('--format', 'json', '--strict', '--skip-services', '--allow-missing-qmt-snapshot-during-provisioning')",
                "$freshProvisioning = Invoke-QPDoctor -CommandArguments $provisioningArguments",
                "$repeatedProvisioning = Invoke-QPDoctor -CommandArguments $provisioningArguments",
                "foreach ($result in @($freshProvisioning, $repeatedProvisioning)) {",
                "    if ([int]$result.ExitCode -ne 0 -or -not [bool]$result.Payload.ok) { throw 'bootstrap provisioning doctor rejected a missing first snapshot' }",
                "    $snapshotCheck = @($result.Payload.checks | Where-Object { $_.name -eq 'qmt_builtin_bridge.snapshot' })",
                "    if ($snapshotCheck.Count -ne 1 -or [string]$snapshotCheck[0].status -cne 'EXPECTED') { throw 'missing first snapshot was not narrowly reported as EXPECTED' }",
                "}",
                "$strictQmt = Invoke-QPDoctor -CommandArguments @('--format', 'json', '--strict', '--skip-services')",
                "if ([int]$strictQmt.ExitCode -eq 0 -or [bool]$strictQmt.Payload.ok) { throw 'ordinary status semantics accepted a missing QMT snapshot' }",
                "$env:QUANTPILOT_BROKER_PROVIDER = 'none'",
                "$noneStrict = Invoke-QPDoctor -CommandArguments @('--format', 'json', '--strict', '--skip-services')",
                "$noneProvisioning = Invoke-QPDoctor -CommandArguments $provisioningArguments",
                "foreach ($result in @($noneStrict, $noneProvisioning)) {",
                "    if ([int]$result.ExitCode -ne 0 -or -not [bool]$result.Payload.ok) { throw 'provider=none behavior was weakened' }",
                "    $brokerCheck = @($result.Payload.checks | Where-Object { $_.name -eq 'broker' })",
                "    $qmtChecks = @($result.Payload.checks | Where-Object { $_.name -like 'qmt_builtin_bridge.*' })",
                "    if ($brokerCheck.Count -ne 1 -or [string]$brokerCheck[0].status -cne 'EXPECTED' -or $qmtChecks.Count -ne 0) { throw 'provider=none diagnostics changed under provisioning flag' }",
                "}",
            )
        ),
        encoding="utf-8",
    )

    result = subprocess.run(
        [powershell, "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(script_path)],
        cwd=root,
        capture_output=True,
        text=True,
        check=False,
        timeout=45,
    )

    assert result.returncode == 0, result.stdout + result.stderr


def test_compose_and_windows_ci_cover_runtime_contract() -> None:
    root = Path(__file__).parents[2]
    compose = (root / "infra" / "control_center" / "docker-compose.yml").read_text(encoding="utf-8")
    workflow = (root / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    docs = (root / "docs" / "windows_runtime.md").read_text(encoding="utf-8")
    pyproject = (root / "pyproject.toml").read_text(encoding="utf-8")

    assert compose.count("POSTGRES_PASSWORD:") >= 2
    assert "grafana_data:/var/lib/grafana" in compose
    assert "grafana_data: {}" in compose and "pgdata: {}" in compose
    assert 'python -m pip install -e ".[dev,windows-runtime]"' in workflow
    assert "shell: powershell" in workflow
    assert "-NonInteractive -SkipDocker" in workflow
    assert '"prefect>=3.1.16,<4"' in pyproject
    assert '"tzdata>=2025.2; platform_system == \'Windows\'"' in pyproject
    assert not re.search(r"(?i)(?:atlas|gaoyn|[a-z]:\\code\\|/users/)", docs)


def test_runtime_doctor_strict_mode_returns_nonzero_for_missing_required_packages(monkeypatch, capsys) -> None:
    import scripts.runtime_doctor_v1 as doctor_script

    monkeypatch.setattr(doctor_script, "diagnostics_payload", lambda **_kwargs: {"ok": False, "checks": []})
    assert doctor_script.main(["--format", "json", "--strict", "--skip-services"]) == 1
    assert json.loads(capsys.readouterr().out)["ok"] is False
