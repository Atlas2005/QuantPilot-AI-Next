"""Platform-neutral runtime-node configuration; no broker implementation lives here."""
from __future__ import annotations

import math
import os
import platform
import re
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Mapping
from zoneinfo import ZoneInfo

RUNTIME_CONFIG_SCHEMA_VERSION = 2

_REDACTED_QMT_ACCOUNT_PATTERN = re.compile(r"^qmtacct-v1-[0-9a-f]{24}$")


class BrokerProvider(str, Enum):
    NONE = "none"
    QMT_BUILTIN_BRIDGE = "qmt_builtin_bridge"


class QmtProviderMode(str, Enum):
    """QMT-side mode allowed by this read-only bridge revision."""

    SIMULATION_SIGNAL = "simulation_signal"


def _positive_finite_number(value: Any, *, name: str) -> float:
    if isinstance(value, bool):
        raise ValueError(f"{name} must be a positive finite number")
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError) as exc:
        raise ValueError(f"{name} must be a positive finite number") from exc
    if not math.isfinite(number) or number <= 0:
        raise ValueError(f"{name} must be a positive finite number")
    return number


def _optional_environment_text(name: str, default: str | None = None) -> str | None:
    value = os.environ.get(name)
    if value is None:
        return default
    normalized = value.strip()
    return normalized or None


@dataclass(frozen=True)
class QmtBuiltinBridgeConfig:
    """Operational settings for the local, read-only QMT filesystem bridge."""

    bridge_root: Path | None = None
    max_snapshot_age_seconds: float = 120.0
    expected_account_type: str | None = "STOCK"
    expected_redacted_account_id: str | None = None
    polling_interval_seconds: float = 5.0
    heartbeat_interval_seconds: float = 30.0
    provider_mode: QmtProviderMode = QmtProviderMode.SIMULATION_SIGNAL

    def __post_init__(self) -> None:
        if self.bridge_root is not None and not isinstance(self.bridge_root, Path):
            if not isinstance(self.bridge_root, str) or not self.bridge_root.strip():
                raise ValueError("bridge_root must be a non-empty path when configured")
            object.__setattr__(self, "bridge_root", Path(self.bridge_root).expanduser())
        object.__setattr__(
            self,
            "max_snapshot_age_seconds",
            _positive_finite_number(self.max_snapshot_age_seconds, name="max_snapshot_age_seconds"),
        )
        object.__setattr__(
            self,
            "polling_interval_seconds",
            _positive_finite_number(self.polling_interval_seconds, name="polling_interval_seconds"),
        )
        object.__setattr__(
            self,
            "heartbeat_interval_seconds",
            _positive_finite_number(self.heartbeat_interval_seconds, name="heartbeat_interval_seconds"),
        )
        if self.heartbeat_interval_seconds < self.polling_interval_seconds:
            raise ValueError("heartbeat_interval_seconds must be at least polling_interval_seconds")
        if self.bridge_root is not None and not str(self.bridge_root).strip():
            raise ValueError("bridge_root must be a non-empty path when configured")
        if self.expected_account_type is not None:
            if not isinstance(self.expected_account_type, str):
                raise ValueError("expected_account_type must be a short non-empty value")
            account_type = self.expected_account_type.strip().upper()
            if not account_type or len(account_type) > 32:
                raise ValueError("expected_account_type must be a short non-empty value")
            object.__setattr__(self, "expected_account_type", account_type)
        if self.expected_redacted_account_id is not None and (
            not isinstance(self.expected_redacted_account_id, str)
            or not _REDACTED_QMT_ACCOUNT_PATTERN.fullmatch(self.expected_redacted_account_id)
        ):
            raise ValueError("expected_redacted_account_id must use the qmtacct-v1 redacted binding format")
        if not isinstance(self.provider_mode, QmtProviderMode):
            object.__setattr__(self, "provider_mode", QmtProviderMode(str(self.provider_mode).strip().lower()))

    @classmethod
    def from_environment(cls, *, default_bridge_root: Path | None = None) -> "QmtBuiltinBridgeConfig":
        root = _optional_environment_text("QUANTPILOT_QMT_BRIDGE_ROOT")
        return cls(
            bridge_root=Path(root).expanduser() if root is not None else default_bridge_root,
            max_snapshot_age_seconds=os.environ.get("QUANTPILOT_QMT_MAX_SNAPSHOT_AGE_SECONDS", "120"),
            expected_account_type=_optional_environment_text("QUANTPILOT_QMT_EXPECTED_ACCOUNT_TYPE", "STOCK"),
            expected_redacted_account_id=_optional_environment_text("QUANTPILOT_QMT_EXPECTED_REDACTED_ACCOUNT_ID"),
            polling_interval_seconds=os.environ.get("QUANTPILOT_QMT_POLL_INTERVAL_SECONDS", "5"),
            heartbeat_interval_seconds=os.environ.get("QUANTPILOT_QMT_HEARTBEAT_INTERVAL_SECONDS", "30"),
            provider_mode=QmtProviderMode(os.environ.get("QUANTPILOT_QMT_PROVIDER_MODE", QmtProviderMode.SIMULATION_SIGNAL.value).lower()),
        )

    def as_dict(self) -> dict[str, Any]:
        return {
            "bridge_root": str(self.bridge_root) if self.bridge_root is not None else None,
            "max_snapshot_age_seconds": self.max_snapshot_age_seconds,
            "expected_account_type": self.expected_account_type,
            "expected_redacted_account_id": self.expected_redacted_account_id,
            "polling_interval_seconds": self.polling_interval_seconds,
            "heartbeat_interval_seconds": self.heartbeat_interval_seconds,
            "provider_mode": self.provider_mode.value,
        }

    @classmethod
    def from_mapping(cls, payload: Mapping[str, Any] | None) -> "QmtBuiltinBridgeConfig":
        values = payload or {}
        root = values.get("bridge_root")
        return cls(
            bridge_root=Path(str(root)).expanduser() if root not in (None, "") else None,
            max_snapshot_age_seconds=values.get("max_snapshot_age_seconds", 120.0),
            expected_account_type=values.get("expected_account_type", "STOCK"),
            expected_redacted_account_id=values.get("expected_redacted_account_id"),
            polling_interval_seconds=values.get("polling_interval_seconds", 5.0),
            heartbeat_interval_seconds=values.get("heartbeat_interval_seconds", 30.0),
            provider_mode=QmtProviderMode(str(values.get("provider_mode", QmtProviderMode.SIMULATION_SIGNAL.value)).lower()),
        )


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
    qmt_builtin_bridge: QmtBuiltinBridgeConfig = field(default_factory=QmtBuiltinBridgeConfig)
    runtime_home: Path = field(default_factory=default_runtime_home)
    reporting_enabled: bool = True
    grafana_enabled: bool = True
    deepseek_live_calls_enabled: bool = False

    def __post_init__(self) -> None:
        if not isinstance(self.broker_provider, BrokerProvider):
            object.__setattr__(self, "broker_provider", BrokerProvider(str(self.broker_provider).strip().lower()))
        if not isinstance(self.qmt_builtin_bridge, QmtBuiltinBridgeConfig):
            raise ValueError("qmt_builtin_bridge must use QmtBuiltinBridgeConfig")
        if not isinstance(self.runtime_home, Path):
            object.__setattr__(self, "runtime_home", Path(self.runtime_home).expanduser())
        ZoneInfo(self.timezone)

    @classmethod
    def from_environment(cls) -> "RuntimeConfig":
        provider = BrokerProvider(os.environ.get("QUANTPILOT_BROKER_PROVIDER", BrokerProvider.NONE.value).lower())
        runtime_home = Path(os.environ.get("QUANTPILOT_RUNTIME_HOME", default_runtime_home()))
        return cls(
            platform=os.environ.get("QUANTPILOT_RUNTIME_PLATFORM", platform.system().lower()),
            timezone=os.environ.get("QUANTPILOT_TIMEZONE", "Asia/Shanghai"),
            broker_provider=provider,
            qmt_builtin_bridge=QmtBuiltinBridgeConfig.from_environment(default_bridge_root=runtime_home / "qmt_builtin_bridge"),
            runtime_home=runtime_home,
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
            "qmt_builtin_bridge": self.qmt_builtin_bridge.as_dict(),
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
        schema_version = payload.get("schema_version", RUNTIME_CONFIG_SCHEMA_VERSION)
        if isinstance(schema_version, bool) or not isinstance(schema_version, int) or schema_version != RUNTIME_CONFIG_SCHEMA_VERSION:
            raise ValueError("runtime configuration schema version is unsupported")
        runtime_home = Path(str(payload.get("runtime_home", default_runtime_home())))
        bridge_payload = payload.get("qmt_builtin_bridge")
        if not isinstance(bridge_payload, Mapping):
            bridge_payload = {"bridge_root": str(runtime_home / "qmt_builtin_bridge")}
        return cls(
            platform=str(payload.get("platform", platform.system().lower())),
            timezone=str(payload.get("timezone", "Asia/Shanghai")),
            broker_provider=BrokerProvider(str(payload.get("broker_provider", BrokerProvider.NONE.value))),
            qmt_builtin_bridge=QmtBuiltinBridgeConfig.from_mapping(bridge_payload),
            runtime_home=runtime_home,
            reporting_enabled=bool(payload.get("reporting_enabled", True)),
            grafana_enabled=bool(payload.get("grafana_enabled", True)),
            deepseek_live_calls_enabled=bool(payload.get("deepseek_live_calls_enabled", False)),
        )
