from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pandas as pd
import pytest

from quantpilot_core.evaluation import real_data_walk_forward_smoke as scaleup_module
from quantpilot_core.a_share_market_reality_execution import (
    AShareExecutionAccountState,
    AShareExecutionConfig,
    SettlementLot,
    execute_a_share_reality_proposal,
)
from quantpilot_core.evaluation.real_data_walk_forward_smoke import RealDataWalkForwardScaleupConfig
from quantpilot_core.evaluation.a_share_market_reality_execution import (
    AShareMarketRealityExecutionConfig,
    _metadata_coverage_section,
    run_a_share_market_reality_execution_v1,
)
from quantpilot_core.evaluation.ml_ranking_robustness_walkforward import MLRankingRobustnessWalkForwardConfig
from quantpilot_core.order_intent import OrderIntent, OrderIntentProposal, OrderIntentSide
from quantpilot_core.paper_trading import PaperAccount, PaperFillCostAssumptions


FIXTURE_SYMBOLS = ("000001.SZ", "000002.SZ", "600000.SH")


class CountingRegressor:
    fit_calls = []

    def fit(self, x, y, eval_set=None):
        self.__class__.fit_calls.append(len(x))
        self.feature_importances_ = [1.0 for _ in x.columns]
        return self

    def predict(self, x):
        return [float(row["momentum_20d"]) - float(row["volatility_20d"]) for _, row in x.iterrows()]


def proposal(*intents: OrderIntent) -> OrderIntentProposal:
    return OrderIntentProposal(intents=intents, proposal_source="exec2", run_label="unit", advisory_only=True)


def intent(symbol: str, side: OrderIntentSide | str, shares: int, order_id: str | None = None) -> OrderIntent:
    metadata = {"order_id": order_id} if order_id else {}
    return OrderIntent(symbol=symbol, side=side, target_shares=shares, metadata=metadata, run_label="unit")


def market_row(**overrides):
    row = {
        "date": "2025-01-02",
        "symbol": "600000.SH",
        "open": 10.0,
        "high": 10.2,
        "low": 9.8,
        "close": 10.0,
        "previous_close": 9.9,
        "volume": 10_000,
        "is_suspended": False,
    }
    row.update(overrides)
    return {"600000.SH": row}


def zero_cost() -> PaperFillCostAssumptions:
    return PaperFillCostAssumptions(fee_rate=0.0, min_fee=0.0, stamp_tax_rate=0.0, slippage_bps=0.0, lot_size=100)


def run_one(
    state: AShareExecutionAccountState,
    order: OrderIntent,
    rows=None,
    cfg: AShareExecutionConfig | None = None,
    cost: PaperFillCostAssumptions | None = None,
):
    return execute_a_share_reality_proposal(
        proposal(order),
        rows or market_row(),
        state,
        trade_date="2025-01-02",
        cost_assumptions=cost or zero_cost(),
        config=cfg or AShareExecutionConfig(max_participation_rate=1.0),
    )


def fixture_frame(days: int = 150) -> pd.DataFrame:
    rows = []
    specs = {
        "000001.SZ": (10.0, 0.04, 1_000_000),
        "000002.SZ": (12.0, 0.01, 900_000),
        "600000.SH": (9.0, 0.03, 800_000),
    }
    for symbol, (base, slope, volume) in specs.items():
        previous = base
        for index in range(days):
            close = round(base + index * slope + ((-1) ** index) * 0.01, 6)
            rows.append(
                {
                    "date": pd.Timestamp("2025-01-01") + pd.Timedelta(days=index),
                    "symbol": symbol,
                    "open": close,
                    "high": round(close + 0.05, 6),
                    "low": round(close - 0.05, 6),
                    "close": close,
                    "previous_close": previous,
                    "volume": volume + index * 100,
                    "amount": close * (volume + index * 100),
                    "is_suspended": False,
                }
            )
            previous = close
    return pd.DataFrame(rows)


def robustness_config(tmp_path: Path, **metadata) -> MLRankingRobustnessWalkForwardConfig:
    return MLRankingRobustnessWalkForwardConfig(
        symbols=FIXTURE_SYMBOLS,
        start_date="2025-01-01",
        end_date="2025-06-01",
        provider="fixture",
        fold_count=3,
        min_fold_count=2,
        train_window_days=20,
        validation_window_days=10,
        test_window_days=10,
        max_windows_per_fold=1,
        min_symbols_required=2,
        target_position_count=2,
        max_position_weight=0.20,
        reserve_cash_weight=0.02,
        artifact_path=None,
        metadata=metadata,
    )


def test_sellable_quantity_is_separate_from_total_position_and_same_day_lot_is_deferred() -> None:
    state = AShareExecutionAccountState(
        account=PaperAccount(cash=0.0, positions={"600000.SH": 200}, average_costs={"600000.SH": 9.0}),
        settlement_lots=(
            SettlementLot("600000.SH", 100, "2025-01-01"),
            SettlementLot("600000.SH", 100, "2025-01-02"),
        ),
    )

    result = run_one(state, intent("600000.SH", OrderIntentSide.SELL, 200))

    outcome = result.outcomes[0]
    assert outcome.sellable_quantity_before == 100
    assert outcome.status == "deferred"
    assert outcome.rejection_or_deferral_reason == "t_plus_one_sellable_quantity_insufficient"
    assert result.state.account.positions == {"600000.SH": 200}


def test_unaffected_settled_position_can_sell_when_other_same_day_lot_exists() -> None:
    state = AShareExecutionAccountState(
        account=PaperAccount(cash=0.0, positions={"600000.SH": 200}, average_costs={"600000.SH": 9.0}),
        settlement_lots=(
            SettlementLot("600000.SH", 100, "2025-01-01"),
            SettlementLot("600000.SH", 100, "2025-01-02"),
        ),
    )

    result = run_one(state, intent("600000.SH", "sell", 100))

    assert result.outcomes[0].status == "filled"
    assert result.state.account.positions == {"600000.SH": 100}
    assert sum(lot.quantity for lot in result.state.settlement_lots) == 100


def test_quantity_normalization_and_invalid_quantities_are_reported() -> None:
    state = AShareExecutionAccountState(PaperAccount(cash=20_000.0))

    invalid = run_one(state, intent("600000.SH", "buy", 50))
    normalized = run_one(state, intent("600000.SH", "buy", 150))

    assert invalid.outcomes[0].rejection_or_deferral_reason == "buy_quantity_below_lot_size"
    assert normalized.outcomes[0].normalized_quantity == 100
    assert normalized.outcomes[0].rejection_or_deferral_reason == "buy_quantity_normalized_to_lot_increment"
    assert normalized.outcomes[0].status == "rejected"


def test_suspension_unavailable_price_and_one_price_limit_are_rejected() -> None:
    state = AShareExecutionAccountState(PaperAccount(cash=20_000.0))

    suspended = run_one(state, intent("600000.SH", "buy", 100), market_row(is_suspended=True))
    missing = run_one(state, intent("600000.SH", "buy", 100), market_row(close=0.0, open=0.0))
    limit_up = run_one(
        state,
        intent("600000.SH", "buy", 100),
        market_row(close=11.0, open=11.0, high=11.0, low=11.0, previous_close=10.0, upper_limit=11.0, lower_limit=9.0),
    )

    assert suspended.outcomes[0].rejection_or_deferral_reason == "symbol_suspended"
    assert missing.outcomes[0].rejection_or_deferral_reason == "price_missing_or_non_positive"
    assert limit_up.outcomes[0].rejection_or_deferral_reason == "one_price_limit_state_no_realistic_fill"


def test_volume_participation_partial_fill_cash_fee_and_account_consistency() -> None:
    state = AShareExecutionAccountState(PaperAccount(cash=20_000.0))
    cost = PaperFillCostAssumptions(fee_rate=0.001, min_fee=1.0, stamp_tax_rate=0.0005, slippage_bps=10.0, lot_size=100)

    result = run_one(
        state,
        intent("600000.SH", "buy", 500),
        market_row(volume=1_000),
        cfg=AShareExecutionConfig(max_participation_rate=0.20),
        cost=cost,
    )

    outcome = result.outcomes[0]
    assert outcome.status == "partial"
    assert outcome.filled_quantity == 200
    assert outcome.unfilled_quantity == 300
    assert outcome.fee_breakdown["commission"] > 0
    assert outcome.fee_breakdown["slippage_cost"] > 0
    assert outcome.cash_available_after < outcome.cash_available_before
    assert result.state.account.positions == {"600000.SH": 200}
    assert result.state.account.cash >= 0


def test_duplicate_order_id_is_standardized_rejection_reason() -> None:
    state = AShareExecutionAccountState(PaperAccount(cash=50_000.0))
    first = execute_a_share_reality_proposal(
        proposal(intent("600000.SH", "buy", 100, "dup"), intent("600000.SH", "buy", 100, "dup")),
        market_row(),
        state,
        trade_date="2025-01-02",
        cost_assumptions=zero_cost(),
        config=AShareExecutionConfig(max_participation_rate=1.0),
    )

    assert first.outcomes[0].status == "filled"
    assert first.outcomes[1].rejection_or_deferral_reason == "duplicate_order_id"


def test_reality_comparison_uses_identical_base_and_reality_strategy_inputs_without_network(tmp_path: Path) -> None:
    CountingRegressor.fit_calls = []

    report = run_a_share_market_reality_execution_v1(
        AShareMarketRealityExecutionConfig(
            robustness_config=robustness_config(tmp_path),
            artifact_path=tmp_path / "a_share_market_reality_execution" / "latest_report.json",
            a_share_execution_config={"max_participation_rate": 0.05},
        ),
        price_frame=fixture_frame(),
        model_backend_factory=CountingRegressor,
    )

    assert report.identical_strategy_inputs is True
    assert report.no_profitability_claim is True
    assert report.aggregate_results["fold_count"] >= 2
    assert "attempted_order_count" in report.aggregate_results
    assert report.artifact_path is not None
    assert Path(report.artifact_path).exists()
    assert report.corporate_action_price_consistency_audit["material_inconsistency_detected"] is False
    assert any("explicit_fill_simulation_boundary" in module for module in report.modules_reused)
    assert "reality_coverage_audit" in report.__dict__
    assert "base_vs_reality_order_deltas" in report.__dict__


def test_production_scaleup_path_reports_rule_coverage_for_controlled_execution_fixtures(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    trade_date = pd.Timestamp("2025-01-02")
    rows = [
        _bar(trade_date, "600000.SH", close=10.0),
        _bar(trade_date, "000001.SZ", close=10.0),
        _bar(trade_date, "000002.SZ", close=10.0),
        _bar(trade_date, "000003.SZ", close=10.0, is_suspended=True),
        _bar(trade_date, "000004.SZ", close=11.0, open=11.0, high=11.0, low=11.0, previous_close=10.0),
        _bar(trade_date, "000005.SZ", close=10.0, volume=1_000),
        _bar(trade_date, "000006.SZ", close=1_000.0),
    ]
    frame = pd.DataFrame(rows)
    window = SimpleNamespace(
        train_start="2025-01-02",
        train_end="2025-01-02",
        test_start="2025-01-02",
        test_end="2025-01-02",
        run_label="controlled",
    )
    orders = proposal(
        intent("600000.SH", "sell", 200),
        intent("600000.SH", "sell", 100),
        intent("000001.SZ", "buy", 150),
        intent("000002.SZ", "sell", 75),
        intent("000003.SZ", "buy", 100),
        intent("000004.SZ", "buy", 100),
        intent("000005.SZ", "buy", 500),
        intent("000006.SZ", "buy", 100),
    )

    def controlled_builder(**kwargs):
        return orders, {
            "resized_order_count": 0,
            "skipped_below_lot_count": 0,
            "rebalance_sell_count": 3,
            "rebalance_buy_count": 5,
            "rebalance_order_sides": tuple(order.side.value if isinstance(order.side, OrderIntentSide) else order.side for order in orders.intents),
            "skipped_rebalance_orders": (),
        }

    monkeypatch.setattr(scaleup_module, "_build_rebalance_proposal", controlled_builder)
    config = RealDataWalkForwardScaleupConfig(
        symbols=tuple(row["symbol"] for row in rows),
        initial_cash=7_000.0,
        min_symbols_required=1,
        min_order_lot=1,
        max_windows=1,
        artifact_path=None,
        ranking_mode="equal_weight_baseline",
        metadata={
            "execution_reality": "a_share_market_reality_v1",
            "initial_paper_account": {
                "cash": 7_000.0,
                "positions": {"600000.SH": 200, "000002.SZ": 75},
                "average_costs": {"600000.SH": 9.0, "000002.SZ": 9.0},
            },
            "initial_settlement_lots": (
                SettlementLot("600000.SH", 100, "2025-01-01"),
                SettlementLot("600000.SH", 100, "2025-01-02"),
                SettlementLot("000002.SZ", 75, "2025-01-01"),
            ),
            "a_share_execution_config": {"max_participation_rate": 0.20},
            "a_share_tradability_metadata_enrichment_v1": True,
            "a_share_tradability_metadata": {
                "fetched_at": "controlled-fixture",
                "primary_price_provider": "controlled_fixture",
                "security_master_records": tuple(
                    {
                        "symbol": row["symbol"],
                        "exchange": row["symbol"].split(".")[-1],
                        "board": "main",
                        "is_st": False,
                        "source": "controlled_point_in_time_security_master",
                        "effective_start": "2025-01-02",
                        "data_quality": "fixture",
                    }
                    for row in rows
                ),
                "tradability_overrides": (
                    {
                        "trade_date": "2025-01-02",
                        "symbol": "000004.SZ",
                        "upper_limit": 11.0,
                        "lower_limit": 9.0,
                        "source": "controlled_point_in_time_price_limit",
                        "data_quality": "fixture",
                    },
                ),
            },
        },
    )

    per_window, account = scaleup_module._run_scaleup_rebalance_windows(frame, (window,), config)

    metrics = per_window[0]
    outcomes = {row["symbol"] + ":" + row["side"] + ":" + str(row["requested_quantity"]): row for row in metrics["execution_outcomes"]}
    assert metrics["execution_reality"] == "a_share_market_reality_v1"
    assert metrics["attempted_order_count"] == 8
    assert outcomes["600000.SH:sell:200"]["status"] == "deferred"
    assert outcomes["600000.SH:sell:100"]["status"] == "filled"
    assert outcomes["000001.SZ:buy:150"]["rejection_or_deferral_reason"] == "buy_quantity_normalized_to_lot_increment"
    assert outcomes["000002.SZ:sell:75"]["status"] == "filled"
    assert outcomes["000003.SZ:buy:100"]["rejection_or_deferral_reason"] == "symbol_suspended"
    assert outcomes["000004.SZ:buy:100"]["rejection_or_deferral_reason"] == "one_price_limit_state_no_realistic_fill"
    assert outcomes["000005.SZ:buy:500"]["status"] == "partial"
    assert outcomes["000005.SZ:buy:500"]["filled_quantity"] == 200
    assert outcomes["000006.SZ:buy:100"]["rejection_or_deferral_reason"] == "insufficient_cash_after_fee_reserve"
    assert outcomes["000005.SZ:buy:500"]["fee_breakdown"]["commission"] > 0
    assert outcomes["000005.SZ:buy:500"]["cash_available_after"] > 0
    assert account.cash >= 0

    coverage = metrics["rule_coverage"]
    assert coverage["t_plus_sellable_inventory"]["triggered_order_count"] >= 1
    assert coverage["buy_lot_normalization"]["triggered_order_count"] >= 1
    assert coverage["sell_odd_lot_handling"]["triggered_order_count"] >= 1
    assert coverage["suspension"]["triggered_order_count"] >= 1
    assert coverage["one_price_limit_state"]["triggered_order_count"] >= 1
    assert coverage["volume_participation_limit"]["changed_order_count"] >= 1
    assert coverage["partial_fill"]["triggered_order_count"] >= 1
    assert coverage["available_cash_frozen_cash"]["triggered_order_count"] >= 1
    assert coverage["fee_breakdown"]["triggered_order_count"] >= 1


def test_missing_price_limit_metadata_is_explicit_without_broad_order_rejection() -> None:
    state = AShareExecutionAccountState(PaperAccount(cash=20_000.0))

    result = run_one(
        state,
        intent("600000.SH", "buy", 100),
        market_row(close=11.0, open=11.0, high=11.0, low=11.0, previous_close=10.0),
        cfg=AShareExecutionConfig(max_participation_rate=1.0),
    )

    outcome = result.outcomes[0]
    assert outcome.rejection_or_deferral_reason is None
    assert outcome.status == "filled"
    assert outcome.metadata_availability["price_limit_fields"]["available"] is False
    assert outcome.rule_diagnostics["one_price_limit_state"]["metadata_unavailable"] is True

    summary = scaleup_module.summarize_execution_outcomes(result.outcomes)
    assert summary["rule_coverage"]["one_price_limit_state"]["unavailable_metadata_count"] == 1
    assert summary["metadata_availability"]["price_limit_fields"]["unavailable_count"] == 1
    coverage = _metadata_coverage_section(summary["metadata_availability"], {"rules": summary["rule_coverage"]})
    assert coverage["reality_coverage_sufficient"] is False
    assert "price_limit_fields" in coverage["unsupported_fields"]


def _bar(date: pd.Timestamp, symbol: str, **overrides):
    close = float(overrides.pop("close", 10.0))
    row = {
        "date": date,
        "symbol": symbol,
        "open": close,
        "high": close + 0.1,
        "low": close - 0.1,
        "close": close,
        "previous_close": close,
        "volume": 10_000,
        "amount": close * 10_000,
        "is_suspended": False,
    }
    row.update(overrides)
    return row
