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
    normalize_tdx_historical_minute_bars,
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
    compute_intraday_features_v1,
    prediction_signal_record,
    run_historical_replay,
)
from quantpilot_core.tdx_prediction_integration.replay import _no_lookahead_audit
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
            min_feature_bars=15,
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

    assert engine.process_completed_bars(bars[:74]) == ()
    emitted = engine.process_completed_bars((bars[74],))

    assert emitted
    signal = emitted[0]
    assert signal.decision_timestamp == bars[74].end.isoformat()
    assert signal.data_cutoff_timestamp == signal.decision_timestamp
    assert 0 <= signal.entry_probability <= 1
    assert 0 <= signal.continuation_probability <= 1
    assert 0 <= signal.exit_probability <= 1
    assert signal.calibration_label.startswith("deterministic_untrained")
    assert "factor" not in signal.calibration_label


def test_intraday_features_have_explicit_windows_and_units() -> None:
    bars = _minute_bars(include_second_day=False)
    features = compute_intraday_features_v1(
        bars,
        primary_interval_minutes=5,
        cutoff=bars[89].end,
    )

    assert features is not None
    assert features.primary_interval_minutes == 5
    assert features.completed_primary_bar_count == 18
    assert features.atr_14_feature_bars > 0
    assert features.session_vwap > 0
    assert features.relative_volume_20_feature_bars > 0
    assert not any("20d" in name or "60d" in name for name in features.as_dict())
    engine = _engine()
    engine.process_completed_bars(bars)
    assert engine.material_signals
    assert all(
        "factor_ranking_baseline" not in component
        for signal in engine.material_signals
        for component in signal.source_components
    )


def test_tdx_historical_timestamp_labels_bar_start() -> None:
    timestamp = "20260803100100"
    payload = {
        "Open": {timestamp: "10.00"},
        "High": {timestamp: "10.20"},
        "Low": {timestamp: "9.90"},
        "Close": {timestamp: "10.10"},
        "Volume": {timestamp: "10"},
        "Amount": {timestamp: "1.01"},
    }

    bar = normalize_tdx_historical_minute_bars(
        payload,
        requested_symbols=("000001.SZ",),
    )[0]

    assert bar.start.isoformat() == "2026-08-03T10:01:00+08:00"
    assert bar.end.isoformat() == "2026-08-03T10:02:00+08:00"


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
    engine = TDXPredictionEngineV1(
        ("000001.SZ",),
        config=PredictionEngineConfig(
            feature_interval_minutes=5,
            min_feature_bars=15,
            material_probability_delta=0.9,
            material_expected_move_delta=0.1,
        ),
    )

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
    assert (
        report["prediction_evaluation"][
            "prediction_correctness_is_separate_from_execution"
        ]
        is True
    )
    assert "trade_executability" in report
    assert "net_profitability" in report
    assert report["no_lookahead_audit"]["passed"] is True
    assert report["trade_executability"]["next_bar_execution_only"] is True
    assert report["trade_executability"]["t_plus_one_rejection_count"] >= 1
    assert report["trade_executability"]["executable_signal_count"] >= 2
    assert report["net_profitability"]["transaction_cost_total"] > 0
    assert all(
        row["execution_bar_index"] > row["decision_bar_index"]
        and row["execution_delay_bars"] >= 1
        for row in result.execution_outcomes
    )
    one_bar_delay = next(
        row for row in result.execution_outcomes if row["execution_delay_bars"] == 1
    )
    assert one_bar_delay["decision_bar_end"] == one_bar_delay["execution_bar_start"]
    assert report["bar_timestamp_convention"].startswith(
        "TDX timestamp is the one-minute bar start"
    )

    evaluation = report["prediction_evaluation"]
    assert evaluation["model_brier_score"] is not None
    assert evaluation["empirical_class_frequency_brier_score"] is not None
    assert evaluation["constant_0_5_brier_score"] == pytest.approx(0.25)
    assert "brier_skill_score_vs_empirical_frequency" in evaluation
    assert evaluation["model_directional_hit_rate"] is not None
    assert evaluation["naive_directional_hit_rate"] is not None
    assert "simple_buy_and_hold_return" in report["net_profitability"]
    assert "excess_net_return_versus_buy_and_hold" in report["net_profitability"]

    assert report["signal_count_by_state"].keys() == {
        "WATCH", "ENTRY", "HOLD", "WEAKENING", "EXIT", "INVALIDATED"
    }
    reconciliation = report["trade_executability"]["state_to_order_reconciliation"]
    assert reconciliation["reconciled"] is True
    assert reconciliation["attempted_order_count"] == len(result.execution_outcomes)
    assert reconciliation["order_state_signal_count"] == (
        reconciliation["entry_signal_count"]
        + reconciliation["exit_signal_count"]
        + reconciliation["invalidated_signal_count"]
    )
    for transition in reconciliation["transitions"]:
        if (
            transition["state"] in {"ENTRY", "EXIT"}
            and not transition["attempted_order_count"]
        ):
            assert transition["no_attempt_reason"]


def test_same_bar_index_execution_fails_no_lookahead_audit() -> None:
    result = run_historical_replay(_minute_bars(), _engine())
    outcome = dict(result.execution_outcomes[0])
    outcome["execution_bar_index"] = outcome["decision_bar_index"]
    outcome["execution_delay_bars"] = 0

    audit = _no_lookahead_audit(result.all_predictions, (outcome,))

    assert audit["passed"] is False
    assert any(
        "execution_not_after_decision_bar" in item
        for item in audit["violations"]
    )


def test_invalidated_state_is_reachable() -> None:
    engine = _engine()

    engine.process_completed_bars(_minute_bars(include_second_day=False))

    assert any(signal.state == "INVALIDATED" for signal in engine.all_predictions)


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
    assert tq_row[10] == record["intraday_score"]
    assert dry_run["column_spec"] == {
        column: name for column, name, _kind in PREDICTION_TQ_COLUMN_SPEC
    }


def test_live_deepseek_configuration_is_rejected() -> None:
    with pytest.raises(ValueError, match="does not permit live DeepSeek"):
        _engine(context=PredictionContext(deepseek_live_calls_enabled=True))
