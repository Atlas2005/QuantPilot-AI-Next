from __future__ import annotations

import sys
from pathlib import Path

import pytest

from quantpilot_core.ai_open_source_provider_small_sample_mixed_etf_replay import (
    AIShadowAgentRecommendation,
    AIShadowAgentRole,
    OpenSourceProviderExportSpec,
    OpenSourceProviderName,
    ProviderExportSourceType,
    build_ai_adjusted_replay_result,
    build_open_source_backtest_handoffs,
    build_p40_ai_provider_replay_report,
    build_replay_adjustment_plan,
    generate_ai_shadow_decision_set,
    meta_review_shadow_recommendations,
    summarize_ai_adjusted_replay_impact,
    validate_approved_provider_export,
)
from quantpilot_core.provider_vectorbt_replay import (
    replay_provider_mixed_etf_sample_with_vectorbt,
)
from quantpilot_core.vectorbt_replay_adapter import VectorbtReplayResult, VectorbtReplayStatus


def schema_mapping() -> dict[str, str]:
    return {
        "symbol": "symbol",
        "trade_date": "trade_date",
        "instrument_type": "instrument_type",
        "open": "open",
        "high": "high",
        "low": "low",
        "close": "close",
        "volume": "volume",
        "etf_category": "etf_category",
    }


def sample_records() -> tuple[dict[str, object], ...]:
    rows: list[dict[str, object]] = []
    for trade_date, stock_close, etf_close in (
        ("2026-01-02", 10.0, 2.0),
        ("2026-01-05", 10.2, 2.02),
        ("2026-01-06", 10.3, 2.04),
    ):
        rows.append(
            {
                "symbol": "000001.SZ",
                "trade_date": trade_date,
                "instrument_type": "stock",
                "open": stock_close,
                "high": round(stock_close * 1.02, 4),
                "low": round(stock_close * 0.98, 4),
                "close": stock_close,
                "volume": 1_000_000,
            }
        )
        rows.append(
            {
                "symbol": "510300.SH",
                "trade_date": trade_date,
                "instrument_type": "etf",
                "etf_category": "equity_etf",
                "open": etf_close,
                "high": round(etf_close * 1.02, 4),
                "low": round(etf_close * 0.98, 4),
                "close": etf_close,
                "volume": 5_000_000,
            }
        )
    return tuple(rows)


def export_spec(
    provider: str = OpenSourceProviderName.AKSHARE.value,
    source_uri: str = "fixtures/p40/approved_export",
) -> OpenSourceProviderExportSpec:
    return OpenSourceProviderExportSpec(
        provider_name=provider,
        source_type=ProviderExportSourceType.DETERMINISTIC_FIXTURE.value,
        source_uri=source_uri,
        approved_by="qa_reviewer",
        approval_reason="approved deterministic small sample",
        export_timestamp="2026-01-07T00:00:00",
        provider_schema_mapping=schema_mapping(),
        evaluation_start="2026-01-02",
        evaluation_end="2026-01-06",
        initial_cash=100_000.0,
        evidence_refs=("evidence://p40/spec",),
    )


def completed_vectorbt_runner(_input_data) -> VectorbtReplayResult:
    return VectorbtReplayResult(
        status=VectorbtReplayStatus.COMPLETED.value,
        reason="completed",
        equity_curve=(100_000.0, 100_300.0, 100_250.0),
        total_return=0.0025,
        max_drawdown=0.0005,
        trade_count=3,
        turnover_proxy=0.5,
        warnings=(),
    )


def provider_vectorbt_replay_result():
    validation = validate_approved_provider_export(export_spec(), sample_records())
    assert validation.replay_input is not None
    return replay_provider_mixed_etf_sample_with_vectorbt(
        validation.replay_input,
        replay_runner=completed_vectorbt_runner,
    )


def test_akshare_export_boundary_accepted_without_importing_package() -> None:
    result = validate_approved_provider_export(export_spec(OpenSourceProviderName.AKSHARE.value), sample_records())

    assert result.ok is True
    assert result.provider_name == OpenSourceProviderName.AKSHARE.value
    assert "provider_boundary:akshare" in result.quality_flags
    assert "akshare" not in sys.modules


def test_baostock_export_boundary_accepted_without_importing_package() -> None:
    result = validate_approved_provider_export(export_spec(OpenSourceProviderName.BAOSTOCK.value), sample_records())

    assert result.ok is True
    assert result.provider_name == OpenSourceProviderName.BAOSTOCK.value
    assert "provider_boundary:baostock" in result.quality_flags
    assert "baostock" not in sys.modules


def test_manual_approved_export_accepted() -> None:
    spec = export_spec(OpenSourceProviderName.MANUAL_APPROVED_EXPORT.value)
    spec = OpenSourceProviderExportSpec(
        provider_name=spec.provider_name,
        source_type=ProviderExportSourceType.LOCAL_CSV_EXPORT.value,
        source_uri=spec.source_uri,
        approved_by=spec.approved_by,
        approval_reason=spec.approval_reason,
        export_timestamp=spec.export_timestamp,
        provider_schema_mapping=spec.provider_schema_mapping,
        evaluation_start=spec.evaluation_start,
        evaluation_end=spec.evaluation_end,
        initial_cash=spec.initial_cash,
        evidence_refs=spec.evidence_refs,
    )

    result = validate_approved_provider_export(spec, sample_records())

    assert result.ok is True
    assert result.provider_name == OpenSourceProviderName.MANUAL_APPROVED_EXPORT.value


@pytest.mark.parametrize(
    "field,expected",
    (
        ("approved_by", "approved_by_missing"),
        ("approval_reason", "approval_reason_missing"),
        ("export_timestamp", "export_timestamp_missing"),
    ),
)
def test_missing_approval_metadata_rejected(field: str, expected: str) -> None:
    spec = export_spec()
    values = spec.__dict__ | {field: ""}
    result = validate_approved_provider_export(OpenSourceProviderExportSpec(**values), sample_records())

    assert result.ok is False
    assert expected in result.blockers


def test_remote_url_source_rejected() -> None:
    result = validate_approved_provider_export(
        export_spec(source_uri="https://example.invalid/export.csv"),
        sample_records(),
    )

    assert result.ok is False
    assert "remote_source_rejected" in result.blockers


def test_stock_and_etf_coverage_required() -> None:
    rows = tuple(row for row in sample_records() if row["instrument_type"] == "stock")

    result = validate_approved_provider_export(export_spec(), rows)

    assert result.ok is False
    assert "etf_coverage_missing" in result.blockers


def test_etf_category_required() -> None:
    rows = [dict(row) for row in sample_records()]
    for row in rows:
        row.pop("etf_category", None)

    result = validate_approved_provider_export(export_spec(), tuple(rows))

    assert result.ok is False
    assert "etf_category_missing:510300.SH" in result.blockers


def test_ohlcv_like_fields_required() -> None:
    rows = [dict(row) for row in sample_records()]
    rows[0].pop("open")

    result = validate_approved_provider_export(export_spec(), tuple(rows))

    assert result.ok is False
    assert "missing_ohlcv_fields:0:open" in result.blockers


def test_duplicate_symbol_date_rejected() -> None:
    rows = (*sample_records(), dict(sample_records()[0]))

    result = validate_approved_provider_export(export_spec(), rows)

    assert result.ok is False
    assert "duplicate_symbol_date:000001.SZ:2026-01-02" in result.blockers


def test_future_rows_rejected() -> None:
    rows = [dict(row) for row in sample_records()]
    rows[-1]["trade_date"] = "2026-01-08"

    result = validate_approved_provider_export(export_spec(), tuple(rows))

    assert result.ok is False
    assert "future_dated_row:510300.SH:2026-01-08" in result.blockers


def test_missing_close_and_volume_rejected() -> None:
    rows = [dict(row) for row in sample_records()]
    rows[0]["close"] = None
    rows[1]["volume"] = 0

    result = validate_approved_provider_export(export_spec(), tuple(rows))

    assert result.ok is False
    assert "non_numeric_close:0" in result.blockers
    assert "missing_volume:1" in result.blockers


def test_provider_schema_mapping_explicit() -> None:
    result = validate_approved_provider_export(export_spec(), sample_records())

    assert result.ok is True
    assert "provider_schema_mapping_explicit" in result.quality_flags


def test_all_required_ai_shadow_agent_roles_produce_recommendations() -> None:
    validation = validate_approved_provider_export(export_spec(), sample_records())
    decisions = generate_ai_shadow_decision_set(validation, provider_vectorbt_replay_result())

    assert tuple(item.role for item in decisions.recommendations) == tuple(
        role.value for role in AIShadowAgentRole
    )
    assert decisions.deterministic_shadow_mode is True


def test_recommendations_are_structured_and_deterministic() -> None:
    validation = validate_approved_provider_export(export_spec(), sample_records())
    first = generate_ai_shadow_decision_set(validation, provider_vectorbt_replay_result())
    second = generate_ai_shadow_decision_set(validation, provider_vectorbt_replay_result())

    assert first == second
    assert all(0 <= item.confidence <= 1 for item in first.recommendations)
    assert all(item.evidence_refs for item in first.recommendations)


def test_meta_review_blocks_profitability_claims() -> None:
    decisions = meta_review_shadow_recommendations((unsafe_recommendation("guaranteed_profit"),))

    assert "alpha_research" in decisions.meta_blocked_roles
    assert "unsupported_profitability_claim" in decisions.unsafe_reasons


def test_meta_review_blocks_live_trading_suggestions() -> None:
    decisions = meta_review_shadow_recommendations((unsafe_recommendation("live_trade"),))

    assert "live_trading_suggestion" in decisions.unsafe_reasons


def test_meta_review_blocks_cost_blind_suggestions() -> None:
    decisions = meta_review_shadow_recommendations((unsafe_recommendation("ignore_cost"),))

    assert "cost_blind_suggestion" in decisions.unsafe_reasons


def test_replay_adjustment_plan_uses_bounded_position_size_multiplier() -> None:
    validation = validate_approved_provider_export(export_spec(), sample_records())
    decisions = generate_ai_shadow_decision_set(validation, provider_vectorbt_replay_result())
    plan = build_replay_adjustment_plan(decisions, provider_vectorbt_replay_result())

    assert 0.5 <= plan.position_size_multiplier <= 1.5
    assert plan.position_size_multiplier == 1.0333
    assert plan.etf_preference_delta == 0.25


def test_forbidden_adjustments_are_rejected() -> None:
    decisions = meta_review_shadow_recommendations((unsafe_recommendation("broker_connect"),))
    plan = build_replay_adjustment_plan(decisions, provider_vectorbt_replay_result())

    assert "live_trading_suggestion" in plan.forbidden_adjustments_rejected
    assert "broker_connect" in plan.forbidden_adjustments_rejected


def test_baseline_versus_ai_shadow_adjusted_replay_comparison_computed() -> None:
    validation = validate_approved_provider_export(export_spec(), sample_records())
    decisions = generate_ai_shadow_decision_set(validation, provider_vectorbt_replay_result())
    adjusted = build_ai_adjusted_replay_result(provider_vectorbt_replay_result(), decisions)

    assert adjusted.ai_adjustment_improved_paper_metrics is True
    assert adjusted.mixed_stock_etf_remains_default is True


def test_adjusted_replay_deltas_computed() -> None:
    report = build_p40_ai_provider_replay_report(
        export_spec(),
        sample_records(),
        replay_runner=completed_vectorbt_runner,
    )
    adjusted = report.ai_adjusted_replay

    assert adjusted.fill_rate_delta == 0.0
    assert adjusted.zero_trade_day_delta == 0
    assert adjusted.capital_usage_delta == 0.01665
    assert adjusted.cost_drag_delta == 0.0
    assert adjusted.net_pnl_after_cost_delta == 2.5001
    assert adjusted.turnover_delta == 0.000333
    assert summarize_ai_adjusted_replay_impact(adjusted)[0] == "fill_rate_delta:0.0"


def test_qlib_and_rqalpha_handoff_metadata_produced() -> None:
    validation = validate_approved_provider_export(export_spec(), sample_records())
    qlib_handoff, rqalpha_handoff = build_open_source_backtest_handoffs(export_spec(), validation)

    assert qlib_handoff.target == "qlib_offline_ai_quant_backtest"
    assert rqalpha_handoff.target == "rqalpha_later_event_driven_backtest"
    assert qlib_handoff.stock_count == 1
    assert qlib_handoff.etf_count == 1
    assert qlib_handoff.runtime_disabled_by_default is True
    assert rqalpha_handoff.runtime_disabled_by_default is True


def test_safety_barrier_remains_at_or_below_140() -> None:
    report = build_p40_ai_provider_replay_report(
        export_spec(),
        sample_records(),
        safety_barrier_percent=185.0,
        replay_runner=completed_vectorbt_runner,
    )

    assert report.safety_barrier_percent <= 140.0


def test_deterministic_report_ordering() -> None:
    report = build_p40_ai_provider_replay_report(
        export_spec(),
        sample_records(),
        replay_runner=completed_vectorbt_runner,
    )

    assert tuple(item.role for item in report.ai_shadow_decisions.recommendations) == tuple(
        role.value for role in AIShadowAgentRole
    )
    assert report.evidence_refs == ("evidence://p40/spec",)


def test_report_answers_p40_questions() -> None:
    report = build_p40_ai_provider_replay_report(
        export_spec(),
        sample_records(),
        replay_runner=completed_vectorbt_runner,
    )

    assert report.used_approved_local_provider_export_style_data is True
    assert report.provider_boundary_modeled == OpenSourceProviderName.AKSHARE.value
    assert report.ai_shadow_agents_produced_recommendations is True
    assert report.ai_shadow_adjustment_improved_paper_metrics is True
    assert report.mixed_stock_etf_remained_useful is True
    assert report.created_open_source_backtest_handoffs is True
    assert report.next_improvement_target == "Qlib backtest"


def test_no_forbidden_runtime_behavior() -> None:
    package_root = Path("src/quantpilot_core/ai_open_source_provider_small_sample_mixed_etf_replay")
    source_text = "\n".join(path.read_text() for path in sorted(package_root.glob("*.py")))

    forbidden_fragments = (
        "requests.",
        "connect_broker(",
        "place_order(",
        "send_order(",
        "submit_order(",
        "execute_order(",
        "api_key",
        "access_token",
        "qrun",
    )
    assert not any(fragment in source_text for fragment in forbidden_fragments)
    assert "akshare" not in sys.modules
    assert "baostock" not in sys.modules
    assert "qlib" not in sys.modules
    assert "rqalpha" not in sys.modules


def test_report_module_does_not_import_legacy_provider_replay_defaults() -> None:
    report_source = Path(
        "src/quantpilot_core/ai_open_source_provider_small_sample_mixed_etf_replay/report.py"
    ).read_text(encoding="utf-8")

    assert "build_provider_mixed_etf_replay_report" not in report_source
    assert "replay_provider_mixed_etf_sample(" not in report_source
    assert "replay_provider_mixed_etf_sample," not in report_source
    assert "replay_provider_mixed_etf_sample_with_vectorbt" in report_source


def unsafe_recommendation(marker: str) -> AIShadowAgentRecommendation:
    return AIShadowAgentRecommendation(
        role=AIShadowAgentRole.ALPHA_RESEARCH.value,
        recommended_universe_adjustment=marker,
        recommended_etf_weight_adjustment=0.5,
        recommended_position_size_adjustment=2.0,
        recommended_alpha_adjustment=marker,
        cost_warning=marker,
        risk_warning=marker,
        recommended_next_action=marker,
        confidence=0.99,
        evidence_refs=("evidence://p40/unsafe",),
        blocked_by=(),
        agent_notes=(marker,),
    )
