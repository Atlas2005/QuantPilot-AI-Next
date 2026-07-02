from __future__ import annotations

from pathlib import Path

from quantpilot_core.evaluation.profitability_smoke import (
    ProfitabilitySmokeReport,
    run_profitability_smoke_test,
)


def test_profitability_smoke_returns_structured_current_system_baseline() -> None:
    report = run_profitability_smoke_test()

    assert isinstance(report, ProfitabilitySmokeReport)
    assert report.initial_cash == 20_000.0
    assert report.final_equity > 0
    assert report.total_return == round((report.final_equity - report.initial_cash) / report.initial_cash, 6)
    assert report.realized_pnl == 0.0
    assert report.unrealized_pnl == round(sum(report.symbol_unrealized_pnl.values()), 6)
    assert report.number_of_filled_trades >= 2
    assert report.number_of_rejected_trades == 0
    assert report.turnover > 0
    assert report.cost_total > 0
    assert report.cost_drag > 0
    assert report.zero_cost_final_equity > report.final_equity
    assert report.zero_cost_total_return > report.total_return
    assert len(report.symbols) >= 2
    assert len(report.price_dates) >= 3
    assert report.symbol_unrealized_pnl["000001.SZ"] > 0
    assert report.symbol_unrealized_pnl["000002.SZ"] < 0
    assert report.no_external_calls is True


def test_profitability_smoke_insufficient_cash_rejects_without_exception() -> None:
    report = run_profitability_smoke_test()

    assert report.insufficient_cash_rejected_trades > 0
    assert "insufficient_cash" in report.insufficient_cash_rejection_reasons


def test_profitability_smoke_helper_has_no_forbidden_runtime_scope() -> None:
    source = (
        Path(__file__).parents[2]
        / "src"
        / "quantpilot_core"
        / "evaluation"
        / "profitability_smoke.py"
    ).read_text()

    forbidden_fragments = (
        "requests",
        "urllib",
        "socket",
        "download",
        "openai",
        "anthropic",
        "deepseek",
        "place_order",
        "send_order",
        "submit_order",
    )
    assert not any(fragment in source.lower() for fragment in forbidden_fragments)
