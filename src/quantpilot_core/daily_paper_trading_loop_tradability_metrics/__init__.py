"""P36 daily paper trading loop with tradability metrics."""

from quantpilot_core.daily_paper_trading_loop_tradability_metrics.contracts import (
    DailyAdjustmentRecommendation,
    DailyPaperTradingDayResult,
    DailyPaperTradingInput,
    DailyPaperTradingLoopReport,
    DailyTradabilityMetrics,
    ZeroTradeDiagnosisSummary,
)
from quantpilot_core.daily_paper_trading_loop_tradability_metrics.loop import (
    run_daily_paper_trading_loop,
)
from quantpilot_core.daily_paper_trading_loop_tradability_metrics.metrics import (
    calculate_daily_tradability_metrics,
    summarize_zero_trade_diagnosis,
)
from quantpilot_core.daily_paper_trading_loop_tradability_metrics.report import (
    build_daily_paper_trading_loop_report,
)

__all__ = [
    "DailyAdjustmentRecommendation",
    "DailyPaperTradingDayResult",
    "DailyPaperTradingInput",
    "DailyPaperTradingLoopReport",
    "DailyTradabilityMetrics",
    "ZeroTradeDiagnosisSummary",
    "build_daily_paper_trading_loop_report",
    "calculate_daily_tradability_metrics",
    "run_daily_paper_trading_loop",
    "summarize_zero_trade_diagnosis",
]
