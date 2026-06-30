from __future__ import annotations

import sys
from pathlib import Path

from quantpilot_core.real_provider_mixed_etf_paper_replay import (
    ProviderSampleSourceType,
    RealProviderReplayInput,
    build_provider_mixed_etf_replay_report,
    compare_provider_replay_to_p38_baseline,
    evaluate_provider_capital_path_suitability,
    replay_provider_mixed_etf_sample,
    validate_provider_mixed_universe_sample,
)


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


def valid_input(records: tuple[dict[str, object], ...] | None = None) -> RealProviderReplayInput:
    return RealProviderReplayInput(
        sample_source_type=ProviderSampleSourceType.FIXTURE.value,
        sample_source_uri="fixtures/p39/provider_mixed_sample",
        evaluation_start="2026-01-02",
        evaluation_end="2026-01-06",
        initial_cash=100_000.0,
        records=records or sample_records(),
        evidence_refs=("evidence://p39/sample",),
    )


def test_local_fixture_provider_sample_accepted() -> None:
    result = validate_provider_mixed_universe_sample(valid_input())

    assert result.ok is True
    assert result.blockers == ()
    assert result.sample is not None
    assert result.sample.stock_symbols == ("000001.SZ",)
    assert result.sample.etf_symbols == ("510300.SH",)


def test_remote_provider_url_source_rejected() -> None:
    replay_input = RealProviderReplayInput(
        sample_source_type=ProviderSampleSourceType.PROVIDER_GATED_SAMPLE.value,
        sample_source_uri="https://example.invalid/provider.csv",
        evaluation_start="2026-01-02",
        evaluation_end="2026-01-06",
        initial_cash=100_000.0,
        records=sample_records(),
    )

    result = validate_provider_mixed_universe_sample(replay_input)

    assert result.ok is False
    assert "sample_source_uri_remote" in result.blockers


def test_missing_etf_category_rejected() -> None:
    rows = [dict(row) for row in sample_records()]
    for row in rows:
        if row["instrument_type"] == "etf":
            row.pop("etf_category", None)

    result = validate_provider_mixed_universe_sample(valid_input(tuple(rows)))

    assert result.ok is False
    assert "etf_category_missing:510300.SH" in result.blockers


def test_missing_ohlcv_field_rejected() -> None:
    rows = [dict(row) for row in sample_records()]
    rows[0].pop("open")

    result = validate_provider_mixed_universe_sample(valid_input(tuple(rows)))

    assert result.ok is False
    assert "missing_required_fields:0:open" in result.blockers


def test_duplicate_symbol_date_rejected() -> None:
    rows = (*sample_records(), dict(sample_records()[0]))

    result = validate_provider_mixed_universe_sample(valid_input(rows))

    assert result.ok is False
    assert "duplicate_symbol_date:000001.SZ:2026-01-02" in result.blockers


def test_unsorted_dates_rejected() -> None:
    rows = tuple(reversed(sample_records()))

    result = validate_provider_mixed_universe_sample(valid_input(rows))

    assert result.ok is False
    assert "trade_dates_unsorted" in result.blockers


def test_future_dated_rows_rejected() -> None:
    rows = [dict(row) for row in sample_records()]
    rows[-1]["trade_date"] = "2026-01-07"

    result = validate_provider_mixed_universe_sample(valid_input(tuple(rows)))

    assert result.ok is False
    assert "future_dated_row:510300.SH:2026-01-07" in result.blockers


def test_missing_close_and_volume_rejected() -> None:
    rows = [dict(row) for row in sample_records()]
    rows[0]["close"] = None
    rows[1]["volume"] = 0

    result = validate_provider_mixed_universe_sample(valid_input(tuple(rows)))

    assert result.ok is False
    assert "missing_close:0" in result.blockers
    assert "missing_volume:1" in result.blockers


def test_mixed_stock_etf_sample_required_for_mixed_replay() -> None:
    rows = tuple(row for row in sample_records() if row["instrument_type"] == "stock")

    result = validate_provider_mixed_universe_sample(valid_input(rows))

    assert result.ok is False
    assert "etf_sample_missing" in result.blockers


def test_provider_replay_produces_order_intents() -> None:
    replay = replay_provider_mixed_etf_sample(valid_input())

    assert replay.order_intent_count_total == 4


def test_provider_replay_produces_simulated_fills() -> None:
    replay = replay_provider_mixed_etf_sample(valid_input())

    assert replay.simulated_fill_count_total == 4


def test_fill_rate_computed() -> None:
    replay = replay_provider_mixed_etf_sample(valid_input())

    assert replay.fill_rate == 1.0


def test_zero_trade_reasons_reported() -> None:
    replay = replay_provider_mixed_etf_sample(valid_input())

    assert replay.zero_trade_day_count == 0
    assert replay.zero_trade_reason_distribution == {}


def test_cost_tax_slippage_reported() -> None:
    replay = replay_provider_mixed_etf_sample(valid_input())

    assert replay.cost_tax_slippage_total == 5.209


def test_net_pnl_after_cost_reported() -> None:
    report = build_provider_mixed_etf_replay_report(valid_input())

    assert report.provider_replay.net_pnl_after_cost == 37.0788
    assert report.pnl_sign == "positive"


def test_comparison_vs_p38_baseline_computed() -> None:
    replay = replay_provider_mixed_etf_sample(valid_input())
    notes = compare_provider_replay_to_p38_baseline(replay)

    assert "fill_rate_delta_vs_p38:0.0" in notes
    assert "net_pnl_after_cost_delta_vs_p38:0.0" in notes
    assert "data_quality_no_blockers" in notes


def test_capital_path_suitability_reported() -> None:
    replay = replay_provider_mixed_etf_sample(valid_input())
    suitability = evaluate_provider_capital_path_suitability(replay)

    assert tuple(item.stage_capital_cny for item in suitability) == (1_000, 10_000, 100_000)
    assert all(item.etf_inclusion_helps for item in suitability)
    assert all(item.recommend_mixed_default for item in suitability)


def test_safety_barrier_remains_at_or_below_140() -> None:
    report = build_provider_mixed_etf_replay_report(valid_input(), safety_barrier_percent=185.0)

    assert report.safety_barrier_percent <= 140.0


def test_deterministic_report_ordering() -> None:
    report = build_provider_mixed_etf_replay_report(valid_input())

    assert report.provider_replay.validation.sample is not None
    assert report.provider_replay.validation.sample.trading_days == (
        "2026-01-02",
        "2026-01-05",
        "2026-01-06",
    )
    assert tuple(item.stage_capital_cny for item in report.capital_path_suitability) == (
        1_000,
        10_000,
        100_000,
    )
    assert report.evidence_refs == ("evidence://p39/sample",)


def test_report_answers_provider_replay_questions() -> None:
    report = build_provider_mixed_etf_replay_report(valid_input())

    assert report.provider_sample_includes_stock_and_etf is True
    assert report.replay_produced_simulated_fills is True
    assert report.fill_rate_positive is True
    assert report.zero_trade_days_explained is True
    assert report.data_quality_blocked_replay is False
    assert report.etf_inclusion_remained_useful is True
    assert report.next_improvement_target == "daily loop realism"


def test_no_forbidden_runtime_behavior() -> None:
    package_root = Path("src/quantpilot_core/real_provider_mixed_etf_paper_replay")
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
    assert "qlib" not in sys.modules
