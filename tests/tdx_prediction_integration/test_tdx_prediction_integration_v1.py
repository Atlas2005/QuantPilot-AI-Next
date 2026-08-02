from __future__ import annotations

import csv
import json
from dataclasses import replace
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Mapping, Sequence
from zoneinfo import ZoneInfo

import pytest

from quantpilot_core.real_data_provider import (
    NormalizedIntradayBar,
    NormalizedLevel1Event,
)
from quantpilot_core.tdx_manual_signal_bridge import (
    TDX_PREDICTION_SIGNAL_CSV_HEADER,
    write_prediction_signals_atomic,
)
from quantpilot_core.tdx_prediction_integration import (
    LiveShadowPredictionSink,
    PredictionContext,
    PredictionEngineConfig,
    ReplayConfig,
    TDXPredictionEngineV1,
    cached_deepseek_evidence_from_payload,
    candidate_context_from_report,
    prediction_signal_record,
    run_historical_replay,
)
from scripts.publish_tdx_signals_tq_v1 import (
    PREDICTION_STATE_CODE,
    PREDICTION_TQ_COLUMN_SPEC,
    prediction_signal_to_tq_row,
    publish_to_tq,
)


SHANGHAI = ZoneInfo("Asia/Shanghai")


def _minute_bars(*, include_second_day: bool = True) -> tuple[NormalizedIntradayBar, ...]:
    rows: list[NormalizedIntradayBar] = []
    price = 10.0
    days = ((datetime(2026, 8, 3, 9, 30, tzinfo=SHANGHAI), 120),)
    if include_second_day:
        days += ((datetime(2026, 8, 4, 9, 30, tzinfo=SHANGHAI), 70),)
    ordinal = 0
    for start, count in days:
        for minute in range(count):
            opened = price
            if ordinal < 70:
                price *= 1.0015
            elif ordinal < 120:
                price *= 0.997
            else:
                price *= 1.0002
            closed = round(price, 6)
            rows.append(
                NormalizedIntradayBar(
                    symbol="000001.SZ",
                    start=start + timedelta(minutes=minute),
                    end=start + timedelta(minutes=minute + 1),
                    interval_minutes=1,
                    open=round(opened, 6),
                    high=round(max(opened, closed) * 1.0005, 6),
                    low=round(min(opened, closed) * 0.9995, 6),
                    close=closed,
                    volume=10_000.0,
                    amount=10_000.0 * closed,
                    average_price=closed,
                    event_count=1,
                )
            )
            ordinal += 1
    return tuple(rows)


def _engine(*, context: PredictionContext | None = None) -> TDXPredictionEngineV1:
    return TDXPredictionEngineV1(
        ("000001.SZ",),
        config=PredictionEngineConfig(
            feature_interval_minutes=5,
            min_feature_bars=11,
        ),
        context=context,
    )


def test_engine_reuses_tdx_symbol_normalization() -> None:
    engine = TDXPredictionEngineV1(("000001", "SZ000001", "000001.SZ"))

    assert engine.symbols == ("000001.SZ",)


def _candidate_report() -> Mapping[str, Any]:
    candidate = {
        "symbol": "000001.SZ",
        "direction": "long",
        "confidence": 0.8,
        "risk_score": 0.2,
        "liquidity_score": 0.9,
        "metadata": {
            "candidate_id": "daily:000001.SZ",
            "factor_rank": 1,
            "factor_composite_score_raw": 0.75,
        },
    }
    return {
        "decision_session": "2026-08-03",
        "candidate_report": {"candidates": [candidate]},
        "quant_firm_input_candidate_report": {"candidates": [candidate]},
        "ledger_after": {"positions": {}, "sellable_quantities": {}},
    }


def _cached_evidence() -> Mapping[str, Any]:
    return {
        "findings": [
            {
                "symbol": "000001.SZ",
                "data_asof": "2026-08-03T09:00:00+08:00",
                "role": "factor_agent",
                "summary": "Cached factor-desk evidence.",
                "confidence": 0.7,
                "evidence_refs": ["cache:factor:1"],
                "risk_flags": [],
            }
        ]
    }


def test_completed_higher_timeframes_only_and_probability_bounds() -> None:
    bars = _minute_bars(include_second_day=False)
    engine = _engine()

    assert engine.process_completed_bars(bars[:54]) == ()
    emitted = engine.process_completed_bars((bars[54],))

    assert emitted
    signal = emitted[0]
    assert signal.decision_timestamp == bars[54].end.isoformat()
    assert signal.data_cutoff_timestamp == signal.decision_timestamp
    assert 0 <= signal.entry_probability <= 1
    assert 0 <= signal.continuation_probability <= 1
    assert 0 <= signal.exit_probability <= 1
    assert signal.calibration_label.startswith("deterministic_untrained")


def test_future_bar_mutation_does_not_change_earlier_predictions() -> None:
    bars = _minute_bars(include_second_day=False)
    cutoff = bars[89].end
    changed = tuple(
        replace(
            bar,
            open=bar.open * 1.2,
            high=bar.high * 1.2,
            low=bar.low * 1.2,
            close=bar.close * 1.2,
            amount=bar.amount * 1.2,
            average_price=bar.average_price * 1.2 if bar.average_price else None,
        )
        if index >= 90 else bar
        for index, bar in enumerate(bars)
    )

    first = _engine()
    second = _engine()
    first.process_completed_bars(bars)
    second.process_completed_bars(changed)

    first_prefix = [
        signal.as_dict()
        for signal in first.all_predictions
        if datetime.fromisoformat(signal.decision_timestamp) <= cutoff
    ]
    second_prefix = [
        signal.as_dict()
        for signal in second.all_predictions
        if datetime.fromisoformat(signal.decision_timestamp) <= cutoff
    ]
    assert first_prefix == second_prefix


def test_material_state_change_deduplication_is_idempotent() -> None:
    bars = _minute_bars(include_second_day=False)
    engine = _engine()

    first = engine.process_completed_bars(bars)
    second = engine.process_completed_bars(tuple(reversed(bars)))

    assert first
    assert second == ()
    assert len(engine.material_signals) <= len(engine.all_predictions)
    assert any(not signal.material_change for signal in engine.all_predictions)


def test_daily_candidate_and_cached_deepseek_evidence_enrich_without_live_calls() -> None:
    context = PredictionContext(
        candidates=candidate_context_from_report(_candidate_report()),
        deepseek_evidence=cached_deepseek_evidence_from_payload(_cached_evidence()),
        deepseek_live_calls_enabled=False,
    )
    engine = _engine(context=context)
    engine.process_completed_bars(_minute_bars())

    assert engine.material_signals
    signal = next(
        item
        for item in engine.material_signals
        if "daily_candidate_prior_present" in item.reason_codes
    )
    assert "daily_candidate_prior_present" in signal.reason_codes
    assert "cached_deepseek_evidence_present" in signal.reason_codes
    assert "cache:factor:1" in signal.evidence_refs
    assert signal.context_data_asofs == (
        "2026-08-03T15:00:00+08:00",
        "2026-08-03T09:00:00+08:00",
    )
    assert any("tdx_manual_signal_bridge" in item for item in signal.source_components)


def test_future_or_undated_cached_evidence_cannot_leak_into_earlier_predictions() -> None:
    context = PredictionContext(
        deepseek_evidence=cached_deepseek_evidence_from_payload(
            {
                "findings": [
                    {
                        "symbol": "000001.SZ",
                        "data_asof": "2026-08-04T09:00:00+08:00",
                        "role": "factor_agent",
                        "summary": "Future evidence.",
                        "confidence": 0.7,
                        "evidence_refs": ["cache:future"],
                        "risk_flags": [],
                    },
                    {
                        "symbol": "000001.SZ",
                        "role": "risk_agent",
                        "summary": "Undated evidence.",
                        "confidence": 0.7,
                        "evidence_refs": ["cache:undated"],
                        "risk_flags": [],
                    },
                ]
            }
        )
    )
    engine = _engine(context=context)

    engine.process_completed_bars(_minute_bars(include_second_day=False))

    assert engine.material_signals
    assert all(
        "cached_deepseek_evidence_present" not in signal.reason_codes
        for signal in engine.material_signals
    )


def test_daily_candidate_is_not_available_before_existing_decision_cutoff() -> None:
    report = dict(_candidate_report())
    report["decision_session"] = "2026-08-04"
    context = PredictionContext(candidates=candidate_context_from_report(report))
    engine = _engine(context=context)

    engine.process_completed_bars(_minute_bars(include_second_day=False))

    assert engine.material_signals
    assert all(
        "daily_candidate_prior_present" not in signal.reason_codes
        for signal in engine.material_signals
    )


def test_replay_separates_prediction_execution_profitability_and_t_plus_one() -> None:
    bars = _minute_bars()
    result = run_historical_replay(
        bars,
        _engine(),
        config=ReplayConfig(initial_cash=100_000.0, order_quantity=100),
    )

    report = result.report
    assert report["prediction_evaluation"]["prediction_correctness_is_separate_from_execution"] is True
    assert "trade_executability" in report
    assert "net_profitability" in report
    assert report["no_lookahead_audit"]["passed"] is True
    assert report["trade_executability"]["next_bar_execution_only"] is True
    assert report["trade_executability"]["t_plus_one_rejection_count"] >= 1
    assert report["trade_executability"]["executable_signal_count"] >= 2
    assert report["net_profitability"]["transaction_cost_total"] > 0
    assert all(
        datetime.fromisoformat(row["execution_timestamp"])
        >= datetime.fromisoformat(row["prediction_decision_timestamp"])
        for row in result.execution_outcomes
    )
    first_attempt_by_decision: dict[str, datetime] = {}
    for row in result.execution_outcomes:
        decision = str(row["prediction_decision_timestamp"])
        executed = datetime.fromisoformat(str(row["execution_timestamp"]))
        first_attempt_by_decision[decision] = min(
            executed,
            first_attempt_by_decision.get(decision, executed),
        )
    for decision_timestamp, first_attempt in first_attempt_by_decision.items():
        decision = datetime.fromisoformat(decision_timestamp)
        expected = next(bar.start for bar in bars if bar.start >= decision)
        assert first_attempt == expected


def test_replay_is_deterministic() -> None:
    bars = _minute_bars()
    first = run_historical_replay(bars, _engine())
    second = run_historical_replay(bars, _engine())

    assert first.report["deterministic_digest"] == second.report["deterministic_digest"]
    assert [item.as_dict() for item in first.material_signals] == [
        item.as_dict() for item in second.material_signals
    ]


class _RecordingStore:
    def __init__(self) -> None:
        self.calls: list[tuple[Sequence[NormalizedLevel1Event], Sequence[NormalizedIntradayBar]]] = []

    def persist_market_data(self, events, bars) -> None:
        self.calls.append((tuple(events), tuple(bars)))


def test_replay_and_live_shadow_sink_use_the_same_prediction_engine(tmp_path: Path) -> None:
    bars = _minute_bars(include_second_day=False)
    replay_engine = _engine()
    replay_engine.process_completed_bars(bars)
    live_engine = _engine()
    store = _RecordingStore()
    sink = LiveShadowPredictionSink(store, live_engine, output_dir=str(tmp_path))

    sink.prime(bars)

    assert [item.as_dict() for item in live_engine.all_predictions] == [
        item.as_dict() for item in replay_engine.all_predictions
    ]
    assert sink.report()["broker_or_order_api_calls"] is False
    assert sink.report()["deepseek_live_calls"] is False
    assert Path(sink.report()["tdx_json_path"]).exists()


def test_tdx_prediction_export_and_existing_tq_bridge_schema(tmp_path: Path) -> None:
    engine = _engine()
    engine.process_completed_bars(_minute_bars(include_second_day=False))
    record = prediction_signal_record(engine.material_signals[0])

    json_path, csv_path = write_prediction_signals_atomic((record,), tmp_path)
    payload = json.loads(Path(json_path).read_text(encoding="utf-8"))
    with Path(csv_path).open(encoding="utf-8", newline="") as handle:
        csv_rows = list(csv.reader(handle))
    tq_row = prediction_signal_to_tq_row(record)
    dry_run = publish_to_tq((record,), dry_run=True)

    assert payload[0]["state"] in PREDICTION_STATE_CODE
    assert payload[0]["reason_code"]
    assert csv_rows[0] == list(TDX_PREDICTION_SIGNAL_CSV_HEADER)
    assert len(tq_row) == 16
    assert tq_row[2] == round(record["entry_probability"] * 100)
    assert dry_run["column_spec"] == {
        column: name for column, name, _kind in PREDICTION_TQ_COLUMN_SPEC
    }


def test_live_deepseek_configuration_is_rejected() -> None:
    with pytest.raises(ValueError, match="does not permit live DeepSeek"):
        _engine(context=PredictionContext(deepseek_live_calls_enabled=True))
