"""Market Reality Sandbox contract layer.

R2 exposes contracts and validation helpers only. External engines and
libraries remain adapters, benchmarks, or future integration candidates.
"""

from quantpilot_core.market_reality.contracts import (
    MATURE_EXTERNAL_BOUNDARY_NAMES,
    AccountConstraint,
    CapitalConstraint,
    CostModel,
    DataLatencyAssumption,
    ExecutionConstraint,
    FillSimulation,
    InstrumentTradingProfile,
    OrderDraft,
    OrderSide,
    ProviderFailureAssumption,
    SandboxRejectionReason,
    SandboxResult,
    SandboxScenario,
    SandboxValidationIssue,
    SlippageModel,
    TradingCalendarAssumption,
    ValidationSeverity,
)
from quantpilot_core.market_reality.validation import (
    rejection_reasons,
    validate_account_constraint,
    validate_capital_constraint,
    validate_cost_model,
    validate_fill_simulation,
    validate_instrument_profile,
    validate_order_draft,
    validate_sandbox_result,
    validate_sandbox_scenario,
    validate_slippage_model,
)

__all__ = [
    "MATURE_EXTERNAL_BOUNDARY_NAMES",
    "AccountConstraint",
    "CapitalConstraint",
    "CostModel",
    "DataLatencyAssumption",
    "ExecutionConstraint",
    "FillSimulation",
    "InstrumentTradingProfile",
    "OrderDraft",
    "OrderSide",
    "ProviderFailureAssumption",
    "SandboxRejectionReason",
    "SandboxResult",
    "SandboxScenario",
    "SandboxValidationIssue",
    "SlippageModel",
    "TradingCalendarAssumption",
    "ValidationSeverity",
    "rejection_reasons",
    "validate_account_constraint",
    "validate_capital_constraint",
    "validate_cost_model",
    "validate_fill_simulation",
    "validate_instrument_profile",
    "validate_order_draft",
    "validate_sandbox_result",
    "validate_sandbox_scenario",
    "validate_slippage_model",
]
