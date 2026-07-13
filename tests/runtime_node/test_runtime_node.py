from __future__ import annotations

import json
import re
from pathlib import Path

from quantpilot_core.runtime_node import BrokerProvider, RuntimeConfig, RuntimePaths, ServiceReadiness, collect_runtime_diagnostics
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


def test_runtime_config_defaults_to_no_broker_and_supports_future_provider(monkeypatch) -> None:
    monkeypatch.delenv("QUANTPILOT_BROKER_PROVIDER", raising=False)
    assert RuntimeConfig.from_environment().broker_provider is BrokerProvider.NONE

    monkeypatch.setenv("QUANTPILOT_BROKER_PROVIDER", "qmt")
    assert RuntimeConfig.from_environment().broker_provider is BrokerProvider.QMT


def test_runtime_diagnostics_require_no_broker_and_skip_bounded_service_probes(monkeypatch, tmp_path: Path) -> None:
    runtime = tmp_path / "runtime"
    _create_runtime_layout(runtime)
    monkeypatch.setenv("QUANTPILOT_POSTGRES_DSN", "postgresql://configured")
    monkeypatch.setenv("QUANTPILOT_GRAFANA_URL", "http://localhost:3000")
    monkeypatch.setenv("TUSHARE_TOKEN", "synthetic-placeholder")
    config = RuntimeConfig(
        platform="windows",
        timezone="Asia/Shanghai",
        broker_provider=BrokerProvider.PAPER,
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
    assert "only provider=none" in checks["broker"].detail


def test_qmt_and_deepseek_absence_are_explicitly_optional(monkeypatch, tmp_path: Path) -> None:
    runtime = tmp_path / "runtime"
    _create_runtime_layout(runtime)
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    config = RuntimeConfig(platform="windows", runtime_home=runtime)
    checks = {check.name: check for check in collect_runtime_diagnostics(config, probe_services=False)}
    runtime_checks = {check["name"]: check for check in runtime_diagnostics_payload(probe_services=False)["checks"]}

    assert checks["package.xtquant"].required is False
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
    config = RuntimeConfig(platform="windows", runtime_home=tmp_path / "runtime")
    restored = RuntimeConfig.from_mapping(config.as_dict())

    assert restored.as_dict() == config.as_dict()
    assert config.as_dict()["schema_version"] == 1
    assert config.as_dict()["broker_provider"] == "none"
    assert config.as_dict()["deepseek_live_calls_enabled"] is False


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
    assert "broker_provider = \"none\"" in content
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


def test_windows_lifecycle_uses_scoped_environment_and_read_only_status() -> None:
    root = Path(__file__).parents[2]
    start = (root / "scripts" / "start_windows_runtime_v1.ps1").read_text(encoding="utf-8")
    status = (root / "scripts" / "status_windows_runtime_v1.ps1").read_text(encoding="utf-8")
    stop = (root / "scripts" / "stop_windows_runtime_v1.ps1").read_text(encoding="utf-8")
    bootstrap = (root / "scripts" / "bootstrap_windows_runtime_v1.ps1").read_text(encoding="utf-8")

    for content in (start, status, stop, bootstrap):
        assert "Push-QPRuntimeEnvironment" in content
        assert "finally" in content
        assert "Restore-QPRuntimeEnvironment" in content
    assert 'Invoke-QPCompose -ComposeArguments @("stop")' in stop
    assert not re.search(r'Invoke-QPCompose[^\n]*@\("(?:up|start|stop|down)', status)
    assert "Save-QPSecret" not in status and "Write-QPRuntimeConfig" not in status
    assert 'if ($NonInteractive -and -not $SkipDocker)' in bootstrap
    assert '"--skip-services"' in bootstrap


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
