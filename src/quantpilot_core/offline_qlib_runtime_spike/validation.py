"""Validation helpers for P32 offline Qlib runtime spike."""

from __future__ import annotations

from datetime import datetime
from pathlib import PurePosixPath
from urllib.parse import urlparse

from quantpilot_core.offline_qlib_runtime_spike.contracts import (
    FactorMetricHandoff,
    OfflineQlibRuntimeMode,
    OfflineQlibRuntimePlan,
    OfflineQlibRuntimeRiskFlag,
    OfflineQlibRuntimeSeverity,
    QlibBenchmarkBoundary,
    QlibCalendarBoundary,
    QlibDatasetBoundary,
)


DEFAULT_REQUIRED_FACTOR_METRICS: tuple[str, ...] = (
    "ic",
    "rank_ic",
    "hit_rate",
    "turnover",
    "max_drawdown",
    "cost_aware_score",
)
SUPPORTED_FREQUENCIES = frozenset({"day", "1d", "daily"})
FORBIDDEN_SCOPE_TERMS = (
    "place_order",
    "send_order",
    "live_trade",
    "real_broker",
    "broker_sdk",
    "deepseek api call",
    "openai runtime",
    "train_live_model",
    "mutate_real_account",
)


def validate_dataset_boundary(
    dataset: QlibDatasetBoundary,
) -> tuple[OfflineQlibRuntimeRiskFlag, ...]:
    """Validate local-only dataset boundary metadata."""

    flags: list[OfflineQlibRuntimeRiskFlag] = []
    if not dataset.dataset_uri.strip():
        flags.append(_critical("dataset_uri_missing", "Dataset URI must be non-empty."))
    elif _looks_like_url(dataset.dataset_uri):
        flags.append(_critical("dataset_uri_is_url", "Dataset URI must be local-only and not a URL."))
    elif PurePosixPath(dataset.dataset_uri).is_absolute() and not dataset.dataset_uri.startswith("/"):
        flags.append(_critical("dataset_uri_invalid", "Dataset URI must be a valid local path shape."))
    if not dataset.local_only:
        flags.append(_critical("dataset_not_local_only", "Dataset boundary must be local-only."))
    if not dataset.provider_name.strip():
        flags.append(_critical("dataset_provider_missing", "Dataset provider name must be non-empty."))
    if not dataset.market.strip():
        flags.append(_critical("dataset_market_missing", "Dataset market must be non-empty."))
    if not dataset.symbols:
        flags.append(_critical("dataset_symbols_missing", "Dataset symbols must not be empty."))
    if len(set(dataset.symbols)) != len(dataset.symbols):
        flags.append(_critical("dataset_duplicate_symbols", "Dataset symbols must be unique."))
    if not _strict_iso_date(dataset.start_date):
        flags.append(_critical("dataset_start_date_invalid", "Dataset start_date must be YYYY-MM-DD."))
    if not _strict_iso_date(dataset.end_date):
        flags.append(_critical("dataset_end_date_invalid", "Dataset end_date must be YYYY-MM-DD."))
    if _strict_iso_date(dataset.start_date) and _strict_iso_date(dataset.end_date):
        if dataset.start_date > dataset.end_date:
            flags.append(_critical("dataset_date_range_invalid", "Dataset start_date must be <= end_date."))
    if not _has_evidence(dataset.evidence_refs):
        flags.append(_critical("dataset_evidence_missing", "Dataset evidence_refs must be non-empty."))
    return tuple(flags)


def validate_calendar_boundary(
    calendar: QlibCalendarBoundary,
) -> tuple[OfflineQlibRuntimeRiskFlag, ...]:
    """Validate explicit or fixture-backed calendar metadata."""

    flags: list[OfflineQlibRuntimeRiskFlag] = []
    if not calendar.calendar_name.strip():
        flags.append(_critical("calendar_name_missing", "Calendar name must be non-empty."))
    if not calendar.fixture_backed and not calendar.trading_dates:
        flags.append(_critical("calendar_missing", "Calendar must be explicitly provided or fixture-backed."))
    for index, trading_date in enumerate(calendar.trading_dates):
        if not _strict_iso_date(trading_date):
            flags.append(_critical(f"calendar_date_invalid:{index}", "Calendar trading dates must be YYYY-MM-DD."))
    if len(set(calendar.trading_dates)) != len(calendar.trading_dates):
        flags.append(_critical("calendar_duplicate_dates", "Calendar trading dates must be unique."))
    if not _has_evidence(calendar.evidence_refs):
        flags.append(_critical("calendar_evidence_missing", "Calendar evidence_refs must be non-empty."))
    return tuple(flags)


def validate_benchmark_boundary(
    benchmark: QlibBenchmarkBoundary,
) -> tuple[OfflineQlibRuntimeRiskFlag, ...]:
    """Validate benchmark boundary metadata."""

    flags: list[OfflineQlibRuntimeRiskFlag] = []
    if not benchmark.benchmark_symbol.strip():
        flags.append(_critical("benchmark_symbol_missing", "Benchmark symbol/index must be declared."))
    if benchmark.frequency not in SUPPORTED_FREQUENCIES:
        flags.append(_critical("benchmark_frequency_invalid", "Benchmark frequency must be day, 1d, or daily."))
    if not benchmark.cost_model.strip():
        flags.append(_critical("benchmark_cost_model_missing", "Benchmark cost model must be non-empty."))
    if not _has_evidence(benchmark.evidence_refs):
        flags.append(_critical("benchmark_evidence_missing", "Benchmark evidence_refs must be non-empty."))
    return tuple(flags)


def validate_factor_metric_handoff(
    handoff: FactorMetricHandoff,
) -> tuple[OfflineQlibRuntimeRiskFlag, ...]:
    """Validate R28 factor metric compatibility fields."""

    flags: list[OfflineQlibRuntimeRiskFlag] = []
    if not handoff.factor_id.strip():
        flags.append(_critical("factor_id_missing", "Factor id must be non-empty."))
    if handoff.decision == "fail":
        flags.append(_critical("factor_metric_decision_failed", "Failed factor metrics block offline runtime planning."))
    elif handoff.decision == "manual_review":
        flags.append(_warning("factor_metric_manual_review", "Manual-review factor metrics require operator review."))
    elif handoff.decision != "pass":
        flags.append(_critical("factor_metric_decision_invalid", "Factor metric decision must be pass, manual_review, or fail."))
    required_names = handoff.required_metric_names or DEFAULT_REQUIRED_FACTOR_METRICS
    missing_metrics = tuple(name for name in required_names if name not in handoff.metric_names)
    if missing_metrics:
        flags.append(_critical("factor_metric_fields_missing", "Factor metric handoff is missing required compatibility fields."))
    if not _has_evidence(handoff.evidence_refs):
        flags.append(_critical("factor_metric_evidence_missing", "Factor metric handoff evidence_refs must be non-empty."))
    return tuple(flags)


def validate_offline_runtime_plan(
    plan: OfflineQlibRuntimePlan,
) -> tuple[OfflineQlibRuntimeRiskFlag, ...]:
    """Validate an offline runtime plan without invoking any runtime."""

    flags: list[OfflineQlibRuntimeRiskFlag] = []
    if not plan.plan_id.strip():
        flags.append(_critical("plan_id_missing", "Plan id must be non-empty."))
    if plan.mode not in {mode.value for mode in OfflineQlibRuntimeMode}:
        flags.append(_critical("runtime_mode_invalid", "Runtime mode is not supported."))
    if plan.mode == OfflineQlibRuntimeMode.LIVE_RUNTIME.value:
        flags.append(_critical("live_runtime_mode_blocked", "Live runtime mode is blocked for P32."))
    if plan.allow_network:
        flags.append(_critical("network_mode_blocked", "Network mode is not allowed by default."))
    if plan.allow_runtime_execution and not plan.manual_runtime_required:
        flags.append(_critical("runtime_execution_not_manual", "Runtime execution must be manual and explicitly guarded."))
    if not plan.allow_runtime_execution and plan.mode == OfflineQlibRuntimeMode.MANUAL_RUNTIME.value:
        flags.append(_warning("manual_runtime_disabled", "Manual runtime plan is declared but execution is disabled."))
    if not _has_evidence(plan.integration_boundary_evidence):
        flags.append(_critical("integration_boundary_evidence_missing", "Integration boundary evidence must be non-empty."))
    if not _has_evidence(plan.forbidden_scope_evidence):
        flags.append(_critical("forbidden_scope_evidence_missing", "Forbidden scope evidence must be non-empty."))
    flags.extend(_forbidden_scope_flags(plan.forbidden_scope_evidence))
    if not _has_evidence(plan.evidence_refs):
        flags.append(_critical("plan_evidence_missing", "Plan evidence_refs must be non-empty."))
    flags.extend(validate_dataset_boundary(plan.dataset))
    flags.extend(validate_calendar_boundary(plan.calendar))
    flags.extend(validate_benchmark_boundary(plan.benchmark))
    flags.extend(validate_factor_metric_handoff(plan.factor_metric_handoff))
    return tuple(flags)


def _forbidden_scope_flags(
    evidence_refs: tuple[str, ...],
) -> tuple[OfflineQlibRuntimeRiskFlag, ...]:
    evidence_text = "\n".join(evidence_refs).lower()
    flags: list[OfflineQlibRuntimeRiskFlag] = []
    for term in FORBIDDEN_SCOPE_TERMS:
        if term in evidence_text:
            flags.append(_critical(f"forbidden_scope_detected:{term}", "Forbidden runtime scope evidence was detected."))
    return tuple(flags)


def _looks_like_url(value: str) -> bool:
    parsed = urlparse(value)
    return bool(parsed.scheme and parsed.netloc)


def _strict_iso_date(value: str) -> bool:
    if len(value) != 10:
        return False
    try:
        parsed = datetime.strptime(value, "%Y-%m-%d")
    except ValueError:
        return False
    return parsed.strftime("%Y-%m-%d") == value


def _has_evidence(evidence_refs: tuple[str, ...]) -> bool:
    return any(ref.strip() for ref in evidence_refs)


def _critical(code: str, message: str) -> OfflineQlibRuntimeRiskFlag:
    return OfflineQlibRuntimeRiskFlag(
        code=code,
        severity=OfflineQlibRuntimeSeverity.CRITICAL.value,
        message=message,
    )


def _warning(code: str, message: str) -> OfflineQlibRuntimeRiskFlag:
    return OfflineQlibRuntimeRiskFlag(
        code=code,
        severity=OfflineQlibRuntimeSeverity.MEDIUM.value,
        message=message,
    )
