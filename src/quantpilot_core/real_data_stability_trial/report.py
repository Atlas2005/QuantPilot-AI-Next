"""Report builders for P31 real data stability trial."""

from __future__ import annotations

from quantpilot_core.real_data_stability_trial.contracts import (
    AshareSampleUniverse,
    ProviderDataRow,
    ProviderStabilityReport,
    ProviderTrialCheckRecord,
    ProviderTrialConfig,
    RealDataStabilityTrialResult,
    RealDataTrialCheckStatus,
    RealDataTrialDecision,
    RealDataTrialRiskFlag,
    RealDataTrialSeverity,
)
from quantpilot_core.real_data_stability_trial.validation import (
    validate_provider_rows,
    validate_provider_trial_config,
    validate_sample_universe,
)


def build_provider_stability_report(
    provider_name: str,
    rows: tuple[ProviderDataRow, ...],
    universe: AshareSampleUniverse,
    config: ProviderTrialConfig,
) -> ProviderStabilityReport:
    """Build a single-provider stability report from already supplied rows."""

    risk_flags = (
        validate_provider_trial_config(config)
        + validate_provider_rows(rows, universe, config)
    )
    checks = (
        _check_from_flags("provider_config", provider_name, _provider_config_flags(risk_flags), config.evidence_refs),
        _required_field_coverage_check(provider_name, rows, config),
        _symbol_coverage_check(provider_name, rows, universe),
        _date_coverage_check(provider_name, rows, universe),
        _duplicate_row_check(provider_name, risk_flags, config.evidence_refs),
        _missing_row_ratio_check(provider_name, rows, universe),
        _numeric_sanity_check(provider_name, risk_flags, config.evidence_refs),
    )
    decision = _decision_from_checks(checks, risk_flags)
    return ProviderStabilityReport(
        provider_name=provider_name,
        decision=decision,
        rows_seen=len(rows),
        symbols_seen=tuple(sorted({row.symbol for row in rows})),
        trading_dates_seen=tuple(sorted({row.trading_date for row in rows})),
        checks=checks,
        risk_flags=risk_flags,
    )


def run_real_data_stability_trial(
    universe: AshareSampleUniverse,
    provider_configs: tuple[ProviderTrialConfig, ...],
    rows_by_provider: dict[str, tuple[ProviderDataRow, ...]],
) -> RealDataStabilityTrialResult:
    """Run a deterministic stability trial over supplied provider rows."""

    universe_flags = validate_sample_universe(universe)
    provider_reports = tuple(
        build_provider_stability_report(
            config.provider_name,
            tuple(rows_by_provider.get(config.provider_name, ())),
            universe,
            config,
        )
        for config in provider_configs
    )
    fallback_checks = _fallback_compatibility_checks(provider_reports, universe.evidence_refs)
    all_checks = tuple(check for report in provider_reports for check in report.checks) + fallback_checks
    risk_flags = universe_flags + tuple(flag for report in provider_reports for flag in report.risk_flags)
    if universe_flags:
        all_checks = (
            _check_from_flags("sample_universe", "all", universe_flags, universe.evidence_refs),
            *all_checks,
        )
    passed_checks = tuple(check.name for check in all_checks if check.status == RealDataTrialCheckStatus.PASS.value)
    warning_checks = tuple(check.name for check in all_checks if check.status == RealDataTrialCheckStatus.WARNING.value)
    failed_checks = tuple(check.name for check in all_checks if check.status == RealDataTrialCheckStatus.FAIL.value)

    if any(flag.severity == RealDataTrialSeverity.CRITICAL.value for flag in risk_flags) or failed_checks:
        decision = RealDataTrialDecision.UNSTABLE.value
        reason = "critical_risk_flags" if risk_flags else "failed_checks"
    elif warning_checks:
        decision = RealDataTrialDecision.MANUAL_REVIEW.value
        reason = "warning_checks"
    else:
        decision = RealDataTrialDecision.STABLE.value
        reason = "stable"

    return RealDataStabilityTrialResult(
        ok=decision == RealDataTrialDecision.STABLE.value,
        decision=decision,
        reason=reason,
        universe_id=universe.universe_id,
        provider_reports=provider_reports,
        risk_flags=risk_flags,
        passed_checks=passed_checks,
        warning_checks=warning_checks,
        failed_checks=failed_checks,
    )


def _required_field_coverage_check(
    provider_name: str,
    rows: tuple[ProviderDataRow, ...],
    config: ProviderTrialConfig,
) -> ProviderTrialCheckRecord:
    missing_count = sum(
        1 for row in rows if any(field not in row.fields for field in config.required_fields)
    )
    status = RealDataTrialCheckStatus.FAIL.value if missing_count else RealDataTrialCheckStatus.PASS.value
    return _check("required_field_coverage", provider_name, status, "required_fields_missing" if missing_count else "passed", config.evidence_refs)


def _symbol_coverage_check(
    provider_name: str,
    rows: tuple[ProviderDataRow, ...],
    universe: AshareSampleUniverse,
) -> ProviderTrialCheckRecord:
    seen = {row.symbol for row in rows}
    missing = tuple(symbol for symbol in universe.symbols if symbol not in seen)
    status = RealDataTrialCheckStatus.WARNING.value if missing else RealDataTrialCheckStatus.PASS.value
    reason = "symbol_coverage_incomplete" if missing else "passed"
    return _check("symbol_coverage", provider_name, status, reason, universe.evidence_refs)


def _date_coverage_check(
    provider_name: str,
    rows: tuple[ProviderDataRow, ...],
    universe: AshareSampleUniverse,
) -> ProviderTrialCheckRecord:
    dates_seen = {row.trading_date for row in rows}
    expected = universe.expected_trading_days
    status = RealDataTrialCheckStatus.WARNING.value if expected is not None and len(dates_seen) < expected else RealDataTrialCheckStatus.PASS.value
    reason = "date_coverage_below_expected" if status == RealDataTrialCheckStatus.WARNING.value else "passed"
    return _check("date_coverage", provider_name, status, reason, universe.evidence_refs)


def _duplicate_row_check(
    provider_name: str,
    risk_flags: tuple[RealDataTrialRiskFlag, ...],
    evidence_refs: tuple[str, ...],
) -> ProviderTrialCheckRecord:
    duplicate_flags = tuple(flag for flag in risk_flags if "duplicate_provider_symbol_date" in flag.code)
    return _check_from_flags("duplicate_row_check", provider_name, duplicate_flags, evidence_refs)


def _missing_row_ratio_check(
    provider_name: str,
    rows: tuple[ProviderDataRow, ...],
    universe: AshareSampleUniverse,
) -> ProviderTrialCheckRecord:
    if universe.expected_trading_days is None:
        return _check("missing_row_ratio", provider_name, RealDataTrialCheckStatus.PASS.value, "not_applicable", universe.evidence_refs)
    expected_rows = len(universe.symbols) * universe.expected_trading_days
    missing_ratio = 1.0 if expected_rows == 0 else max(expected_rows - len(rows), 0) / expected_rows
    status = RealDataTrialCheckStatus.WARNING.value if missing_ratio > 0 else RealDataTrialCheckStatus.PASS.value
    reason = f"missing_row_ratio:{missing_ratio:.4f}" if missing_ratio > 0 else "passed"
    return _check("missing_row_ratio", provider_name, status, reason, universe.evidence_refs)


def _numeric_sanity_check(
    provider_name: str,
    risk_flags: tuple[RealDataTrialRiskFlag, ...],
    evidence_refs: tuple[str, ...],
) -> ProviderTrialCheckRecord:
    numeric_flags = tuple(
        flag
        for flag in risk_flags
        if any(token in flag.code for token in ("not_finite", "high_lower_than_low", "outside_high_low", "volume_negative"))
    )
    return _check_from_flags("numeric_sanity", provider_name, numeric_flags, evidence_refs)


def _fallback_compatibility_checks(
    provider_reports: tuple[ProviderStabilityReport, ...],
    evidence_refs: tuple[str, ...],
) -> tuple[ProviderTrialCheckRecord, ...]:
    if len(provider_reports) <= 1:
        return ()
    first_symbols = set(provider_reports[0].symbols_seen)
    first_dates = set(provider_reports[0].trading_dates_seen)
    mismatch = any(
        set(report.symbols_seen) != first_symbols or set(report.trading_dates_seen) != first_dates
        for report in provider_reports[1:]
    )
    return (
        _check(
            "fallback_compatibility",
            "all",
            RealDataTrialCheckStatus.WARNING.value if mismatch else RealDataTrialCheckStatus.PASS.value,
            "provider_symbols_or_dates_differ" if mismatch else "passed",
            evidence_refs,
        ),
    )


def _provider_config_flags(
    risk_flags: tuple[RealDataTrialRiskFlag, ...],
) -> tuple[RealDataTrialRiskFlag, ...]:
    return tuple(flag for flag in risk_flags if flag.code.startswith("provider_"))


def _decision_from_checks(
    checks: tuple[ProviderTrialCheckRecord, ...],
    risk_flags: tuple[RealDataTrialRiskFlag, ...],
) -> str:
    if any(flag.severity == RealDataTrialSeverity.CRITICAL.value for flag in risk_flags) or any(check.status == RealDataTrialCheckStatus.FAIL.value for check in checks):
        return RealDataTrialDecision.UNSTABLE.value
    if any(check.status == RealDataTrialCheckStatus.WARNING.value for check in checks):
        return RealDataTrialDecision.MANUAL_REVIEW.value
    return RealDataTrialDecision.STABLE.value


def _check_from_flags(
    name: str,
    provider_name: str,
    flags: tuple[RealDataTrialRiskFlag, ...],
    evidence_refs: tuple[str, ...],
) -> ProviderTrialCheckRecord:
    if any(flag.severity == RealDataTrialSeverity.CRITICAL.value for flag in flags):
        status = RealDataTrialCheckStatus.FAIL.value
    elif flags:
        status = RealDataTrialCheckStatus.WARNING.value
    else:
        status = RealDataTrialCheckStatus.PASS.value
    return _check(name, provider_name, status, ";".join(flag.code for flag in flags) if flags else "passed", evidence_refs)


def _check(
    name: str,
    provider_name: str,
    status: str,
    reason: str,
    evidence_refs: tuple[str, ...],
) -> ProviderTrialCheckRecord:
    return ProviderTrialCheckRecord(
        name=f"{provider_name}:{name}",
        provider_name=provider_name,
        status=status,
        reason=reason,
        evidence_refs=evidence_refs,
    )
