from __future__ import annotations

import json
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any


class ReadinessStatus(str, Enum):
    not_ready = "not_ready"
    partially_ready = "partially_ready"
    ready_for_manual_probe = "ready_for_manual_probe"
    ready_for_larger_fixture = "ready_for_larger_fixture"
    rejected = "rejected"


class ReadinessSeverity(str, Enum):
    info = "info"
    warning = "warning"
    blocking = "blocking"


class ReadinessCategory(str, Enum):
    data_source = "data_source"
    license = "license"
    schema = "schema"
    adjustment = "adjustment"
    sample_size = "sample_size"
    time_split = "time_split"
    market_rules = "market_rules"
    transaction_cost = "transaction_cost"
    storage = "storage"
    reproducibility = "reproducibility"
    compliance = "compliance"
    alpha_validation = "alpha_validation"
    unknown = "unknown"


@dataclass(frozen=True)
class ReadinessCheck:
    code: str
    category: ReadinessCategory
    severity: ReadinessSeverity
    description: str
    required_before_real_alpha: bool
    required_before_strategy_tournament: bool
    notes: str


@dataclass(frozen=True)
class ReadinessCheckResult:
    code: str
    passed: bool
    severity: ReadinessSeverity
    message: str


@dataclass(frozen=True)
class RealDataReadinessReport:
    gate_name: str
    status: ReadinessStatus
    alpha_claim_allowed: bool
    trading_ready: bool
    checks: list[ReadinessCheckResult]
    blocking_count: int
    warning_count: int
    recommended_next_action: str


REQUIRED_GATE_FIELDS = {
    "gate_name",
    "gate_version",
    "phase",
    "alpha_claim_allowed",
    "trading_ready",
    "strategy_tournament_allowed",
    "external_provider_integration_allowed",
    "real_data_fetch_allowed_in_this_phase",
    "approved_data_sources",
    "candidate_data_sources",
    "deferred_storage_tools",
    "deferred_quality_tools",
    "deferred_analytics_tools",
    "checks",
}

REQUIRED_CHECK_FIELDS = {
    "code",
    "category",
    "severity",
    "description",
    "passed",
    "required_before_real_alpha",
    "required_before_strategy_tournament",
    "notes",
}


def load_readiness_gate(path: str | Path) -> dict[str, Any]:
    with Path(path).open("r", encoding="utf-8") as handle:
        data = json.load(handle)
    if not isinstance(data, dict):
        raise ValueError("Readiness gate must be a JSON object.")
    return data


def validate_readiness_gate(gate: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    missing = sorted(REQUIRED_GATE_FIELDS - set(gate))
    for field in missing:
        errors.append(f"missing required field: {field}")

    if gate.get("alpha_claim_allowed") is not False:
        errors.append("alpha_claim_allowed must be false in Phase 7E")
    if gate.get("trading_ready") is not False:
        errors.append("trading_ready must be false in Phase 7E")
    if gate.get("strategy_tournament_allowed") is not False:
        errors.append("strategy_tournament_allowed must be false in Phase 7E")
    if gate.get("real_data_fetch_allowed_in_this_phase") is not False:
        errors.append("real_data_fetch_allowed_in_this_phase must be false")
    if gate.get("external_provider_integration_allowed") is not False:
        errors.append("external_provider_integration_allowed must be false")
    if gate.get("approved_data_sources") != []:
        errors.append("approved_data_sources must be empty in Phase 7E")

    checks = gate.get("checks", [])
    if not isinstance(checks, list) or not checks:
        errors.append("checks must be a non-empty list")
        return errors

    seen_codes: set[str] = set()
    for check in checks:
        code = str(check.get("code", ""))
        if code in seen_codes:
            errors.append(f"duplicate readiness check code: {code}")
        seen_codes.add(code)

        missing_check_fields = sorted(REQUIRED_CHECK_FIELDS - set(check))
        for field in missing_check_fields:
            errors.append(f"{code}: missing required field: {field}")

        try:
            ReadinessCategory(check.get("category"))
        except ValueError:
            errors.append(f"{code}: invalid category")
        try:
            ReadinessSeverity(check.get("severity"))
        except ValueError:
            errors.append(f"{code}: invalid severity")

    return errors


def evaluate_readiness_gate(gate: dict[str, Any]) -> RealDataReadinessReport:
    results: list[ReadinessCheckResult] = []
    blocking_count = 0
    warning_count = 0

    for check in gate.get("checks", []):
        severity = ReadinessSeverity(check.get("severity", "warning"))
        passed = bool(check.get("passed", False))
        if not passed and severity == ReadinessSeverity.blocking:
            blocking_count += 1
        if not passed and severity == ReadinessSeverity.warning:
            warning_count += 1
        message = "passed" if passed else str(check.get("notes", "not passed"))
        results.append(
            ReadinessCheckResult(
                code=str(check.get("code", "")),
                passed=passed,
                severity=severity,
                message=message,
            )
        )

    if blocking_count > 0:
        status = ReadinessStatus.not_ready
    elif warning_count > 0:
        status = ReadinessStatus.partially_ready
    else:
        status = ReadinessStatus.ready_for_manual_probe

    return RealDataReadinessReport(
        gate_name=str(gate.get("gate_name", "")),
        status=status,
        alpha_claim_allowed=False,
        trading_ready=False,
        checks=results,
        blocking_count=blocking_count,
        warning_count=warning_count,
        recommended_next_action="resolve_blocking_readiness_checks",
    )


def summarize_readiness_report(report: RealDataReadinessReport) -> dict[str, Any]:
    return {
        "gate_name": report.gate_name,
        "status": report.status.value,
        "alpha_claim_allowed": report.alpha_claim_allowed,
        "trading_ready": report.trading_ready,
        "check_count": len(report.checks),
        "blocking_count": report.blocking_count,
        "warning_count": report.warning_count,
        "recommended_next_action": report.recommended_next_action,
    }
