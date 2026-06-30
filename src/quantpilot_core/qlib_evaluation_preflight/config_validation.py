"""Config validation helpers for R29 Qlib evaluation preflight."""

from __future__ import annotations

from datetime import datetime

from quantpilot_core.qlib_evaluation_preflight.contracts import (
    QlibBenchmarkConfig,
    QlibDatasetConfig,
    QlibEvaluationConfig,
    QlibEvaluationMode,
    QlibEvaluationRiskFlag,
    QlibRiskSeverity,
)


SUPPORTED_FREQUENCIES = frozenset({"day", "1d", "daily"})
SUSPICIOUS_PROVIDER_URIS = frozenset({"", "todo", "none", "null", "na", "n/a"})
A_SHARE_MARKET_TOKENS = frozenset({"cn", "china", "a_share", "ashare", "cn_a_share", "china_a_share"})


def validate_qlib_dataset_config(
    dataset: QlibDatasetConfig,
) -> tuple[QlibEvaluationRiskFlag, ...]:
    """Validate Qlib dataset config shape without touching files or network."""

    flags: list[QlibEvaluationRiskFlag] = []
    provider_uri = dataset.provider_uri.strip()
    if provider_uri.lower() in SUSPICIOUS_PROVIDER_URIS:
        flags.append(_critical("dataset_provider_uri_invalid", "Dataset provider_uri must be explicit and non-placeholder."))
    if not dataset.region.strip():
        flags.append(_critical("dataset_region_missing", "Dataset region must be non-empty."))
    if not dataset.market.strip():
        flags.append(_critical("dataset_market_missing", "Dataset market must be non-empty."))
    elif not _is_a_share_market(dataset.market):
        flags.append(_warning("dataset_market_manual_review", "Dataset market is not clearly A-share/CN oriented."))
    if not dataset.instrument_universe:
        flags.append(_critical("dataset_instrument_universe_empty", "Instrument universe must not be empty."))
    duplicate_instruments = _duplicates(dataset.instrument_universe)
    if duplicate_instruments:
        flags.append(_critical("dataset_duplicate_instruments", "Duplicate instruments are not allowed."))
    if not _strict_iso_date(dataset.start_date):
        flags.append(_critical("dataset_start_date_invalid", "Dataset start_date must be YYYY-MM-DD."))
    if not _strict_iso_date(dataset.end_date):
        flags.append(_critical("dataset_end_date_invalid", "Dataset end_date must be YYYY-MM-DD."))
    if _strict_iso_date(dataset.start_date) and _strict_iso_date(dataset.end_date):
        if dataset.start_date > dataset.end_date:
            flags.append(_critical("dataset_date_range_invalid", "Dataset start_date must be <= end_date."))
    if not dataset.calendar_name.strip():
        flags.append(_critical("dataset_calendar_name_missing", "Dataset calendar_name must be non-empty."))
    if not _has_evidence(dataset.evidence_refs):
        flags.append(_critical("dataset_evidence_missing", "Dataset evidence_refs must be non-empty."))
    return tuple(flags)


def validate_qlib_benchmark_config(
    benchmark: QlibBenchmarkConfig,
    market: str = "",
) -> tuple[QlibEvaluationRiskFlag, ...]:
    """Validate benchmark config shape without creating a runtime config."""

    flags: list[QlibEvaluationRiskFlag] = []
    if not benchmark.benchmark_symbol.strip():
        flags.append(_critical("benchmark_symbol_missing", "Benchmark symbol must be non-empty."))
    elif _is_a_share_market(market) and not _is_cn_compatible_symbol(benchmark.benchmark_symbol):
        flags.append(_warning("benchmark_symbol_manual_review", "Benchmark symbol is not clearly compatible with A-share/CN market."))
    if benchmark.frequency not in SUPPORTED_FREQUENCIES:
        flags.append(_critical("benchmark_frequency_invalid", "Benchmark frequency must be one of day, 1d, daily."))
    if not benchmark.cost_model.strip():
        flags.append(_critical("benchmark_cost_model_missing", "Benchmark cost_model must be non-empty."))
    if not 0 <= benchmark.slippage_bps <= 100:
        flags.append(_critical("benchmark_slippage_bps_invalid", "Benchmark slippage_bps must be in [0, 100]."))
    if not 0 <= benchmark.commission_rate <= 0.01:
        flags.append(_critical("benchmark_commission_rate_invalid", "Benchmark commission_rate must be in [0, 0.01]."))
    if not 0 <= benchmark.stamp_tax_rate <= 0.01:
        flags.append(_critical("benchmark_stamp_tax_rate_invalid", "Benchmark stamp_tax_rate must be in [0, 0.01]."))
    if not _has_evidence(benchmark.evidence_refs):
        flags.append(_critical("benchmark_evidence_missing", "Benchmark evidence_refs must be non-empty."))
    return tuple(flags)


def validate_qlib_evaluation_config(
    config: QlibEvaluationConfig,
) -> tuple[QlibEvaluationRiskFlag, ...]:
    """Validate the full R29 Qlib evaluation preflight config."""

    flags: list[QlibEvaluationRiskFlag] = []
    if not config.config_id.strip():
        flags.append(_critical("config_id_missing", "Config id must be non-empty."))
    if config.mode not in {mode.value for mode in QlibEvaluationMode}:
        flags.append(_critical("config_mode_invalid", "Qlib evaluation mode is not supported."))
    if not _has_evidence(config.evidence_refs):
        flags.append(_critical("config_evidence_missing", "Config evidence_refs must be non-empty."))
    if config.allow_runtime_execution:
        flags.append(_critical("runtime_execution_requested", "Qlib runtime execution must remain disabled in R29."))
    if not config.pit_required:
        flags.append(_critical("pit_required_false", "PIT/no-lookahead validation must be required."))
    flags.extend(validate_qlib_dataset_config(config.dataset))
    flags.extend(validate_qlib_benchmark_config(config.benchmark, market=config.dataset.market))
    flags.extend(_validate_factor_metric_result(config.factor_metric_result))
    return tuple(flags)


def _validate_factor_metric_result(
    factor_metric_result: object,
) -> tuple[QlibEvaluationRiskFlag, ...]:
    if factor_metric_result is None:
        return (_critical("factor_metric_result_missing", "R28 factor metric result is required."),)

    flags: list[QlibEvaluationRiskFlag] = []
    decision = getattr(factor_metric_result, "decision", None)
    if decision == "fail":
        flags.append(_critical("factor_metric_result_failed", "R28 factor metric result FAIL blocks Qlib evaluation preflight."))
    elif decision == "manual_review":
        flags.append(_warning("factor_metric_result_manual_review", "R28 factor metric result requires manual review."))
    elif decision != "pass":
        flags.append(_critical("factor_metric_result_decision_invalid", "R28 factor metric result decision must be pass, manual_review, or fail."))

    if getattr(factor_metric_result, "failed_metrics", ()):
        flags.append(_critical("factor_metric_failed_metrics_present", "R28 factor metric failed_metrics must be empty."))
    if getattr(factor_metric_result, "warning_metrics", ()):
        flags.append(_warning("factor_metric_warning_metrics_present", "R28 factor metric warning_metrics require manual review."))
    if any("non_pit" in str(ref).lower() or "lookahead" in str(ref).lower() for ref in getattr(factor_metric_result, "evidence_refs", ())):
        flags.append(_critical("factor_metric_pit_evidence_failed", "Factor metric evidence indicates non-PIT or lookahead risk."))
    return tuple(flags)


def _is_a_share_market(value: str) -> bool:
    normalized = value.strip().lower().replace("-", "_")
    return normalized in A_SHARE_MARKET_TOKENS


def _is_cn_compatible_symbol(symbol: str) -> bool:
    normalized = symbol.strip().lower()
    return (
        normalized.startswith(("sh", "sz", "bj"))
        or normalized.endswith((".sh", ".sz", ".bj"))
        or normalized.endswith((".ss",))
        or normalized in {"csi300", "000300", "000300.sh", "sh000300"}
    )


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


def _duplicates(values: tuple[str, ...]) -> set[str]:
    seen: set[str] = set()
    duplicates: set[str] = set()
    for value in values:
        normalized = value.strip()
        if normalized in seen:
            duplicates.add(normalized)
        seen.add(normalized)
    return duplicates


def _critical(code: str, message: str) -> QlibEvaluationRiskFlag:
    return QlibEvaluationRiskFlag(code=code, severity=QlibRiskSeverity.CRITICAL.value, message=message)


def _warning(code: str, message: str) -> QlibEvaluationRiskFlag:
    return QlibEvaluationRiskFlag(code=code, severity=QlibRiskSeverity.MEDIUM.value, message=message)
