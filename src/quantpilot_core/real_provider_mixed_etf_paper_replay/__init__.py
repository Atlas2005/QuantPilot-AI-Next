"""Legacy P39 provider replay path kept for reference compatibility."""

from quantpilot_core.real_provider_mixed_etf_paper_replay.comparison import (
    compare_provider_replay_to_p38_baseline,
    evaluate_provider_capital_path_suitability,
)
from quantpilot_core.real_provider_mixed_etf_paper_replay.contracts import (
    ProviderMixedEtfReplayReport,
    ProviderMixedUniverseSample,
    ProviderReplayResult,
    ProviderSampleSourceType,
    ProviderSampleValidationResult,
    RealProviderReplayInput,
)
from quantpilot_core.real_provider_mixed_etf_paper_replay.report import (
    build_provider_mixed_etf_replay_report,
)
from quantpilot_core.real_provider_mixed_etf_paper_replay.replay import (
    replay_provider_mixed_etf_sample,
)
from quantpilot_core.real_provider_mixed_etf_paper_replay.sample_bridge import (
    validate_provider_mixed_universe_sample,
)

__all__ = [
    "ProviderMixedEtfReplayReport",
    "ProviderMixedUniverseSample",
    "ProviderReplayResult",
    "ProviderSampleSourceType",
    "ProviderSampleValidationResult",
    "RealProviderReplayInput",
    "build_provider_mixed_etf_replay_report",
    "compare_provider_replay_to_p38_baseline",
    "evaluate_provider_capital_path_suitability",
    "replay_provider_mixed_etf_sample",
    "validate_provider_mixed_universe_sample",
]
