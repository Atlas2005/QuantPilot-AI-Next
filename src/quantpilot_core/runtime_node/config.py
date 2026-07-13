"""Platform-neutral runtime-node configuration; no broker implementation lives here."""
from __future__ import annotations

import os
import platform
from pathlib import Path
from typing import Any, Mapping
from dataclasses import dataclass, field
from enum import Enum
from zoneinfo import ZoneInfo

RUNTIME_CONFIG_SCHEMA_VERSION = 1


class BrokerProvider(str, Enum):
    NONE = "none"
    PAPER = "paper"
    QMT = "qmt"  # Provider selection only; an adapter is intentionally absent.


@dataclass(frozen=True)
class ServiceReadiness:
    postgres_configured: bool = False
    grafana_configured: bool = False
    control_center_configured: bool = False


@dataclass(frozen=True)
class RuntimePaths:
    home: Path
    config: Path
    secrets: Path
    logs: Path
    state: Path
    reports: Path
    cache: Path

    @classmethod
    def under(cls, home: str | Path) -> "RuntimePaths":
        root = Path(home).expanduser()
        return cls(root, root / "config", root / "secrets", root / "logs", root / "state", root / "reports", root / "cache")


def default_runtime_home() -> Path:
    """Keep machine-local runtime state out of the checked-out repository."""
    local_app_data = os.environ.get("LOCALAPPDATA")
    return Path(local_app_data) / "QuantPilot" / "runtime" if local_app_data else Path.home() / ".local" / "share" / "QuantPilot" / "runtime"


def _environment_bool(name: str, default: bool) -> bool:
    value = os.environ.get(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class RuntimeConfig:
    platform: str = field(default_factory=lambda: platform.system().lower())
    timezone: str = "Asia/Shanghai"
    services: ServiceReadiness = field(default_factory=ServiceReadiness)
    broker_provider: BrokerProvider = BrokerProvider.NONE
    runtime_home: Path = field(default_factory=default_runtime_home)
    reporting_enabled: bool = True
    grafana_enabled: bool = True
    deepseek_live_calls_enabled: bool = False

    def __post_init__(self) -> None:
        ZoneInfo(self.timezone)

    @classmethod
    def from_environment(cls) -> "RuntimeConfig":
        provider = BrokerProvider(os.environ.get("QUANTPILOT_BROKER_PROVIDER", BrokerProvider.NONE.value).lower())
        return cls(
            platform=os.environ.get("QUANTPILOT_RUNTIME_PLATFORM", platform.system().lower()),
            timezone=os.environ.get("QUANTPILOT_TIMEZONE", "Asia/Shanghai"),
            broker_provider=provider,
            runtime_home=Path(os.environ.get("QUANTPILOT_RUNTIME_HOME", default_runtime_home())),
            reporting_enabled=_environment_bool("QUANTPILOT_REPORTING_ENABLED", True),
            grafana_enabled=_environment_bool("QUANTPILOT_GRAFANA_ENABLED", True),
            deepseek_live_calls_enabled=_environment_bool("QUANTPILOT_DEEPSEEK_LIVE_CALLS_ENABLED", False),
            services=ServiceReadiness(
                postgres_configured=bool(os.environ.get("QUANTPILOT_POSTGRES_DSN")),
                grafana_configured=bool(os.environ.get("QUANTPILOT_GRAFANA_URL")),
                control_center_configured=bool(os.environ.get("QUANTPILOT_CONTROL_CENTER_URL")),
            ),
        )

    @property
    def paths(self) -> RuntimePaths:
        return RuntimePaths.under(self.runtime_home)

    def as_dict(self) -> dict[str, Any]:
        """Persist operational settings only; credentials must stay in secret storage."""
        return {
            "schema_version": RUNTIME_CONFIG_SCHEMA_VERSION,
            "platform": self.platform,
            "timezone": self.timezone,
            "broker_provider": self.broker_provider.value,
            "reporting_enabled": self.reporting_enabled,
            "grafana_enabled": self.grafana_enabled,
            "deepseek_live_calls_enabled": self.deepseek_live_calls_enabled,
            "runtime_home": str(self.runtime_home),
            "paths": {name: str(getattr(self.paths, name)) for name in ("config", "secrets", "logs", "state", "reports", "cache")},
            "postgres_dsn_env_var": "QUANTPILOT_POSTGRES_DSN",
            "grafana_url": "http://localhost:3000",
        }

    @classmethod
    def from_mapping(cls, payload: Mapping[str, Any]) -> "RuntimeConfig":
        return cls(
            platform=str(payload.get("platform", platform.system().lower())),
            timezone=str(payload.get("timezone", "Asia/Shanghai")),
            broker_provider=BrokerProvider(str(payload.get("broker_provider", BrokerProvider.NONE.value))),
            runtime_home=Path(str(payload.get("runtime_home", default_runtime_home()))),
            reporting_enabled=bool(payload.get("reporting_enabled", True)),
            grafana_enabled=bool(payload.get("grafana_enabled", True)),
            deepseek_live_calls_enabled=bool(payload.get("deepseek_live_calls_enabled", False)),
        )
