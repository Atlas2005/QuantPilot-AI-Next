from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest

from quantpilot_core.evaluation import (
    FACTOR_RANKING_BASELINE_MODES,
    FactorRankingBaselineConfig,
    FactorRankingBaselineReport,
    run_factor_ranking_baseline_v1,
)
from quantpilot_core.evaluation import real_data_walk_forward_smoke as scaleup_module
from quantpilot_core.evaluation.real_data_walk_forward_smoke import RealDataWalkForwardScaleupConfig


def factor_fixture_frame(*, short_symbol: str | None = None) -> pd.DataFrame:
    rows = []
    specs = {
        "000001.SZ": {"base": 10.0, "slope": 0.030, "wave": 0.010, "volume": 1_000_000},
        "000002.SZ": {"base": 10.0, "slope": 0.050, "wave": 0.080, "volume": 950_000},
        "000003.SZ": {"base": 10.0, "slope": -0.020, "wave": 0.020, "volume": 900_000},
        "000004.SZ": {"base": 10.0, "slope": 0.025, "wave": 0.010, "volume": 12_000},
        "000005.SZ": {"base": 10.0, "slope": 0.030, "wave": 0.010, "volume": 1_000_000},
    }
    for symbol, spec in specs.items():
        length = 8 if symbol == short_symbol else 70
        for index in range(length):
            close = spec["base"] + index * spec["slope"] + ((-1) ** index) * spec["wave"]
            if symbol == "000003.SZ" and index > 45:
                close -= (index - 45) * 0.12
            rows.append(
                {
                    "date": pd.Timestamp("2026-01-01") + pd.Timedelta(days=index),
                    "symbol": symbol,
                    "close": round(max(1.0, close), 6),
                    "volume": spec["volume"] + index * 100,
                    "amount": round(max(1.0, close) * (spec["volume"] + index * 100), 6),
                }
            )
    return pd.DataFrame(rows)


def test_factor_score_schema_and_factor_computation_are_deterministic() -> None:
    report = run_factor_ranking_baseline_v1(
        factor_fixture_frame(),
        FactorRankingBaselineConfig(ranking_mode="defensive_composite_v1", target_symbol_count=3),
    )

    assert isinstance(report, FactorRankingBaselineReport)
    assert report.provider == "in_memory_fixture"
    assert report.date_range == ("2026-01-01", "2026-03-11")
    assert report.symbols_requested == ("000001.SZ", "000002.SZ", "000003.SZ", "000004.SZ", "000005.SZ")
    assert report.valid_symbols == ("000001.SZ", "000005.SZ", "000004.SZ", "000002.SZ", "000003.SZ")
    assert report.ranking_modes == FACTOR_RANKING_BASELINE_MODES
    assert report.ranking_mode == "defensive_composite_v1"
    assert report.as_of_date == "2026-03-11"
    assert report.selected_symbols == ("000001.SZ", "000005.SZ", "000004.SZ")
    first = report.factor_scores[0]
    assert first.symbol == "000001.SZ"
    assert first.volatility_20d is not None
    assert first.volatility_60d is not None
    assert first.momentum_20d is not None
    assert first.momentum_60d is not None
    assert first.drawdown_20d <= 0
    assert first.drawdown_60d <= 0
    assert first.liquidity_proxy is not None
    assert first.trend_filter is True
    assert first.ranking_mode == "defensive_composite_v1"
    assert {"normalized_factors", "factor_contributions", "missing_factors", "rejection_reasons"} <= set(
        first.factor_evidence
    )
    assert "offline_fixture_safe" in report.notes
    assert "no_external_network_in_tests" in report.notes
    assert "no_profitability_claim" in report.notes


def test_normalization_missing_data_and_stable_tie_breaking() -> None:
    report = run_factor_ranking_baseline_v1(
        factor_fixture_frame(short_symbol="000005.SZ"),
        FactorRankingBaselineConfig(ranking_mode="low_volatility_v1", target_symbol_count=4),
    )

    rejected_by_symbol = {row["symbol"]: row["reasons"] for row in report.rejected_symbols_with_reasons}
    short_score = next(score for score in report.factor_scores if score.symbol == "000005.SZ")
    assert "missing_factor_data" in rejected_by_symbol["000005.SZ"]
    assert short_score.factor_evidence["missing_factors"]
    assert report.factor_scores[0].symbol == "000001.SZ"
    assert report.factor_scores[0].composite_score >= report.factor_scores[1].composite_score
    assert report.factor_scores[0].symbol < report.factor_scores[1].symbol or (
        report.factor_scores[0].composite_score > report.factor_scores[1].composite_score
    )


def test_filter_modes_emit_selected_and_rejected_evidence() -> None:
    trend_report = run_factor_ranking_baseline_v1(
        factor_fixture_frame(),
        FactorRankingBaselineConfig(ranking_mode="low_volatility_with_trend_filter", target_symbol_count=4),
    )
    liquidity_report = run_factor_ranking_baseline_v1(
        factor_fixture_frame(),
        FactorRankingBaselineConfig(
            ranking_mode="low_volatility_with_liquidity_filter",
            target_symbol_count=4,
            min_liquidity_percentile=0.30,
        ),
    )
    guarded_report = run_factor_ranking_baseline_v1(
        factor_fixture_frame(),
        FactorRankingBaselineConfig(ranking_mode="momentum_reversal_guarded", target_symbol_count=4),
    )

    trend_reasons = {row["symbol"]: row["reasons"] for row in trend_report.rejected_symbols_with_reasons}
    liquidity_reasons = {row["symbol"]: row["reasons"] for row in liquidity_report.rejected_symbols_with_reasons}
    guarded_reasons = {row["symbol"]: row["reasons"] for row in guarded_report.rejected_symbols_with_reasons}
    assert "trend_filter_failed" in trend_reasons["000003.SZ"]
    assert "liquidity_filter_failed" in liquidity_reasons["000004.SZ"]
    assert "momentum_guard_failed" in guarded_reasons["000003.SZ"]
    assert guarded_report.factor_contribution_summary["selected_count"] == len(guarded_report.selected_symbols)


def test_factor_report_json_serialization_works_with_temp_path(tmp_path: Path) -> None:
    artifact_path = tmp_path / "factor" / "latest_report.json"

    report = run_factor_ranking_baseline_v1(
        factor_fixture_frame(),
        FactorRankingBaselineConfig(
            ranking_mode="defensive_composite_v1",
            target_symbol_count=2,
            artifact_path=artifact_path,
        ),
    )

    payload = json.loads(artifact_path.read_text(encoding="utf-8"))
    assert report.artifact_path == str(artifact_path)
    assert payload["artifact_path"] == str(artifact_path)
    assert payload["provider"] == "in_memory_fixture"
    assert payload["date_range"] == ["2026-01-01", "2026-03-11"]
    assert payload["symbols_requested"] == [
        "000001.SZ",
        "000002.SZ",
        "000003.SZ",
        "000004.SZ",
        "000005.SZ",
    ]
    assert payload["valid_symbols"] == list(report.valid_symbols)
    assert payload["ranking_modes"] == list(FACTOR_RANKING_BASELINE_MODES)
    assert payload["ranking_mode"] == "defensive_composite_v1"
    assert payload["as_of_date"] == "2026-03-11"
    assert payload["notes"] == list(report.notes)
    assert payload["selected_symbols"] == list(report.selected_symbols)
    assert payload["factor_scores"][0]["factor_evidence"]["factor_contributions"]
    assert payload["factor_contribution_summary"] == report.factor_contribution_summary


def test_manual_style_report_serializes_real_provider_metadata_and_notes(tmp_path: Path) -> None:
    artifact_path = tmp_path / "manual" / "latest_report.json"

    report = run_factor_ranking_baseline_v1(
        factor_fixture_frame(),
        FactorRankingBaselineConfig(
            ranking_mode="defensive_composite_v1",
            target_symbol_count=2,
            artifact_path=artifact_path,
            metadata={
                "provider": "baostock",
                "date_range": ("2023-01-01", "2024-12-31"),
                "symbols_requested": ("000001.SZ", "000002.SZ", "000003.SZ"),
                "ranking_modes": FACTOR_RANKING_BASELINE_MODES,
                "run_context": "manual_real_provider",
            },
        ),
    )

    payload = json.loads(artifact_path.read_text(encoding="utf-8"))
    assert report.provider == "baostock"
    assert report.date_range == ("2023-01-01", "2024-12-31")
    assert report.symbols_requested == ("000001.SZ", "000002.SZ", "000003.SZ")
    assert payload["provider"] == "baostock"
    assert payload["date_range"] == ["2023-01-01", "2024-12-31"]
    assert payload["symbols_requested"] == ["000001.SZ", "000002.SZ", "000003.SZ"]
    assert payload["valid_symbols"] == list(report.valid_symbols)
    assert payload["ranking_modes"] == list(FACTOR_RANKING_BASELINE_MODES)
    assert payload["ranking_mode"] == "defensive_composite_v1"
    assert payload["artifact_path"] == str(artifact_path)
    assert "manual_only_real_provider_run" in payload["notes"]
    assert "no_external_network_in_tests" in payload["notes"]
    assert "offline_fixture_safe" not in payload["notes"]
    assert "no_external_network" not in payload["notes"]


def test_factor_modes_are_available_to_scaleup_selector_for_future_sweep_use() -> None:
    selected = scaleup_module._select_scaleup_candidates(
        factor_fixture_frame(),
        {"000001.SZ": 10.0, "000002.SZ": 10.0, "000003.SZ": 10.0, "000004.SZ": 10.0, "000005.SZ": 10.0},
        RealDataWalkForwardScaleupConfig(
            target_position_count=2,
            ranking_mode="defensive_composite_v1",
            artifact_path=None,
        ),
    )

    assert selected == ("000001.SZ", "000005.SZ")
    assert set(FACTOR_RANKING_BASELINE_MODES) <= set(scaleup_module.SUPPORTED_REAL_DATA_SCALEUP_RANKING_MODES)


def test_factor_fixture_run_uses_no_external_network_llm_or_broker(monkeypatch: pytest.MonkeyPatch) -> None:
    def fail_deepseek(*args, **kwargs):
        raise AssertionError("DeepSeek advisory must not run in factor baseline tests")

    def fail_provider_constructor(*args, **kwargs):
        raise AssertionError("real provider constructor must not be used")

    monkeypatch.setattr("quantpilot_core.walk_forward.engine.run_deepseek_advisory_fallback", fail_deepseek)
    monkeypatch.setattr(
        "quantpilot_core.evaluation.real_data_walk_forward_smoke.BaoStockDailyBarProvider",
        fail_provider_constructor,
    )
    monkeypatch.setattr(
        "quantpilot_core.evaluation.real_data_walk_forward_smoke.AkShareDailyBarProvider",
        fail_provider_constructor,
    )

    report = run_factor_ranking_baseline_v1(
        factor_fixture_frame(),
        FactorRankingBaselineConfig(ranking_mode="defensive_composite_v1", target_symbol_count=2),
    )

    assert report.selected_symbols
    assert "no_broker_live_execution" in report.notes
    assert "deepseek_live_disabled" in report.notes
    assert "no_external_network_in_tests" in report.notes
