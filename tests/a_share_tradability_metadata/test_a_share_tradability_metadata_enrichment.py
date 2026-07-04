from __future__ import annotations

from pathlib import Path

import pandas as pd

from quantpilot_core.a_share_tradability_metadata import (
    AShareTradabilityMetadataConfig,
    SecurityMasterRecord,
    TradabilityOverrideRecord,
    enrich_market_rows,
)
from quantpilot_core.evaluation.a_share_tradability_metadata_enrichment import (
    AShareTradabilityMetadataEnrichmentConfig,
    run_a_share_tradability_metadata_enrichment_v1,
)
from quantpilot_core.evaluation.a_share_market_reality_execution import _metadata_coverage_section
from quantpilot_core.evaluation.ml_ranking_robustness_walkforward import MLRankingRobustnessWalkForwardConfig
from quantpilot_core.a_share_market_reality_execution import (
    AShareExecutionAccountState,
    AShareExecutionConfig,
    execute_a_share_reality_proposal,
    summarize_execution_outcomes,
)
from quantpilot_core.order_intent import OrderIntent, OrderIntentProposal
from quantpilot_core.paper_trading import PaperAccount, PaperFillCostAssumptions


class CountingRegressor:
    fit_calls = []

    def fit(self, x, y, eval_set=None):
        self.__class__.fit_calls.append(len(x))
        self.feature_importances_ = [1.0 for _ in x.columns]
        return self

    def predict(self, x):
        return [float(row["momentum_20d"]) - float(row["volatility_20d"]) for _, row in x.iterrows()]


def test_point_in_time_board_st_and_no_future_status_leakage() -> None:
    rows = {
        "300001.SZ": {
            "date": "2020-01-02",
            "symbol": "300001.SZ",
            "open": 10.0,
            "high": 10.5,
            "low": 9.5,
            "close": 10.0,
            "previous_close": 10.0,
            "volume": 1000,
        }
    }
    config = AShareTradabilityMetadataConfig(
        security_master_records=(
            SecurityMasterRecord("300001.SZ", board="main", is_st=False, source="security_master", effective_start="2010-01-01", effective_end="2020-01-31"),
            SecurityMasterRecord("300001.SZ", board="chinext", is_st=True, source="security_master", effective_start="2020-02-01"),
        ),
        fetched_at="unit-test",
        enabled=True,
    )

    enriched = enrich_market_rows(rows, config=config)["300001.SZ"]

    assert enriched["board"] == "main"
    assert enriched["is_st"] is False
    assert enriched["upper_limit"] == 11.0
    assert enriched["lower_limit"] == 9.0


def test_suspension_one_price_limit_provider_precedence_and_missing_fields() -> None:
    rows = {
        "600000.SH": {
            "date": "2025-01-02",
            "symbol": "600000.SH",
            "open": 11.0,
            "high": 11.0,
            "low": 11.0,
            "close": 11.0,
            "previous_close": 10.0,
            "volume": 1000,
        }
    }
    config = AShareTradabilityMetadataConfig(
        tradability_overrides=(
            TradabilityOverrideRecord("2025-01-02", "600000.SH", is_suspended=True, upper_limit=11.0, lower_limit=9.0, source="tushare_limit_list_d"),
        ),
        fetched_at="unit-test",
        enabled=True,
    )

    enriched = enrich_market_rows(rows, config=config)["600000.SH"]

    assert enriched["is_suspended"] is True
    assert enriched["tradable"] is False
    assert enriched["one_price_upper_limit"] is True
    assert enriched["tradability_metadata_fields"]["price_limit_fields"]["provider"] == "tushare_limit_list_d"
    assert enriched["tradability_metadata_fields"]["corporate_action_fields"]["unavailable_reason"] == "corporate_action_fields_unavailable"
    assert enriched["price_basis_metadata"]["execution"] == "unadjusted_adjustment_none"


def test_price_limit_derivation_unavailable_when_historical_st_status_unknown() -> None:
    rows = {
        "600000.SH": {
            "date": "2025-01-02",
            "symbol": "600000.SH",
            "open": 11.0,
            "high": 11.0,
            "low": 11.0,
            "close": 11.0,
            "previous_close": 10.0,
            "volume": 1000,
        }
    }

    enriched = enrich_market_rows(rows, config=AShareTradabilityMetadataConfig(enabled=True, fetched_at="unit-test"))["600000.SH"]

    assert enriched["board"] == "main"
    assert enriched["is_st"] is None
    assert "upper_limit" not in enriched
    assert enriched["tradability_metadata_fields"]["price_limit_fields"]["quality"] == "unavailable"
    assert enriched["tradability_metadata_fields"]["price_limit_fields"]["unavailable_reason"] == "price_limit_requires_previous_close_and_point_in_time_board_st_status"


def test_direct_provider_limits_remain_usable_without_st_derivation() -> None:
    rows = {
        "600000.SH": {
            "date": "2025-01-02",
            "symbol": "600000.SH",
            "open": 11.0,
            "high": 11.0,
            "low": 11.0,
            "close": 11.0,
            "previous_close": 10.0,
            "volume": 1000,
            "upper_limit": 11.0,
            "lower_limit": 9.0,
        }
    }

    enriched = enrich_market_rows(rows, config=AShareTradabilityMetadataConfig(enabled=True, fetched_at="unit-test"))["600000.SH"]

    assert enriched["is_st"] is None
    assert enriched["one_price_upper_limit"] is True
    assert enriched["tradability_metadata_fields"]["price_limit_fields"]["quality"] == "provider_row"


def test_price_limit_derivation_records_approximated_board_lineage() -> None:
    rows = {
        "600000.SH": {
            "date": "2025-01-02",
            "symbol": "600000.SH",
            "open": 10.0,
            "high": 10.2,
            "low": 9.8,
            "close": 10.0,
            "previous_close": 10.0,
            "volume": 1000,
            "is_st": False,
        }
    }

    enriched = enrich_market_rows(rows, config=AShareTradabilityMetadataConfig(enabled=True, fetched_at="unit-test"))["600000.SH"]
    price_limit = enriched["tradability_metadata_fields"]["price_limit_fields"]

    assert enriched["board"] == "main"
    assert enriched["tradability_metadata_fields"]["board_classification"]["approximation_used"] is True
    assert price_limit["quality"] == "derived_with_approximate_input"
    assert price_limit["derived_from_approximate_input"] is True
    assert "board_classification:symbol_prefix_approximation" in price_limit["lineage"]


def test_observed_derived_and_approximation_coverage_are_separated() -> None:
    metadata = {
        "board_classification": {
            "available_count": 844,
            "observed_count": 0,
            "derived_count": 0,
            "approximation_used_count": 844,
            "unavailable_count": 0,
            "providers": {"symbol_prefix": 844},
            "approximation_reasons": {"approximation_used": 844},
        },
        "order_side_volume_participation_input": {
            "available_count": 844,
            "observed_count": 0,
            "derived_count": 0,
            "approximation_used_count": 844,
            "unavailable_count": 0,
            "providers": {"daily_volume": 844},
            "approximation_reasons": {"true_order_side_volume_participation_unavailable": 844},
        },
        "st_classification": {
            "available_count": 0,
            "observed_count": 0,
            "derived_count": 0,
            "approximation_used_count": 0,
            "unavailable_count": 844,
            "providers": {"none": 844},
            "unavailable_reasons": {"historical_st_status_unavailable": 844},
        },
        "suspension_status": {
            "available_count": 0,
            "observed_count": 0,
            "derived_count": 0,
            "approximation_used_count": 0,
            "unavailable_count": 844,
            "providers": {"none": 844},
            "unavailable_reasons": {"suspension_status_unavailable": 844},
        },
        "price_limit_fields": {
            "available_count": 837,
            "observed_count": 0,
            "derived_count": 837,
            "derived_from_approximate_input_count": 837,
            "approximation_used_count": 837,
            "unavailable_count": 7,
            "providers": {"point_in_time_board_st_regime": 837, "none": 7},
            "approximation_reasons": {"provider_explicit_price_limits_unavailable": 837},
            "unavailable_reasons": {"price_limit_requires_previous_close_and_point_in_time_board_st_status": 7},
        },
        "corporate_action_fields": {
            "available_count": 0,
            "observed_count": 0,
            "derived_count": 0,
            "approximation_used_count": 0,
            "unavailable_count": 844,
            "providers": {"none": 844},
            "unavailable_reasons": {"corporate_action_fields_unavailable": 844},
        },
    }

    coverage = _metadata_coverage_section(metadata, {"rules": {}})

    board = coverage["metadata_field_coverage"]["board_classification"]
    participation = coverage["metadata_field_coverage"]["order_side_volume_participation_input"]
    price_limit = coverage["metadata_field_coverage"]["price_limit_fields"]
    assert board["observed_record_count"] == 0
    assert board["approximation_count"] == 844
    assert participation["observed_coverage_ratio"] == 0.0
    assert participation["usable_coverage_ratio"] == 0.0
    assert price_limit["observed_record_count"] == 0
    assert price_limit["derived_record_count"] == 837
    assert price_limit["derived_from_approximate_input_count"] == 837
    assert price_limit["approximation_count"] == 837
    assert price_limit["unavailable_record_count"] == 7
    assert price_limit["quality_lineage_note"] is not None
    assert "historical_st_status" in coverage["unsupported_fields"]
    assert "suspension_status" in coverage["unsupported_fields"]
    assert "true_order_side_volume_participation_input" in coverage["unsupported_fields"]
    assert "price_limit_fields" in coverage["unsupported_fields"]
    assert coverage["reality_coverage_sufficient"] is False


def test_missing_optional_metadata_does_not_globally_block_orders() -> None:
    order = OrderIntent(symbol="600000.SH", side="buy", target_shares=100)
    result = execute_a_share_reality_proposal(
        OrderIntentProposal(intents=(order,), proposal_source="unit", run_label="unit", advisory_only=True),
        {
            "600000.SH": {
                "date": "2025-01-02",
                "symbol": "600000.SH",
                "open": 11.0,
                "high": 11.0,
                "low": 11.0,
                "close": 11.0,
                "previous_close": 10.0,
                "volume": 1000,
                "is_suspended": False,
            }
        },
        AShareExecutionAccountState(PaperAccount(cash=20_000.0)),
        trade_date="2025-01-02",
        cost_assumptions=PaperFillCostAssumptions(fee_rate=0.0, min_fee=0.0, stamp_tax_rate=0.0, slippage_bps=0.0, lot_size=100),
        config=AShareExecutionConfig(max_participation_rate=1.0),
    )

    assert result.outcomes[0].status == "filled"
    summary = summarize_execution_outcomes(result.outcomes)
    assert summary["rule_coverage"]["one_price_limit_state"]["unavailable_metadata_count"] == 1


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
                }
            )
            previous = close
    return pd.DataFrame(rows)


def robustness_config() -> MLRankingRobustnessWalkForwardConfig:
    return MLRankingRobustnessWalkForwardConfig(
        symbols=("000001.SZ", "000002.SZ", "600000.SH"),
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
    )


def test_production_path_metadata_propagation_no_network_broker_or_profitability_claim(tmp_path: Path) -> None:
    report = run_a_share_tradability_metadata_enrichment_v1(
        AShareTradabilityMetadataEnrichmentConfig(
            robustness_config=robustness_config(),
            artifact_path=tmp_path / "a_share_tradability_metadata_enrichment" / "latest_report.json",
            metadata_config={
                "fetched_at": "unit-test",
                "security_master_records": (
                    {"symbol": "000001.SZ", "board": "main", "is_st": False, "source": "security_master", "effective_start": "2000-01-01"},
                    {"symbol": "000002.SZ", "board": "main", "is_st": False, "source": "security_master", "effective_start": "2000-01-01"},
                    {"symbol": "600000.SH", "board": "main", "is_st": False, "source": "security_master", "effective_start": "2000-01-01"},
                ),
            },
        ),
        price_frame=fixture_frame(),
        model_backend_factory=CountingRegressor,
    )

    assert report.no_profitability_claim is True
    assert report.artifact_path is not None
    assert Path(report.artifact_path).exists()
    assert report.metadata_coverage_section["point_in_time_alignment_passed"] is True
    assert report.metadata_coverage_section["board_coverage"] == 1.0
    assert report.report_schema_notes["comparison_key_present"] is False
    assert report.report_schema_notes["aggregate_results_key_present"] is False
    assert "baostock" in report.provider_precedence["ohlcv"]
    assert any("execute_a_share_reality_proposal" in module for module in report.existing_modules_reused)
