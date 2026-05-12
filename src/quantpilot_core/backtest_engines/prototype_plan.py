"""Backtest prototype isolation plan types."""

from dataclasses import dataclass
from enum import Enum


class PrototypePriority(str, Enum):
    FIRST_WAVE = "first_wave"
    SECOND_WAVE = "second_wave"
    DEFERRED = "deferred"
    AVOID_FOR_NOW = "avoid_for_now"


class PrototypeRunMode(str, Enum):
    MANUAL_ONLY = "manual_only"
    DISABLED_IN_CI = "disabled_in_ci"
    ISOLATED_ENVIRONMENT_REQUIRED = "isolated_environment_required"
    METADATA_ONLY = "metadata_only"
    AVOID_FOR_NOW = "avoid_for_now"


class PrototypeRisk(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class BacktestPrototypePlan:
    """Static plan metadata for a future manual prototype."""

    engine_name: str
    priority: PrototypePriority
    run_mode: PrototypeRunMode
    requires_external_package: bool
    requires_network: bool
    requires_market_data: bool
    requires_live_trading_isolation: bool
    requires_license_review: bool
    expected_input_contract: str
    expected_output_artifact: str
    a_share_rule_fit_questions: list[str]
    prototype_success_criteria: list[str]
    risks: list[str]
    notes: str

