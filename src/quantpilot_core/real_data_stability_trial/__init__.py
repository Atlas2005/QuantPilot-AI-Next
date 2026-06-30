"""P31 real data stability trial."""

from quantpilot_core.real_data_stability_trial.contracts import (
    AshareSampleUniverse,
    ExpectedDataType,
    ProviderDataRow,
    ProviderStabilityReport,
    ProviderTrialCheckRecord,
    ProviderTrialConfig,
    RealDataProviderName,
    RealDataStabilityTrialResult,
    RealDataTrialCheckStatus,
    RealDataTrialDecision,
    RealDataTrialRiskFlag,
    RealDataTrialSeverity,
)
from quantpilot_core.real_data_stability_trial.manual_runner import (
    run_optional_manual_provider_trial,
)
from quantpilot_core.real_data_stability_trial.report import (
    build_provider_stability_report,
    run_real_data_stability_trial,
)
from quantpilot_core.real_data_stability_trial.validation import (
    validate_provider_rows,
    validate_provider_trial_config,
    validate_sample_universe,
)

__all__ = [
    "AshareSampleUniverse",
    "ExpectedDataType",
    "ProviderDataRow",
    "ProviderStabilityReport",
    "ProviderTrialCheckRecord",
    "ProviderTrialConfig",
    "RealDataProviderName",
    "RealDataStabilityTrialResult",
    "RealDataTrialCheckStatus",
    "RealDataTrialDecision",
    "RealDataTrialRiskFlag",
    "RealDataTrialSeverity",
    "build_provider_stability_report",
    "run_optional_manual_provider_trial",
    "run_real_data_stability_trial",
    "validate_provider_rows",
    "validate_provider_trial_config",
    "validate_sample_universe",
]
