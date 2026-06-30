"""Optional manual runner interface for P31 provider stability trials."""

from __future__ import annotations

import importlib
from typing import Callable

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
from quantpilot_core.real_data_stability_trial.report import run_real_data_stability_trial


def run_optional_manual_provider_trial(
    universe: AshareSampleUniverse,
    config: ProviderTrialConfig,
    *,
    allow_network: bool = False,
    importer: Callable[[str], object] | None = None,
    row_loader: Callable[[AshareSampleUniverse, ProviderTrialConfig], tuple[ProviderDataRow, ...]] | None = None,
) -> RealDataStabilityTrialResult:
    """Run an explicitly enabled manual provider trial.

    Without allow_network=True, this returns MANUAL_REVIEW and does not import
    provider packages. When enabled, callers must supply row_loader for the
    actual provider access boundary.
    """

    if not allow_network:
        return _manual_review_result(universe, config, "manual_network_trial_not_enabled")

    package_importer = importer or importlib.import_module
    package_name = _provider_package_name(config.provider_name)
    if package_name:
        try:
            package_importer(package_name)
        except ImportError:
            return _manual_review_result(universe, config, "provider_package_unavailable")

    if row_loader is None:
        return _manual_review_result(universe, config, "manual_row_loader_required")
    rows = row_loader(universe, config)
    return run_real_data_stability_trial(universe, (config,), {config.provider_name: rows})


def _provider_package_name(provider_name: str) -> str:
    if provider_name == "akshare":
        return "akshare"
    if provider_name == "baostock":
        return "baostock"
    return ""


def _manual_review_result(
    universe: AshareSampleUniverse,
    config: ProviderTrialConfig,
    reason: str,
) -> RealDataStabilityTrialResult:
    risk_flag = RealDataTrialRiskFlag(
        code=reason,
        severity=RealDataTrialSeverity.MEDIUM.value,
        message="Manual provider trial requires explicit operator action.",
    )
    check = ProviderTrialCheckRecord(
        name=f"{config.provider_name}:manual_runner",
        provider_name=config.provider_name,
        status=RealDataTrialCheckStatus.WARNING.value,
        reason=reason,
        evidence_refs=config.evidence_refs,
    )
    report = ProviderStabilityReport(
        provider_name=config.provider_name,
        decision=RealDataTrialDecision.MANUAL_REVIEW.value,
        rows_seen=0,
        symbols_seen=(),
        trading_dates_seen=(),
        checks=(check,),
        risk_flags=(risk_flag,),
    )
    return RealDataStabilityTrialResult(
        ok=False,
        decision=RealDataTrialDecision.MANUAL_REVIEW.value,
        reason=reason,
        universe_id=universe.universe_id,
        provider_reports=(report,),
        risk_flags=(risk_flag,),
        passed_checks=(),
        warning_checks=(check.name,),
        failed_checks=(),
    )
