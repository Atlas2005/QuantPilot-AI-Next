"""Read-only runtime readiness checks suitable for local nodes and CI."""
from __future__ import annotations

import importlib
import importlib.util
import os
import platform
import shutil
import subprocess
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from .config import BrokerProvider, RuntimeConfig

REQUIRED_RUNTIME_PACKAGES = ("prefect", "psycopg", "pandas", "tushare", "pyarrow")
SUCCESSFUL_REQUIRED_STATUSES = {"READY", "REACHABLE", "CONFIGURED", "EXPECTED", "DISABLED", "SKIPPED"}


@dataclass(frozen=True)
class DoctorCheck:
    name: str
    status: str
    detail: str
    required: bool = False

    def as_dict(self) -> dict[str, str | bool]:
        return asdict(self)


def _package_status(name: str, *, required: bool = False) -> DoctorCheck:
    spec = importlib.util.find_spec(name)
    if spec is None:
        return DoctorCheck(
            f"package.{name}",
            "NOT_READY" if required else "OPTIONAL_NOT_INSTALLED",
            "required runtime package is not installed" if required else "optional package is not installed",
            required,
        )
    try:
        module = importlib.import_module(name)
        version = getattr(module, "__version__", "installed")
    except Exception as exc:  # A broken install should be visible without leaking environment data.
        return DoctorCheck(
            f"package.{name}",
            "NOT_READY" if required else "OPTIONAL_NOT_READY",
            f"import failed: {type(exc).__name__}",
            required,
        )
    return DoctorCheck(f"package.{name}", "READY", f"version={version}", required)


def _postgres_status(config: RuntimeConfig, *, probe_services: bool, timeout_seconds: float) -> DoctorCheck:
    if not config.reporting_enabled:
        return DoctorCheck("postgresql", "DISABLED", "reporting is disabled")
    dsn = os.environ.get("QUANTPILOT_POSTGRES_DSN")
    if not config.services.postgres_configured or not dsn:
        return DoctorCheck("postgresql", "NOT_READY", "required DSN is not configured", True)
    if probe_services:
        return DoctorCheck("postgresql", "NOT_CHECKED", "configured; reachability must be established by the runtime doctor script", True)
    return DoctorCheck("postgresql", "CONFIGURED", "DSN configured; reachability check skipped", True)


def _grafana_status(config: RuntimeConfig, *, probe_services: bool, timeout_seconds: float) -> DoctorCheck:
    if not config.grafana_enabled:
        return DoctorCheck("grafana", "DISABLED", "Grafana is disabled")
    url = os.environ.get("QUANTPILOT_GRAFANA_URL")
    if not config.services.grafana_configured or not url:
        return DoctorCheck("grafana", "NOT_READY", "required local URL is not configured", True)
    if probe_services:
        return DoctorCheck("grafana", "NOT_CHECKED", "configured; reachability must be established by the runtime doctor script", True)
    return DoctorCheck("grafana", "CONFIGURED", "local URL configured; reachability check skipped", True)


def _layout_status(config: RuntimeConfig) -> DoctorCheck:
    home = config.runtime_home.expanduser().resolve()
    repository_value = os.environ.get("QUANTPILOT_REPOSITORY_ROOT")
    repository: Path | None = Path(repository_value).expanduser().resolve() if repository_value else None
    if repository is None:
        source_checkout = Path(__file__).resolve().parents[3]
        if (source_checkout / "pyproject.toml").is_file() and (source_checkout / "src").is_dir():
            repository = source_checkout
    if repository is not None:
        try:
            home.relative_to(repository)
        except ValueError:
            pass
        else:
            return DoctorCheck("runtime_layout", "NOT_READY", "runtime home is inside the Git repository", True)
    else:
        return DoctorCheck("runtime_layout", "NOT_CHECKED", "repository root is unavailable; runtime-home isolation could not be verified", True)
    missing = [name for name in ("config", "secrets", "logs", "state", "reports", "cache") if not getattr(config.paths, name).is_dir()]
    if missing:
        return DoctorCheck("runtime_layout", "NOT_READY", f"missing required runtime directories: {','.join(missing)}", True)
    return DoctorCheck("runtime_layout", "READY", "runtime directories exist outside the repository", True)


def collect_runtime_diagnostics(
    config: RuntimeConfig | None = None,
    *,
    probe_services: bool = True,
    timeout_seconds: float = 3.0,
) -> tuple[DoctorCheck, ...]:
    """Inspect local requirements; network reachability is delegated to the runtime doctor script."""
    config = config or RuntimeConfig.from_environment()
    python_ready = sys.version_info[:2] == (3, 12)
    actual_platform = platform.system().lower()
    platform_ready = actual_platform == "windows" and config.platform == "windows"
    checks: list[DoctorCheck] = [
        DoctorCheck("python", "READY" if python_ready else "NOT_READY", sys.version.split()[0], True),
        DoctorCheck("operating_system", "READY" if platform_ready else "NOT_READY", f"actual={actual_platform}; configured={config.platform}", True),
        _layout_status(config),
    ]
    try:
        importlib.import_module("quantpilot_core")
    except Exception as exc:
        checks.append(DoctorCheck("project_import", "NOT_READY", f"import failed: {type(exc).__name__}", True))
    else:
        checks.append(DoctorCheck("project_import", "READY", "quantpilot_core import succeeded", True))
    checks.extend(_package_status(name, required=True) for name in REQUIRED_RUNTIME_PACKAGES)
    checks.append(_package_status("xtquant"))

    if probe_services:
        docker = shutil.which("docker")
        checks.append(DoctorCheck("docker", "READY" if docker else "NOT_READY", "docker executable found" if docker else "docker executable not on PATH", True))
        compose_ready = False
        if docker:
            try:
                compose_ready = subprocess.run(
                    [docker, "compose", "version"],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    timeout=timeout_seconds,
                    check=False,
                ).returncode == 0
            except (OSError, subprocess.TimeoutExpired):
                compose_ready = False
        checks.append(DoctorCheck("docker_compose", "READY" if compose_ready else "NOT_READY", "docker compose available" if compose_ready else "docker compose is unavailable", True))
    else:
        checks.extend(
            (
                DoctorCheck("docker", "SKIPPED", "service checks disabled"),
                DoctorCheck("docker_compose", "SKIPPED", "service checks disabled"),
            )
        )

    checks.append(_postgres_status(config, probe_services=probe_services, timeout_seconds=timeout_seconds))
    checks.append(_grafana_status(config, probe_services=probe_services, timeout_seconds=timeout_seconds))
    checks.append(
        DoctorCheck(
            "control_center",
            "CONFIGURED" if config.services.control_center_configured else "NOT_CONFIGURED",
            "local control-center URL configured" if config.services.control_center_configured else "control-center URL is not configured",
        )
    )
    if config.broker_provider is BrokerProvider.NONE:
        broker_status, broker_detail = "EXPECTED", "provider=none; broker connectivity and order submission are disabled"
    else:
        broker_status, broker_detail = "NOT_READY", f"provider={config.broker_provider.value}; only provider=none is permitted in this runtime"
    checks.append(DoctorCheck("broker", broker_status, broker_detail, True))
    return tuple(checks)


def diagnostics_payload(
    config: RuntimeConfig | None = None,
    *,
    probe_services: bool = True,
    timeout_seconds: float = 3.0,
) -> dict[str, Any]:
    checks = collect_runtime_diagnostics(config, probe_services=probe_services, timeout_seconds=timeout_seconds)
    return {
        "ok": all(check.status in SUCCESSFUL_REQUIRED_STATUSES for check in checks if check.required),
        "checks": [check.as_dict() for check in checks],
    }
