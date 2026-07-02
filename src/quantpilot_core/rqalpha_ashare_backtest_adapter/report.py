"""Report builder for the optional RQAlpha A-share adapter."""

from __future__ import annotations

from quantpilot_core.rqalpha_ashare_backtest_adapter.adapter import (
    Runner,
    run_rqalpha_ashare_backtest,
)
from quantpilot_core.rqalpha_ashare_backtest_adapter.contracts import (
    RqalphaAshareBacktestInput,
    RqalphaAshareBacktestReport,
)


def build_rqalpha_ashare_backtest_report(
    backtest_input: RqalphaAshareBacktestInput,
    runner: Runner | None = None,
) -> RqalphaAshareBacktestReport:
    """Build a concise report without claiming runtime production readiness."""

    result = run_rqalpha_ashare_backtest(backtest_input, runner=runner)
    notes = (
        *result.notes,
        "RQAlpha is the mature external target for A-share event-driven semantics.",
        "vectorbt remains preferred for signal replay and portfolio metrics.",
        "Qlib remains preferred for AI and factor research.",
        "This report is adapter readiness evidence, not production readiness.",
    )
    summary = (
        f"engine={result.engine}; status={result.status}; "
        f"runtime_available={result.runtime_available}; executed={result.executed}; "
        f"metrics_count={len(result.metrics)}"
    )
    return RqalphaAshareBacktestReport(
        engine=result.engine,
        status=result.status,
        runtime_available=result.runtime_available,
        executed=result.executed,
        metrics_count=len(result.metrics),
        warnings=result.warnings,
        errors=result.errors,
        notes=notes,
        summary=summary,
    )
