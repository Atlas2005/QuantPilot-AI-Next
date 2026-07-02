from __future__ import annotations

import importlib
from pathlib import Path

from quantpilot_core.rqalpha_ashare_backtest_adapter import (
    RqalphaAshareBacktestInput,
    RqalphaAshareBacktestStatus,
    build_rqalpha_ashare_backtest_report,
    run_rqalpha_ashare_backtest,
)


def valid_input() -> RqalphaAshareBacktestInput:
    return RqalphaAshareBacktestInput(
        strategy_id="ashare-momentum",
        symbols=("000001.XSHE",),
        start_date="2026-01-02",
        end_date="2026-01-30",
        initial_cash=100_000.0,
        benchmark="000300.XSHG",
    )


def test_invalid_input_returns_invalid_input() -> None:
    result = run_rqalpha_ashare_backtest(
        RqalphaAshareBacktestInput(
            strategy_id="",
            symbols=(),
            start_date="2026-02-01",
            end_date="2026-01-01",
            initial_cash=0.0,
        )
    )

    assert result.status == RqalphaAshareBacktestStatus.INVALID_INPUT.value
    assert result.executed is False
    assert result.errors


def test_missing_rqalpha_returns_framework_missing(monkeypatch) -> None:
    real_import = importlib.import_module

    def fake_import(name: str):
        if name == "rqalpha":
            raise ImportError(name)
        return real_import(name)

    monkeypatch.setattr(importlib, "import_module", fake_import)

    result = run_rqalpha_ashare_backtest(valid_input())

    assert result.status == RqalphaAshareBacktestStatus.FRAMEWORK_MISSING.value
    assert result.runtime_available is False
    assert result.executed is False


def test_provided_runner_completed_mapping_returns_completed_metrics() -> None:
    def runner(backtest_input: RqalphaAshareBacktestInput) -> dict[str, object]:
        return {
            "status": "completed",
            "executed": True,
            "metrics": {"total_return": 0.12, "trade_count": 3},
            "warnings": ("caller owned runtime",),
        }

    result = run_rqalpha_ashare_backtest(valid_input(), runner=runner)

    assert result.status == RqalphaAshareBacktestStatus.COMPLETED.value
    assert result.executed is True
    assert [metric.name for metric in result.metrics] == ["total_return", "trade_count"]
    assert result.metrics[0].value == 0.12


def test_provided_runner_not_executed_mapping_returns_not_executed() -> None:
    result = run_rqalpha_ashare_backtest(
        valid_input(),
        runner=lambda _: {"warnings": ["config omitted"]},
    )

    assert result.status == RqalphaAshareBacktestStatus.NOT_EXECUTED.value
    assert result.executed is False
    assert result.metrics == ()


def test_no_top_level_rqalpha_import_in_production_package() -> None:
    package_root = (
        Path(__file__).resolve().parents[2]
        / "src"
        / "quantpilot_core"
        / "rqalpha_ashare_backtest_adapter"
    )
    violations: list[str] = []
    for path in package_root.rglob("*.py"):
        text = path.read_text(encoding="utf-8").lower()
        for forbidden in ("import rqalpha", "from rqalpha", "rqalpha."):
            if forbidden in text:
                violations.append(f"{path.name}: {forbidden}")

    assert violations == []


def test_package_exports_expected_symbols() -> None:
    module = importlib.import_module("quantpilot_core.rqalpha_ashare_backtest_adapter")

    assert hasattr(module, "RqalphaAshareBacktestInput")
    assert hasattr(module, "RqalphaAshareBacktestStatus")
    assert hasattr(module, "run_rqalpha_ashare_backtest")
    assert hasattr(module, "normalize_rqalpha_runner_output")
    assert hasattr(module, "build_rqalpha_ashare_backtest_report")


def test_report_includes_engine_status_and_no_production_readiness_claim() -> None:
    report = build_rqalpha_ashare_backtest_report(
        valid_input(),
        runner=lambda _: {"status": "not_executed", "warnings": ("manual only",)},
    )

    assert report.engine == "rqalpha"
    assert report.status == RqalphaAshareBacktestStatus.NOT_EXECUTED.value
    assert "engine=rqalpha" in report.summary
    assert "status=not_executed" in report.summary
    assert any("not production readiness" in note for note in report.notes)
