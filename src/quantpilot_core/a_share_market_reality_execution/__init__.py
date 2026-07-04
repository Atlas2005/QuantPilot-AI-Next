"""A-share market-reality execution adapter for existing paper evaluation paths."""

from quantpilot_core.a_share_market_reality_execution.execution import (
    AShareExecutionAccountState,
    AShareExecutionConfig,
    AShareExecutionOutcome,
    AShareExecutionRealityResult,
    SettlementLot,
    execute_a_share_reality_proposal,
    summarize_metadata_availability,
    summarize_execution_outcomes,
    summarize_rule_coverage,
)

__all__ = [
    "AShareExecutionAccountState",
    "AShareExecutionConfig",
    "AShareExecutionOutcome",
    "AShareExecutionRealityResult",
    "SettlementLot",
    "execute_a_share_reality_proposal",
    "summarize_metadata_availability",
    "summarize_execution_outcomes",
    "summarize_rule_coverage",
]
