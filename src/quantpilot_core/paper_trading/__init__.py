"""Deterministic paper trading loop for advisory order intents."""

from quantpilot_core.paper_trading.adapters import (
    BacktraderOrderIntentAdapter,
    DisabledRuntimeAdapterMapping,
    RQAlphaPaperIntentAdapter,
    VectorbtOrderIntentAdapter,
    VectorbtOrderIntentMapping,
)
from quantpilot_core.paper_trading.contracts import (
    PaperAccount,
    PaperFillCostAssumptions,
    PaperFillSimulationResult,
    PaperLoopLearningDeskOutput,
    PaperPerformanceMetrics,
    PaperTrade,
    PaperTradingLoopResult,
    RejectedPaperFill,
)
from quantpilot_core.paper_trading.loop import (
    PaperTradingLoop,
    account_symbol_pnl_breakdown,
    run_paper_trading_loop,
)
from quantpilot_core.paper_trading.simulator import PaperFillSimulator

__all__ = [
    "BacktraderOrderIntentAdapter",
    "DisabledRuntimeAdapterMapping",
    "PaperAccount",
    "PaperFillCostAssumptions",
    "PaperFillSimulationResult",
    "PaperFillSimulator",
    "PaperLoopLearningDeskOutput",
    "PaperPerformanceMetrics",
    "PaperTrade",
    "PaperTradingLoop",
    "PaperTradingLoopResult",
    "RejectedPaperFill",
    "RQAlphaPaperIntentAdapter",
    "VectorbtOrderIntentAdapter",
    "VectorbtOrderIntentMapping",
    "account_symbol_pnl_breakdown",
    "run_paper_trading_loop",
]
