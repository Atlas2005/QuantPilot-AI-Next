from __future__ import annotations

from dataclasses import replace
import importlib.util
from pathlib import Path
import sys
from types import SimpleNamespace

import pandas as pd
import pytest

from quantpilot_core.evaluation.full_a_strategy_ml_oos_ablation import (
    DynamicSelectorPolicy,
    FullAStrategyMLOOSAblationConfig,
    ProvisionalCandidateThresholds,
    _aggregate,
    _dynamic_rows,
    _fold_evidence,
    _ml_cost_folds,
    _ml_fold,
    _recommend,
    _rejection_reasons,
    _run_rule_fold,
    _validate,
    run_full_a_strategy_ml_oos_ablation_v1,
    score_dynamic_candidates,
)
from quantpilot_core.evaluation.real_data_walk_forward_smoke import _buy_and_hold_benchmark
from quantpilot_core.evaluation.real_data_walk_forward_smoke import RealDataWalkForwardScaleupConfig, _rank_scaleup_candidates
from quantpilot_core.evaluation.ml_ranking_robustness_walkforward import build_ml_ranking_walkforward_folds
from quantpilot_core.evaluation.ml_ranking_robustness_walkforward import MLRankingRobustnessWalkForwardConfig


def _cli_module():
    path = Path(__file__).parents[2] / "scripts" / "run_full_a_strategy_ml_oos_ablation_v1.py"
    spec = importlib.util.spec_from_file_location("full_a_ablation_cli_test", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _frame() -> pd.DataFrame:
    dates = pd.bdate_range("2023-01-02", periods=140)
    return pd.DataFrame(
        [
            {"date": date.date().isoformat(), "symbol": symbol, "open": 10 + index, "high": 11 + index, "low": 9 + index, "close": 10.5 + index, "volume": 100000, "amount": 1_000_000}
            for index, date in enumerate(dates)
            for symbol in ("000001.SZ", "000002.SZ")
        ]
    )


def _ranking_frame() -> pd.DataFrame:
    dates = pd.bdate_range("2023-01-02", periods=180)
    symbols = ("000001.SZ", "000002.SZ", "000003.SZ", "600000.SH")
    return pd.DataFrame(
        [
            {"date": date.date().isoformat(), "symbol": symbol, "open": 10 + symbol_index + index * 0.01, "high": 11 + symbol_index + index * 0.01, "low": 9 + symbol_index + index * 0.01, "close": 10.5 + symbol_index + index * 0.01, "volume": 100000 + symbol_index * 1000, "amount": 1_000_000 + symbol_index * 1000}
            for index, date in enumerate(dates)
            for symbol_index, symbol in enumerate(symbols)
        ]
    )


def _reference_buy_and_hold_benchmark(frame: pd.DataFrame, windows, initial_cash: float) -> dict[str, object]:
    """The pre-optimization per-symbol scan, retained only as test oracle."""
    if frame.empty:
        return {"benchmark_final_equity": None, "benchmark_total_return": None, "benchmark_notes": ("simple_equal_weight_benchmark_unavailable:no_price_rows",)}
    start_date = str(windows[0].test_start) if windows else str(frame["date"].min())
    end_date = str(windows[-1].test_end) if windows else str(frame["date"].max())
    ordered = frame.sort_values(["date", "symbol"], kind="stable")
    symbols = tuple(sorted(str(symbol) for symbol in ordered["symbol"].dropna().unique()))
    valid = []
    for symbol in symbols:
        group = ordered.loc[ordered["symbol"] == symbol].copy()
        start_rows = group.loc[group["date"] >= start_date]
        end_rows = group.loc[group["date"] <= end_date]
        if start_rows.empty or end_rows.empty:
            continue
        start_price = float(start_rows.iloc[0]["close"])
        end_price = float(end_rows.iloc[-1]["close"])
        if start_price > 0 and end_price > 0:
            valid.append((symbol, start_price, end_price))
    if not valid:
        return {"benchmark_final_equity": None, "benchmark_total_return": None, "benchmark_notes": ("simple_equal_weight_benchmark_unavailable:no_valid_symbol_prices",)}
    final_equity = round(sum((initial_cash / len(valid) / start_price) * end_price for _, start_price, end_price in valid), 6)
    return {
        "benchmark_final_equity": final_equity,
        "benchmark_total_return": round((final_equity - initial_cash) / initial_cash, 6),
        "benchmark_notes": ("simple_equal_weight_close_to_close_no_costs", f"benchmark_start:{start_date}", f"benchmark_end:{end_date}", f"benchmark_symbols:{','.join(symbol for symbol, _, _ in valid)}"),
    }


def test_grouped_benchmark_matches_reference_for_unsorted_missing_and_duplicate_rows() -> None:
    frame = pd.DataFrame([
        {"date": "2023-01-04", "symbol": "000002.SZ", "close": 22.0},
        {"date": "2023-01-02", "symbol": "000001.SZ", "close": 10.0},
        {"date": "2023-01-03", "symbol": "000001.SZ", "close": 12.0},
        {"date": "2023-01-02", "symbol": "000002.SZ", "close": 20.0},
        {"date": "2023-01-04", "symbol": "000001.SZ", "close": 15.0},
        {"date": "2023-01-04", "symbol": "000001.SZ", "close": 16.0},
        {"date": "2023-01-03", "symbol": "000003.SZ", "close": 0.0},
        {"date": "2023-01-04", "symbol": "000003.SZ", "close": 5.0},
        {"date": "2023-01-04", "symbol": "000004.SZ", "close": 7.0},
    ])
    windows = (SimpleNamespace(test_start="2023-01-03", test_end="2023-01-04"),)
    assert _buy_and_hold_benchmark(frame, windows, 1_000.0) == _reference_buy_and_hold_benchmark(frame, windows, 1_000.0)


def test_cli_exposes_min_fold_count_without_changing_defaults() -> None:
    cli = _cli_module()
    defaults = cli._build_parser().parse_args(["--snapshot-root", "/tmp/snapshot"])
    assert defaults.fold_count == 5
    assert defaults.min_fold_count == 3
    assert FullAStrategyMLOOSAblationConfig().fold_count == 5
    assert FullAStrategyMLOOSAblationConfig().min_fold_count == 3

    probe = cli._build_parser().parse_args(["--snapshot-root", "/tmp/snapshot", "--fold-count", "1", "--min-fold-count", "1"])
    accepted = cli._config_from_args(probe, provider=object(), symbols=("000001.SZ",), modes=("equal_weight_baseline",))
    assert accepted.fold_count == accepted.min_fold_count == 1
    _validate(accepted)

    invalid = cli._build_parser().parse_args(["--snapshot-root", "/tmp/snapshot", "--fold-count", "1"])
    with pytest.raises(ValueError, match="min_fold_count must be no greater than fold_count"):
        _validate(cli._config_from_args(invalid, provider=object(), symbols=("000001.SZ",), modes=("equal_weight_baseline",)))


@pytest.mark.parametrize(("extra_args", "expects_progress"), [((), True), (("--no-progress",), False)])
def test_cli_keyboard_interrupt_and_progress_selection_are_preserved(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], extra_args: tuple[str, ...], expects_progress: bool) -> None:
    cli = _cli_module()
    captured = {}

    class FakeSnapshotProvider:
        def __init__(self, root):
            self.root = root

        def daily_symbol_union(self, start_date, end_date):
            return ("000001.SZ",)

    def interrupted(config, *, progress_callback):
        captured["progress_callback"] = progress_callback
        raise KeyboardInterrupt

    monkeypatch.setattr(cli, "SnapshotDailyBarProvider", FakeSnapshotProvider)
    monkeypatch.setattr(cli, "run_full_a_strategy_ml_oos_ablation_v1", interrupted)
    monkeypatch.setattr(sys, "argv", ["full-a", "--snapshot-root", "/tmp/snapshot", *extra_args])

    assert cli.main() == 130
    assert (captured["progress_callback"] is not None) is expects_progress
    assert "Full-A ablation interrupted; no completed artifact was written." in capsys.readouterr().err


def test_cli_reports_disabled_dynamic_selector_without_positive_selection_count(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    cli = _cli_module()

    class FakeSnapshotProvider:
        def __init__(self, root):
            self.root = root

        def daily_symbol_union(self, start_date, end_date):
            return ("000001.SZ",)

    report = SimpleNamespace(provider="snapshot", snapshot_provenance={}, common_folds=(), per_candidate_metrics={}, selection_history=(object(),), recommendation="no_candidate", artifact_path=None, run_status="completed")
    monkeypatch.setattr(cli, "SnapshotDailyBarProvider", FakeSnapshotProvider)
    monkeypatch.setattr(cli, "run_full_a_strategy_ml_oos_ablation_v1", lambda *args, **kwargs: report)
    monkeypatch.setattr(sys, "argv", ["full-a", "--snapshot-root", "/tmp/snapshot", "--no-dynamic-selector"])

    assert cli.main() == 0
    output = capsys.readouterr().out
    assert "dynamic selector: disabled" in output
    assert "dynamic selections: 1" not in output


def test_common_folds_are_chronological_and_decided_before_test() -> None:
    config = FullAStrategyMLOOSAblationConfig(symbols=("000001.SZ", "000002.SZ"), fold_count=2, min_fold_count=1, train_window_days=20, validation_window_days=10, test_window_days=10)
    folds = build_ml_ranking_walkforward_folds(_frame(), MLRankingRobustnessWalkForwardConfig(symbols=config.symbols, fold_count=2, min_fold_count=1, train_window_days=20, validation_window_days=10, test_window_days=10))
    assert folds
    evidence = _fold_evidence(folds[0], _frame(), config)
    assert evidence["training_end"] < evidence["validation_start"] <= evidence["validation_end"] < evidence["test_start"]
    assert evidence["decision_before_test"] is True


def test_selector_uses_validation_metrics_and_has_stable_ties() -> None:
    metrics = {"z_rule": {"strategy_excess_return": 0.1, "positive_return_fold_ratio": 0.5, "max_drawdown": -0.1, "turnover": 10, "cost_total": 1}, "a_rule": {"strategy_excess_return": 0.1, "positive_return_fold_ratio": 0.5, "max_drawdown": -0.1, "turnover": 10, "cost_total": 1}}
    selected, scores, reason = score_dynamic_candidates(metrics, DynamicSelectorPolicy())
    assert selected == "a_rule"
    assert scores["a_rule"] == scores["z_rule"]
    assert reason == "highest_validation_score_stable_tie_break"


def _eligible_metric(*, drawdown: float = -0.10, compounded_excess_return: float = 0.10) -> dict[str, float]:
    return {
        "successful_fold_ratio": 1.0,
        "positive_return_fold_ratio": 1.0,
        "positive_excess_fold_ratio": 1.0,
        "compounded_excess_return": compounded_excess_return,
        "max_drawdown": drawdown,
        "worst_fold_return": -0.05,
        "rejected_trade_ratio": 0.01,
        "cost_to_turnover_ratio": 0.01,
    }


@pytest.mark.parametrize(
    ("drawdown", "breaches"),
    [(-0.10, False), (-0.30, False), (-0.31, True), (-0.50, True)],
)
def test_drawdown_threshold_is_a_negative_lower_bound(drawdown: float, breaches: bool) -> None:
    reasons = _rejection_reasons(_eligible_metric(drawdown=drawdown), ProvisionalCandidateThresholds())
    assert ("max_drawdown_breach" in reasons) is breaches


def test_dynamic_selector_can_be_recommended_and_no_candidate_remains_possible() -> None:
    metrics = {
        "dynamic_selector": _eligible_metric(compounded_excess_return=0.20),
        "fixed_rule": _eligible_metric(compounded_excess_return=0.10),
    }
    assert _recommend(metrics, {name: () for name in metrics}) == "dynamic_selector"
    assert _recommend(metrics, {name: ("max_drawdown_breach",) for name in metrics}) == "no_candidate"


def test_recommendation_rejects_high_return_candidate_with_excessive_drawdown() -> None:
    metrics = {
        "unsafe": _eligible_metric(drawdown=-0.50, compounded_excess_return=0.90),
        "safe": _eligible_metric(compounded_excess_return=0.10),
    }
    rejections = {name: tuple(_rejection_reasons(row, ProvisionalCandidateThresholds())) for name, row in metrics.items()}
    assert "max_drawdown_breach" in rejections["unsafe"]
    assert _recommend(metrics, rejections) == "safe"


def _fold(fold_id: str = "fold_01") -> dict[str, str]:
    return {
        "fold_id": fold_id,
        "training_start": "2023-01-02",
        "training_end": "2023-02-01",
        "validation_start": "2023-02-02",
        "validation_end": "2023-02-10",
        "test_start": "2023-02-13",
        "test_end": "2023-02-24",
    }


def _portfolio_row(fold_id: str, excess: float, *, status: str = "completed") -> dict[str, object]:
    return {
        "fold_id": fold_id,
        "status": status,
        "total_return": excess,
        "benchmark_total_return": 0.0,
        "strategy_excess_return": excess,
        "max_drawdown": -0.05,
        "turnover": 10.0,
        "cost_total": 0.1,
        "filled_trades": 1,
        "rejected_trades": 0,
    }


def test_dynamic_selection_uses_validation_not_test_outcomes() -> None:
    folds = (_fold(),)
    tests = {"a_rule": (_portfolio_row("fold_01", -0.90),), "z_rule": (_portfolio_row("fold_01", 0.90),)}
    validation = {"a_rule": (_portfolio_row("fold_01", 0.30),), "z_rule": (_portfolio_row("fold_01", 0.10),)}
    history, selected_rows = _dynamic_rows(folds, tests, validation, FullAStrategyMLOOSAblationConfig())
    assert history[0]["selected_candidate"] == "a_rule"
    assert history[0]["uses_test_outcomes"] is False
    assert history[0]["evidence_timestamp"] < folds[0]["test_start"]
    assert selected_rows[0]["strategy_excess_return"] == -0.90


def test_validation_change_can_change_selection_and_ml_eligibility_is_recorded() -> None:
    folds = (_fold(),)
    tests = {"fixed": (_portfolio_row("fold_01", 0.1),), "lightgbm_ml_ranking": (_portfolio_row("fold_01", 0.2),)}
    validation = {"fixed": (_portfolio_row("fold_01", 0.1),), "lightgbm_ml_ranking": (_portfolio_row("fold_01", 0.3),)}
    history, _ = _dynamic_rows(folds, tests, validation, FullAStrategyMLOOSAblationConfig(fixed_rule_modes=("equal_weight_baseline",)))
    assert history[0]["selected_candidate"] == "lightgbm_ml_ranking"
    assert history[0]["candidate_eligibility"]["lightgbm_ml_ranking"] == {"eligible": True, "reason": None}

    missing_ml = {"fixed": validation["fixed"], "lightgbm_ml_ranking": (_portfolio_row("fold_01", 0.0, status="failed"),)}
    history, _ = _dynamic_rows(folds, tests, missing_ml, FullAStrategyMLOOSAblationConfig(fixed_rule_modes=("equal_weight_baseline",)))
    assert history[0]["selected_candidate"] == "fixed"
    assert history[0]["candidate_eligibility"]["lightgbm_ml_ranking"]["reason"] == "missing_pretest_validation_portfolio_evidence"


def test_fold_aggregation_names_sum_and_compounded_returns_separately() -> None:
    metrics = _aggregate((_portfolio_row("fold_01", 0.10), _portfolio_row("fold_02", 0.20)))
    assert metrics["mean_fold_return"] == 0.15
    assert metrics["median_fold_return"] == 0.15
    assert metrics["sum_fold_return"] == 0.30
    assert metrics["compounded_fold_return"] == 0.32
    assert metrics["compounded_excess_return"] == 0.32
    assert metrics["total_return"] == metrics["compounded_fold_return"]


def test_purge_is_derived_from_the_actual_ml_label_horizon() -> None:
    config = FullAStrategyMLOOSAblationConfig(symbols=("000001.SZ", "000002.SZ"))
    evidence = _fold_evidence(_fold(), _frame(), config)
    assert not hasattr(config, "purge_or_embargo_days")
    assert evidence["purge_or_embargo_days"] == 20


def test_selector_ignores_full_period_aggregate_fields() -> None:
    evidence = _portfolio_row("fold_01", 0.10)
    evidence["full_period_strategy_excess_return"] = 999.0
    selected, scores, _ = score_dynamic_candidates({"candidate": evidence})
    clean_selected, clean_scores, _ = score_dynamic_candidates({"candidate": _portfolio_row("fold_01", 0.10)})
    assert selected == clean_selected == "candidate"
    assert scores == clean_scores


class _DeterministicRegressor:
    def fit(self, x, y, eval_set=None):
        self.feature_importances_ = [1.0] * len(x.columns)
        return self

    def predict(self, x):
        return [float(index) for index in range(len(x))]


class _ConstantRegressor:
    def fit(self, x, y, eval_set=None):
        self.feature_importances_ = [1.0] * len(x.columns)
        return self

    def predict(self, x):
        return [1.0] * len(x)


def test_ml_prediction_map_uses_rebalance_date_and_preserves_symbol_association() -> None:
    train = pd.DataFrame([
        {"date": "2023-01-02", "symbol": "000001.SZ", "close": 10.0},
        {"date": "2023-01-02", "symbol": "000002.SZ", "close": 10.0},
        {"date": "2023-01-03", "symbol": "000001.SZ", "close": 10.1},
        {"date": "2023-01-03", "symbol": "000002.SZ", "close": 10.1},
    ])
    config = RealDataWalkForwardScaleupConfig(
        symbols=("000001.SZ", "000002.SZ"), ranking_mode="ml_prediction_score",
        metadata={"ml_prediction_map": {("2023-01-04", "000001.SZ"): 1.0, ("2023-01-04", "000002.SZ"): 9.0}},
    )
    ranked = _rank_scaleup_candidates(train, {"000001.SZ": 10.2, "000002.SZ": 10.2}, config, ranking_date="2023-01-04")
    assert tuple(symbol for _, symbol, _ in ranked) == ("000002.SZ", "000001.SZ")


def test_reversed_ml_scores_change_executor_selection_and_constant_scores_are_unavailable() -> None:
    config = FullAStrategyMLOOSAblationConfig(
        symbols=("000001.SZ", "000002.SZ", "000003.SZ", "600000.SH"), fold_count=2, min_fold_count=1,
        train_window_days=20, validation_window_days=10, test_window_days=10, max_windows_per_fold=1,
        min_symbols_required=4, target_position_count=2, fixed_rule_modes=("equal_weight_baseline",),
        include_ml_candidate=True, include_dynamic_selector=False, cost_multipliers=(1.0,), artifact_path=None,
    )
    reversed_report = run_full_a_strategy_ml_oos_ablation_v1(config, price_frame=_ranking_frame(), model_backend_factory=_DeterministicRegressor)
    fixed_rows = {row["fold_id"]: row for row in reversed_report.per_candidate_fold_metrics["equal_weight_baseline"]}
    ml_rows = reversed_report.per_candidate_fold_metrics["lightgbm_ml_ranking"]
    assert all(row["ranking_evidence"]["ml_selected_symbols"] != row["ranking_evidence"]["equal_weight_selected_symbols"] for row in ml_rows)
    assert all(tuple(row["ranking_evidence"]["ml_selected_symbols"]) == tuple(item["symbol"] for item in row["ranking_evidence"]["top_predicted_symbols"][:2]) for row in ml_rows)
    assert all(set(row["ranking_evidence"]["actual_filled_order_symbols"]) == set(row["ranking_evidence"]["ml_selected_symbols"]) for row in ml_rows)
    assert all(row["execution_windows"][0]["candidate_symbols"] != fixed_rows[row["fold_id"]]["execution_windows"][0]["candidate_symbols"] for row in ml_rows)
    assert all(row["benchmark_total_return"] == fixed_rows[row["fold_id"]]["benchmark_total_return"] for row in ml_rows)

    constant_report = run_full_a_strategy_ml_oos_ablation_v1(config, price_frame=_ranking_frame(), model_backend_factory=_ConstantRegressor)
    constant_rows = constant_report.per_candidate_fold_metrics["lightgbm_ml_ranking"]
    assert all(row["status"] == "failed" for row in constant_rows)
    assert all(row["ranking_evidence"]["fallback_used"] is True for row in constant_rows)
    assert all(row["ranking_evidence"]["fallback_reason"] == "ml_ranking_input_unavailable:constant_or_tied_scores" for row in constant_rows)


def test_orchestrator_reports_dynamic_cost_sensitivity_and_reuses_injected_frame(monkeypatch: pytest.MonkeyPatch) -> None:
    def fail_load(*args, **kwargs):
        raise AssertionError("injected price frame must avoid provider loading")

    monkeypatch.setattr("quantpilot_core.evaluation.full_a_strategy_ml_oos_ablation._load_bars", fail_load)
    report = run_full_a_strategy_ml_oos_ablation_v1(
        FullAStrategyMLOOSAblationConfig(
            symbols=("000001.SZ", "000002.SZ"),
            fold_count=2,
            min_fold_count=1,
            train_window_days=20,
            validation_window_days=10,
            test_window_days=10,
            min_symbols_required=2,
            target_position_count=2,
            fixed_rule_modes=("equal_weight_baseline",),
            cost_multipliers=(1.0, 1.5),
            artifact_path=None,
        ),
        price_frame=_frame(),
        model_backend_factory=_DeterministicRegressor,
    )
    dynamic_rows = [row for row in report.cost_sensitivity if row["candidate_id"] == "dynamic_selector"]
    assert report.run_status == "completed"
    assert {row["cost_multiplier"] for row in dynamic_rows} == {1.0, 1.5}
    assert all("selection_changed_vs_base" in row for row in dynamic_rows)
    assert all(row["uses_test_outcomes"] is False for row in report.selection_history)
    assert all("candidate_eligibility" in row for row in report.selection_history)
    fixed_by_fold = {row["fold_id"]: row for row in report.per_candidate_fold_metrics["equal_weight_baseline"]}
    ml_rows = report.per_candidate_fold_metrics["lightgbm_ml_ranking"]
    assert all(row["test_range"] == fixed_by_fold[row["fold_id"]]["test_range"] for row in ml_rows)
    assert all(row["benchmark_total_return"] == fixed_by_fold[row["fold_id"]]["benchmark_total_return"] for row in ml_rows)
    assert all({"filled_trades", "rejected_trades", "rejected_trade_ratio", "turnover", "cost_total", "execution_windows"} <= set(row) for row in ml_rows)
    assert all(row["filled_trades"] > 0 for row in ml_rows if row["turnover"] or row["cost_total"])


def test_ml_fold_adapter_preserves_execution_evidence_and_rejects_common_fold_mismatch() -> None:
    row = {
        "fold_id": "fold_01", "status": "completed",
        "training_range": ("2023-01-02", "2023-02-01"),
        "validation_range": ("2023-02-02", "2023-02-10"),
        "test_range": ("2023-02-13", "2023-02-24"),
        "actual_trading_evaluation_range": ("2023-02-13", "2023-02-24"),
        "ml_result": {"benchmark_total_return": 0.1, "turnover": 100.0, "cost_total": 1.0, "filled_trades": 2, "rejected_trades": 1, "rejected_trade_ratio": 0.333333},
        "ml_execution_windows": ({"test_start": "2023-02-13", "test_end": "2023-02-24"},),
    }
    fixed = {"benchmark_total_return": 0.1, "execution_windows": ({"test_start": "2023-02-13", "test_end": "2023-02-24"},)}
    adapted = _ml_fold(row, common_fold=_fold(), benchmark_reference=fixed)
    assert adapted["filled_trades"] == 2
    assert adapted["rejected_trades"] == 1
    assert adapted["execution_windows"] == row["ml_execution_windows"]

    mismatched = _ml_fold({**row, "test_range": ("2023-02-14", "2023-02-24")}, common_fold=_fold(), benchmark_reference=fixed)
    assert mismatched["status"] == "failed"
    assert mismatched["ineligibility_reason"] == "ml_common_fold_or_benchmark_mismatch"

    unavailable = _ml_fold({"fold_id": "fold_01", "status": "failed", "failure_reason": "missing"}, common_fold=_fold(), benchmark_reference=fixed)
    assert unavailable["status"] == "failed"
    assert unavailable["failure_reason"] == "missing"
    assert "filled_trades" not in unavailable


def test_ml_cost_fold_adapter_preserves_actual_execution_counts() -> None:
    detail = {"fold_id": "fold_01", "status": "completed", "training_range": ("a", "b"), "validation_range": ("c", "d"), "test_range": ("e", "f")}
    scenario = {"fold_id": "fold_01", "cost_multiplier": 1.0, "benchmark_total_return": 0.1, "turnover": 100.0, "cost_total": 1.0, "filled_trades": 2, "rejected_trades": 1, "rejected_trade_ratio": 0.333333, "execution_windows": ({"test_start": "e", "test_end": "f"},)}
    report = SimpleNamespace(fold_results=(detail,), cost_sensitivity_results=(scenario,))
    output = _ml_cost_folds(report, 1.0, validation=False)
    assert output[0]["filled_trades"] == 2
    assert output[0]["rejected_trades"] == 1
    assert output[0]["execution_windows"] == scenario["execution_windows"]


def test_rule_candidates_reuse_fold_benchmarks_across_cost_multipliers(monkeypatch: pytest.MonkeyPatch) -> None:
    import quantpilot_core.evaluation.real_data_walk_forward_smoke as scaleup_module

    original = scaleup_module._benchmark_metrics
    calls = []

    def counted(*args, **kwargs):
        calls.append((args[2], args[3]))
        return original(*args, **kwargs)

    monkeypatch.setattr(scaleup_module, "_benchmark_metrics", counted)
    report = run_full_a_strategy_ml_oos_ablation_v1(
        FullAStrategyMLOOSAblationConfig(
            symbols=("000001.SZ", "000002.SZ"), fold_count=2, min_fold_count=1,
            train_window_days=20, validation_window_days=10, test_window_days=10,
            min_symbols_required=2, target_position_count=2,
            fixed_rule_modes=("equal_weight_baseline", "momentum_20d"),
            include_ml_candidate=False, include_dynamic_selector=False,
            cost_multipliers=(1.0, 1.5), artifact_path=None,
        ),
        price_frame=_frame(),
    )
    # Two OOS folds plus two validation folds, not once per candidate or cost.
    assert len(calls) == len(report.common_folds) * 2

    isolated_cache = {}
    fold = dict(report.common_folds[0])
    _run_rule_fold("equal_weight_baseline", fold, _frame(), config := FullAStrategyMLOOSAblationConfig(
        symbols=("000001.SZ", "000002.SZ"), train_window_days=20, test_window_days=10,
        min_symbols_required=2, target_position_count=2, artifact_path=None,
    ), "all_a_share_snapshot", (), benchmark_cache=isolated_cache)
    _run_rule_fold("equal_weight_baseline", fold, _frame(), replace(config, initial_cash=2_000_000.0), "all_a_share_snapshot", (), benchmark_cache=isolated_cache)
    assert len(isolated_cache) == 2


def test_progress_events_are_monotonic_and_do_not_change_report_values() -> None:
    config = FullAStrategyMLOOSAblationConfig(
        symbols=("000001.SZ", "000002.SZ"), fold_count=2, min_fold_count=1,
        train_window_days=20, validation_window_days=10, test_window_days=10,
        min_symbols_required=2, target_position_count=2,
        fixed_rule_modes=("equal_weight_baseline",), include_ml_candidate=False,
        include_dynamic_selector=True, cost_multipliers=(1.0, 1.5), artifact_path=None,
    )
    events = []
    with_progress = run_full_a_strategy_ml_oos_ablation_v1(config, price_frame=_frame(), progress_callback=events.append)
    without_progress = run_full_a_strategy_ml_oos_ablation_v1(config, price_frame=_frame())

    assert with_progress == without_progress
    assert events[-1]["phase"] == "artifact_write_complete"
    assert events[-1]["percentage"] == 100.0
    assert [event["completed_work_units"] for event in events] == sorted(event["completed_work_units"] for event in events)
    assert all(event["fold_count"] in {None, 2} for event in events)
    assert any(event["candidate"] == "equal_weight_baseline" and event["fold_index"] == 1 for event in events)
    assert any(event["cost_multiplier"] == 1.5 for event in events)
