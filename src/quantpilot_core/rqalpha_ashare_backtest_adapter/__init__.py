"""Optional RQAlpha A-share backtest adapter exports."""

from quantpilot_core.rqalpha_ashare_backtest_adapter.adapter import (
    run_rqalpha_ashare_backtest,
)
from quantpilot_core.rqalpha_ashare_backtest_adapter.contracts import (
    RqalphaAshareBacktestInput,
    RqalphaAshareBacktestMetric,
    RqalphaAshareBacktestReport,
    RqalphaAshareBacktestResult,
    RqalphaAshareBacktestStatus,
)
from quantpilot_core.rqalpha_ashare_backtest_adapter.normalizer import (
    normalize_rqalpha_runner_output,
)
from quantpilot_core.rqalpha_ashare_backtest_adapter.report import (
    build_rqalpha_ashare_backtest_report,
)

__all__ = [
    "RqalphaAshareBacktestInput",
    "RqalphaAshareBacktestMetric",
    "RqalphaAshareBacktestReport",
    "RqalphaAshareBacktestResult",
    "RqalphaAshareBacktestStatus",
    "build_rqalpha_ashare_backtest_report",
    "normalize_rqalpha_runner_output",
    "run_rqalpha_ashare_backtest",
]
