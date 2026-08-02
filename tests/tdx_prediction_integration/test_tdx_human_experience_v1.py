from __future__ import annotations

import json
import sys
from datetime import datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from zoneinfo import ZoneInfo

from quantpilot_core.daily_paper_loop.state import load_daily_state
from quantpilot_core.real_data_provider import NormalizedIntradayBar
from quantpilot_core.tdx_manual_signal_bridge import write_prediction_outcomes_atomic
from quantpilot_core.tdx_prediction_integration import (
    PREDICTION_STATE_LABEL_ZH,
    LiveShadowPredictionSink,
    PredictionEngineConfig,
    TDXPredictionEngineV1,
    build_end_of_day_experience_review_v1,
    build_next_day_experience_plan_v1,
    prediction_context_from_experience_plan,
)
from scripts.publish_tdx_signals_tq_v1 import (
    PREDICTION_STATE_LABEL_ZH as PUBLISHER_LABELS,
    publish_to_tq,
)
from scripts.record_manual_fill_v1 import main as record_manual_fill
from scripts.run_tdx_prediction_integration_v1 import (
    _load_prediction_provider,
    _resolve_symbols,
)


SHANGHAI = ZoneInfo("Asia/Shanghai")


def _production_report() -> dict:
    candidates = [
        {
            "symbol": "000002.SZ",
            "name": "万科A",
            "direction": "long",
            "confidence": 0.72,
            "risk_score": 0.28,
            "liquidity_score": 0.91,
            "timestamp": "2026-08-03T15:00:00+08:00",
            "metadata": {
                "candidate_id": "production:000002.SZ",
                "strategy_id": "existing-production-candidate",
                "factor_rank": 2,
                "factor_composite_score": 0.66,
                "pit_cutoff": "2026-08-03T15:00:00+08:00",
                "factor_evidence": {"quality": 0.7},
            },
        },
        {
            "symbol": "000001.SZ",
            "name": "平安银行",
            "direction": "long",
            "confidence": 0.68,
            "risk_score": 0.32,
            "liquidity_score": 0.89,
            "timestamp": "2026-08-03T15:00:00+08:00",
            "metadata": {
                "candidate_id": "production:000001.SZ",
                "strategy_id": "existing-production-candidate",
                "factor_rank": 1,
                "factor_composite_score": None,
                "pit_cutoff": "2026-08-03T15:00:00+08:00",
            },
        },
    ]
    research = {
        "target": "000002.SZ",
        "committee_stance": "bull",
        "dominant_thesis": "Existing committee thesis.",
        "risk_thesis": "Existing committee risk.",
    }
    information = {
        "target": "000002.SZ",
        "aggregate_bias": "positive",
        "aggregate_score": 0.61,
        "signals": [{"evidence": ["existing information evidence"]}],
        "conflicts": [],
        "limitations": ["information advisory only"],
    }
    return {
        "schema_version": "real_candidate_pipeline_report_v1",
        "candidate_pipeline": {
            "sessions": {"decision": "2026-08-03", "execution": "2026-08-04"},
            "selected_symbols": ["000002.SZ", "000001.SZ"],
            "candidates": {"candidates": candidates},
            "evidence": {
                "000002.SZ": {"factor_rank": 2},
                "000001.SZ": {"factor_rank": 1},
            },
        },
        "daily_paper_loop": {
            "decision_session": "2026-08-03",
            "execution_session": "2026-08-04",
            "production_candidate_id": "prod-v1",
            "production_candidate_version": "1",
            "candidate_report": {"candidates": candidates},
            "quant_firm_input_candidate_report": {"candidates": candidates},
            "quant_firm_report": {
                "final_recommendation": "approve_offline_shadow_cycle",
                "committee_decision": {"rationale": "Existing Quant Firm approval."},
                "recommendations": [{"output": research}, {"output": information}],
                "limitations": ["advisory_only"],
            },
            "ai_shadow_report": {
                "shadow_committee_decision": {"decision": "review"},
                "specialist_desk_outputs": [],
            },
        },
    }


def _active_shadow() -> dict:
    return {
        "mode": "active_shadow",
        "physical_model_calls": 2,
        "cache_hits": 5,
        "roles": {
            "research_desk": {
                "advisory_summary": "Reuse this exact DeepSeek research summary.",
                "stance": "bullish",
                "confidence": 0.73,
                "risk_notes": ["cached risk"],
                "evidence_used": ["existing:research"],
                "is_fallback": False,
            },
            "investment_committee": {
                "advisory_summary": "Reuse this exact DeepSeek committee summary.",
                "confidence": 0.69,
                "risk_notes": [],
                "evidence_used": ["existing:committee"],
                "is_fallback": False,
            },
        },
    }


def _plan(top_n: int = 2) -> dict:
    return dict(
        build_next_day_experience_plan_v1(
            _production_report(),
            active_shadow_report=_active_shadow(),
            top_n=top_n,
            generated_at="2026-08-03T16:30:00+08:00",
        )
    )


def _bars(symbol: str = "000002.SZ", count: int = 40) -> tuple[NormalizedIntradayBar, ...]:
    start = datetime(2026, 8, 4, 9, 30, tzinfo=SHANGHAI)
    rows = []
    price = 10.0
    for index in range(count):
        opened = price
        price = round(price * 1.001, 6)
        rows.append(
            NormalizedIntradayBar(
                symbol=symbol,
                start=start + timedelta(minutes=index),
                end=start + timedelta(minutes=index + 1),
                interval_minutes=1,
                open=opened,
                high=price * 1.0005,
                low=opened * 0.9995,
                close=price,
                volume=10_000.0,
                amount=price * 10_000.0,
                average_price=price,
                event_count=1,
            )
        )
    return tuple(rows)


def test_after_close_plan_slices_existing_order_and_reuses_multi_agent_output() -> None:
    plan = _plan(top_n=1)

    assert plan["symbols"] == ["000002.SZ"]
    assert plan["candidates"][0]["candidate_rank"] == 2
    assert plan["candidates"][0]["quant_score"] == 0.66
    assert plan["candidates"][0]["stance"] == "bullish"
    assert plan["candidates"][0]["deepseek_stance"] == "bullish"
    summaries = plan["candidates"][0]["ai_conclusion"]["deepseek_role_summaries"]
    assert summaries[0]["summary"] == "Reuse this exact DeepSeek research summary."
    assert plan["ai_analysis"]["active_shadow_physical_model_calls"] == 2
    assert plan["ai_analysis"]["information_agent_reused"] is True
    assert plan["ai_analysis"]["per_tick_deepseek_calls_permitted"] is False
    assert "real_candidate_pipeline existing candidate order" in plan["source_components_reused"]


def test_plan_context_monitors_only_planned_symbols_without_live_deepseek() -> None:
    plan = _plan(top_n=1)
    context = prediction_context_from_experience_plan(plan)

    assert tuple(context.candidates) == ("000002.SZ",)
    assert context.deepseek_live_calls_enabled is False
    assert context.deepseek_evidence
    assert _resolve_symbols("", plan) == ("000002.SZ",)


def test_visible_markers_are_only_state_transitions_and_carry_plan_context() -> None:
    plan = _plan(top_n=1)
    engine = TDXPredictionEngineV1(
        ("000002.SZ",),
        config=PredictionEngineConfig(
            feature_interval_minutes=5,
            min_feature_bars=15,
            prediction_start_timestamp="2026-08-04T09:30:00+08:00",
        ),
        context=prediction_context_from_experience_plan(plan),
    )

    engine.process_completed_bars(_bars(count=120))
    visible = engine.visible_transition_signals

    assert visible
    assert all(signal.state != "WATCH" for signal in visible)
    assert all(
        left.state != right.state or left.symbol != right.symbol
        for left, right in zip(visible, visible[1:])
    )
    assert all(signal.candidate_rank == 2 for signal in visible)
    assert all(signal.after_close_quant_score == 0.66 for signal in visible)
    assert all(signal.deepseek_stance == "bullish" for signal in visible)
    assert all(signal.shadow_status == "EXPERIMENTAL SHADOW" for signal in visible)
    assert all(signal.signal_id.startswith("tdx-signal-") for signal in visible)


def test_chinese_chart_state_mapping_is_exact() -> None:
    expected = {
        "ENTRY": "买",
        "HOLD": "持",
        "WEAKENING": "弱",
        "EXIT": "卖",
        "INVALIDATED": "失效",
    }
    assert {key: PREDICTION_STATE_LABEL_ZH[key] for key in expected} == expected
    assert PUBLISHER_LABELS == expected


def test_live_sink_publishes_transition_ledger_not_per_bar(tmp_path: Path) -> None:
    plan = _plan(top_n=1)
    engine = TDXPredictionEngineV1(
        ("000002.SZ",),
        config=PredictionEngineConfig(feature_interval_minutes=5, min_feature_bars=15),
        context=prediction_context_from_experience_plan(plan),
    )
    published: list[tuple[dict, ...]] = []

    class Store:
        def persist_market_data(self, events, bars) -> None:
            return None

    sink = LiveShadowPredictionSink(
        Store(),
        engine,
        output_dir=str(tmp_path),
        publisher=lambda records: published.append(tuple(dict(item) for item in records)),
    )
    sink.prime(_bars(count=120))

    assert published
    records = published[-1]
    assert len(records) == len(engine.visible_transition_signals)
    assert len(records) < len(engine.all_predictions)
    assert all(record["state"] != "WATCH" for record in records)
    assert sink.report()["visible_marker_policy"] == "lifecycle_state_transitions_only"


def test_live_sink_marks_historical_prime_as_warning_baseline(tmp_path: Path) -> None:
    plan = _plan(top_n=1)
    engine = TDXPredictionEngineV1(
        ("000002.SZ",),
        config=PredictionEngineConfig(feature_interval_minutes=5, min_feature_bars=15),
        context=prediction_context_from_experience_plan(plan),
    )

    class Store:
        def persist_market_data(self, events, bars) -> None:
            return None

    class Publisher:
        def __init__(self) -> None:
            self.baselines = []
            self.live = []

        def publish_baseline(self, records):
            self.baselines.append(tuple(records))
            return {"historical_baseline": True}

        def __call__(self, records):
            self.live.append(tuple(records))
            return {"historical_baseline": False}

    publisher = Publisher()
    sink = LiveShadowPredictionSink(
        Store(),
        engine,
        output_dir=str(tmp_path),
        publisher=publisher,
    )

    sink.prime(_bars(count=120))

    assert publisher.baselines
    assert publisher.live == []
    assert sink.report()["tq_visibility_fallback"]["historical_baseline"] is True


def test_outcomes_bind_prior_signal_use_strict_future_bars_and_existing_costs(tmp_path: Path) -> None:
    plan = _plan(top_n=1)
    bars = _bars(count=40)
    decision = bars[0].end.isoformat()
    signal = {
        "schema_version": "tdx_prediction_signal_v1",
        "signal_id": "tdx-signal-test-entry",
        "symbol": "000002.SZ",
        "decision_timestamp": decision,
        "timestamp": decision,
        "data_cutoff_timestamp": decision,
        "state": "ENTRY",
        "state_label_zh": "买",
        "decision_price": bars[0].close,
        "candidate_rank": 2,
        "after_close_quant_score": 0.66,
        "deepseek_stance": "bullish",
        "prediction_provider": "deterministic_baseline",
        "prediction_provider_requested": "v4_walk_forward",
        "provider_qualified": False,
        "provider_fallback": True,
        "source_components": ["existing_engine"],
        "evidence_refs": ["existing:candidate"],
        "experience_plan_id": plan["plan_id"],
        "shadow_status": "EXPERIMENTAL SHADOW",
    }
    state = {
        "execution_state": {
            "account": {
                "trade_log": [
                    {
                        "symbol": "000002.SZ",
                        "side": "buy",
                        "quantity": 100,
                        "fill_price": 10.02,
                        "total_cost": 5.0,
                        "metadata": {
                            "manual_fill": True,
                            "trade_date": "2026-08-04",
                            "signal_id": "tdx-signal-test-entry",
                        },
                    }
                ]
            }
        }
    }

    review = build_end_of_day_experience_review_v1(
        plan,
        (signal,),
        bars,
        paper_state=state,
    )
    outcome = review["outcomes"][0]

    assert outcome["return_5m"] == round(bars[5].close / bars[0].close - 1.0, 8)
    assert outcome["correct_5m"] is True
    assert outcome["resolution_status"] == "resolved"
    assert outcome["simulated_cost"] > 0
    assert outcome["maximum_favourable_excursion"] > 0
    assert review["no_lookahead_audit"]["passed"] is True
    assert review["manual_fill_associations"][0]["signal_id"] == signal["signal_id"]
    assert review["broker_or_order_api_calls"] is False
    json_path, csv_path = write_prediction_outcomes_atomic(review["outcomes"], tmp_path)
    assert Path(json_path).exists()
    assert Path(csv_path).exists()


def test_manual_fill_is_associated_in_existing_paper_trade_log(
    tmp_path: Path, monkeypatch
) -> None:
    signal_path = tmp_path / "latest_prediction.json"
    signal_path.write_text(
        json.dumps(
            [
                {
                    "signal_id": "tdx-signal-manual",
                    "symbol": "000002.SZ",
                    "state": "ENTRY",
                    "decision_timestamp": "2026-08-04T10:00:00+08:00",
                    "prediction_provider": "deterministic_baseline",
                    "experience_plan_id": "tdx-plan-test",
                }
            ]
        ),
        encoding="utf-8",
    )
    state_path = tmp_path / "state.json"
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "record_manual_fill_v1.py",
            "BUY",
            "000002.SZ",
            "100",
            "10.00",
            "2026-08-04",
            "--state-path",
            str(state_path),
            "--signal-id",
            "tdx-signal-manual",
            "--signals-path",
            str(signal_path),
        ],
    )

    assert record_manual_fill() == 0
    state = load_daily_state(state_path, initial_capital=100_000.0)
    trade = state.execution_state.account.trade_log[-1]
    assert trade.metadata["signal_id"] == "tdx-signal-manual"
    assert trade.metadata["signal_experience_plan_id"] == "tdx-plan-test"


def test_unqualified_trained_provider_is_nonblocking_challenger(tmp_path: Path) -> None:
    provider, reason = _load_prediction_provider(
        "v4_walk_forward", str(tmp_path / "missing-model.json")
    )

    assert provider is None
    assert reason.startswith("model_artifact_unavailable:")


def test_tq_publish_can_share_provider_owned_lifecycle(monkeypatch) -> None:
    tq = SimpleNamespace(
        initialize=lambda *_: (_ for _ in ()).throw(AssertionError("must not initialize")),
        close=lambda: (_ for _ in ()).throw(AssertionError("must not close")),
        send_bt_data=lambda **_: None,
    )
    monkeypatch.setitem(sys.modules, "tqcenter", SimpleNamespace(tq=tq))
    monkeypatch.setattr("scripts.publish_tdx_signals_tq_v1.platform.system", lambda: "Windows")
    signal = {
        "schema_version": "tdx_prediction_signal_v1",
        "symbol": "000002.SZ",
        "timestamp": "2026-08-04T10:00:00+08:00",
        "state": "ENTRY",
        "entry_probability": 0.7,
        "continuation_probability": 0.6,
        "exit_probability": 0.3,
        "expected_return": 0.01,
        "entry_zone_low": 9.9,
        "entry_zone_high": 10.1,
        "invalidation_price": 9.7,
        "first_target_price": 10.3,
        "intraday_score": 0.7,
        "material_change": True,
    }

    result = publish_to_tq((signal,), manage_tq_lifecycle=False)

    assert result["row_count"] == 1
    assert result["manage_tq_lifecycle"] is False
