#!/usr/bin/env python3
"""Qualify or run the shared TDX replay/live-shadow prediction engine."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Mapping, Sequence

from quantpilot_core.continuous_paper import initialize_reporting_store
from quantpilot_core.daily_paper_loop.report import write_report_atomic
from quantpilot_core.real_data_provider import LiveLevel1Collector, TDXLevel1Provider
from quantpilot_core.tdx_manual_signal_bridge import (
    write_prediction_outcomes_atomic,
    write_prediction_signals_atomic,
)
from quantpilot_core.tdx_manual_signal_bridge.tq_visibility import (
    LiveTQVisibilityPublisher,
    publish_experience_plan_visibility,
)
from quantpilot_core.tdx_prediction_integration import (
    LiveShadowPredictionSink,
    PredictionContext,
    PredictionEngineConfig,
    ReplayConfig,
    TDXPredictionEngineV1,
    V4WalkForwardProbabilityProvider,
    V4WalkForwardTrainingConfig,
    build_end_of_day_experience_review_v1,
    cached_deepseek_evidence_from_payload,
    candidate_context_from_report,
    experience_plan_symbols,
    prediction_signal_record,
    prediction_context_from_experience_plan,
    run_historical_replay,
    train_and_qualify_v4_walk_forward_v1,
)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="TDX qualification, historical replay, and live-shadow integration v1.",
    )
    parser.add_argument(
        "--mode", required=True, choices=("replay", "live-shadow", "qualify", "review")
    )
    parser.add_argument("--symbols", default="", help="Comma-separated explicit symbols.")
    parser.add_argument("--tdx-user-dir", default="")
    parser.add_argument("--start-time", default="")
    parser.add_argument("--end-time", default="")
    parser.add_argument("--history-count", type=int, default=500)
    parser.add_argument("--duration", type=float, default=60.0)
    parser.add_argument("--feature-interval", type=int, default=5, choices=(3, 5, 15, 30))
    parser.add_argument("--initial-cash", type=float, default=100_000.0)
    parser.add_argument("--order-quantity", type=int, default=100)
    parser.add_argument(
        "--prediction-provider",
        choices=(
            "deterministic-baseline",
            "v4-walk-forward",
            "deterministic_baseline",
            "v4_walk_forward",
        ),
        default="deterministic-baseline",
    )
    parser.add_argument(
        "--model-artifact",
        default=".cache/tdx_prediction/v4_walk_forward_model.json",
    )
    parser.add_argument(
        "--qualification-report-path",
        default=".cache/tdx_prediction/v4_walk_forward_qualification.json",
    )
    parser.add_argument("--walk-forward-fold-count", type=int, default=3)
    parser.add_argument("--minimum-oos-samples", type=int, default=100)
    parser.add_argument(
        "--prediction-horizon",
        type=int,
        default=15,
        choices=(5, 15, 30),
    )
    parser.add_argument(
        "--candidate-report",
        default=None,
        help="Optional existing daily-paper/candidate JSON report.",
    )
    parser.add_argument(
        "--experience-plan",
        default=None,
        help="After-close plan; symbols and cached AI context are loaded automatically.",
    )
    parser.add_argument(
        "--deepseek-evidence",
        default=None,
        help="Optional cached AgentFinding-shaped JSON; never triggers a live call.",
    )
    parser.add_argument(
        "--store-provider",
        choices=("auto", "memory", "postgresql"),
        default="auto",
    )
    parser.add_argument(
        "--report-path",
        default=".cache/tdx_prediction/latest_report.json",
    )
    parser.add_argument(
        "--tdx-output-dir",
        default=".cache/tdx_prediction/tdx_signals",
    )
    parser.add_argument(
        "--signals-path",
        default=None,
        help="Review input; defaults to <tdx-output-dir>/latest_prediction.json.",
    )
    parser.add_argument(
        "--state-path",
        default=None,
        help="Optional daily paper state containing signal-associated manual fills.",
    )
    parser.add_argument("--publish-to-tq", action="store_true")
    parser.add_argument("--tdx-plugin-dir", default=None)
    parser.add_argument("--tq-block-name", default="QP体验")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        plan = _load_optional_json(args.experience_plan)
        symbols = _resolve_symbols(args.symbols, plan)
        if not str(args.tdx_user_dir).strip():
            raise ValueError("--tdx-user-dir is required for TDX modes")
        if args.history_count <= 0:
            raise ValueError("--history-count must be positive")
        if args.duration < 0:
            raise ValueError("--duration must be non-negative")
        context = (
            prediction_context_from_experience_plan(plan)
            if plan is not None
            else PredictionContext(
                candidates=candidate_context_from_report(
                    _load_optional_json(args.candidate_report)
                ),
                deepseek_evidence=cached_deepseek_evidence_from_payload(
                    _load_optional_json(args.deepseek_evidence)
                ),
                deepseek_live_calls_enabled=False,
            )
        )
        provider = TDXLevel1Provider(args.tdx_user_dir)
        if args.mode == "review":
            if plan is None:
                raise ValueError("--experience-plan is required for review")
            summary = _run_review(args, provider, symbols, plan)
            print(json.dumps({"status": "ok", **summary}, sort_keys=True))
            return 0
        if args.mode == "qualify":
            summary = _run_qualification(args, provider, symbols)
            print(json.dumps({"status": "ok", **summary}, sort_keys=True))
            return 0
        prediction_provider_name = str(args.prediction_provider).replace("-", "_")
        trained_provider, unavailable_reason = _load_prediction_provider(
            prediction_provider_name,
            args.model_artifact,
        )
        engine = TDXPredictionEngineV1(
            symbols,
            config=PredictionEngineConfig(
                feature_interval_minutes=int(args.feature_interval),
                prediction_provider=prediction_provider_name,
                prediction_horizon_bars=int(args.prediction_horizon),
                prediction_start_timestamp=(
                    _prediction_start_timestamp(plan, trained_provider)
                ),
                prediction_provider_unavailable_reason=unavailable_reason,
            ),
            context=context,
            probability_provider=trained_provider,
        )
        if args.mode == "replay":
            summary = _run_replay(args, provider, engine)
        else:
            summary = _run_live_shadow(args, provider, engine, plan=plan)
        print(json.dumps({"status": "ok", **summary}, sort_keys=True))
        return 0
    except Exception as exc:
        print(
            json.dumps(
                {
                    "status": "error",
                    "mode": args.mode,
                    "error_type": type(exc).__name__,
                    "error": str(exc),
                    "deepseek_live_calls": False,
                    "broker_or_order_api_calls": False,
                },
                sort_keys=True,
            )
        )
        return 2


def _run_replay(
    args: argparse.Namespace,
    provider: TDXLevel1Provider,
    engine: TDXPredictionEngineV1,
) -> Mapping[str, Any]:
    provider.initialize()
    try:
        bars = provider.get_historical_intraday_bars(
            engine.symbols,
            period="1m",
            fields=("Open", "High", "Low", "Close", "Volume", "Amount"),
            start_time=str(args.start_time),
            end_time=str(args.end_time),
            count=int(args.history_count),
            dividend_type="none",
            fill_data=False,
        )
    finally:
        provider.close()
    result = run_historical_replay(
        bars,
        engine,
        config=ReplayConfig(
            initial_cash=float(args.initial_cash),
            order_quantity=int(args.order_quantity),
            brier_horizon=int(args.prediction_horizon),
        ),
    )
    report_path = write_report_atomic(result.report, args.report_path)
    records = tuple(
        prediction_signal_record(signal)
        for signal in engine.visible_transition_signals
    )
    json_path, csv_path = write_prediction_signals_atomic(records, args.tdx_output_dir)
    return {
        "mode": "replay",
        "symbols": list(engine.symbols),
        "bar_count": len(bars),
        "material_signal_count": len(result.material_signals),
        "visible_transition_count": len(engine.visible_transition_signals),
        "signal_count_by_state": result.report["signal_count_by_state"],
        "lifecycle_counts": result.report["lifecycle_counts"],
        "report_path": report_path,
        "tdx_json_path": json_path,
        "tdx_csv_path": csv_path,
        "prediction_evaluation": result.report["prediction_evaluation"],
        "trade_executability": result.report["trade_executability"],
        "net_profitability": result.report["net_profitability"],
        "no_lookahead_audit": result.report["no_lookahead_audit"],
        "prediction_provider": result.report["prediction_provider"],
    }


def _run_qualification(
    args: argparse.Namespace,
    provider: TDXLevel1Provider,
    symbols: Sequence[str],
) -> Mapping[str, Any]:
    provider.initialize()
    try:
        bars = provider.get_historical_intraday_bars(
            symbols,
            period="1m",
            fields=("Open", "High", "Low", "Close", "Volume", "Amount"),
            start_time=str(args.start_time),
            end_time=str(args.end_time),
            count=int(args.history_count),
            dividend_type="none",
            fill_data=False,
        )
    finally:
        provider.close()
    result = train_and_qualify_v4_walk_forward_v1(
        bars,
        V4WalkForwardTrainingConfig(
            feature_interval_minutes=int(args.feature_interval),
            fold_count=int(args.walk_forward_fold_count),
            min_oos_samples_per_horizon=int(args.minimum_oos_samples),
            primary_prediction_horizon=int(args.prediction_horizon),
            initial_cash=float(args.initial_cash),
            order_quantity=int(args.order_quantity),
            artifact_path=args.model_artifact,
            report_path=args.qualification_report_path,
            metadata={
                "runtime": "windows_tdx_local_history",
                "thresholds_tuned_on_july_samples": False,
            },
        ),
    )
    return {
        "mode": "qualify",
        "symbols": list(symbols),
        "bar_count": len(bars),
        "prediction_provider": "v4_walk_forward",
        "provider_qualification_status": result.report[
            "provider_qualification_status"
        ],
        "qualification_reasons": result.report["qualification_reasons"],
        "model_artifact_path": result.artifact_path,
        "qualification_report_path": result.report_path,
        "model_artifact_digest": result.artifact["artifact_digest"],
        "deepseek_live_calls": False,
        "broker_or_order_api_calls": False,
    }


def _load_prediction_provider(
    provider_name: str,
    artifact_path: str,
) -> tuple[V4WalkForwardProbabilityProvider | None, str | None]:
    if provider_name == "deterministic_baseline":
        return None, None
    try:
        provider = V4WalkForwardProbabilityProvider.from_path(artifact_path)
    except Exception as exc:
        return None, f"model_artifact_unavailable:{type(exc).__name__}:{exc}"
    if not provider.qualified:
        return provider, provider.fallback_reason or "model_artifact_not_qualified"
    return provider, None


def _run_live_shadow(
    args: argparse.Namespace,
    provider: TDXLevel1Provider,
    engine: TDXPredictionEngineV1,
    *,
    plan: Mapping[str, Any] | None,
) -> Mapping[str, Any]:
    store, storage_backend = initialize_reporting_store(args.store_provider)
    provider.initialize()
    try:
        history = provider.get_historical_intraday_bars(
            engine.symbols,
            period="1m",
            fields=("Open", "High", "Low", "Close", "Volume", "Amount"),
            start_time=str(args.start_time),
            end_time=str(args.end_time),
            count=int(args.history_count),
            dividend_type="none",
            fill_data=False,
        )
        plan_visibility = None
        if args.publish_to_tq and plan is not None:
            plan_visibility = publish_experience_plan_visibility(
                plan,
                block_name=args.tq_block_name,
            )
        tq_publisher = (
            LiveTQVisibilityPublisher(tdx_plugin_dir=args.tdx_plugin_dir)
            if args.publish_to_tq
            else None
        )
        sink = LiveShadowPredictionSink(
            store,
            engine,
            output_dir=str(args.tdx_output_dir),
            publisher=tq_publisher,
        )
        sink.prime(history)
        collector = LiveLevel1Collector(
            provider,
            engine.symbols,
            sink=sink,
            storage_backend=storage_backend,
            shadow=True,
        )
        collector_report = collector.run(float(args.duration))
    except Exception:
        provider.close()
        raise
    report = {
        "schema_version": "tdx_prediction_live_shadow_v1",
        "mode": "live-shadow",
        "symbols": list(engine.symbols),
        "collector": collector_report.as_dict(),
        "prediction": sink.report(),
        "historical_prime_bar_count": len(history),
        "deepseek_live_calls": False,
        "broker_or_order_api_calls": False,
        "experience_plan_id": next(
            (
                candidate.experience_plan_id
                for candidate in engine.context.candidates.values()
                if candidate.experience_plan_id
            ),
            None,
        ),
        "timing_status": "EXPERIMENTAL SHADOW",
        "trained_model_role": "challenger_only_unless_prequalified",
        "tq_plan_visibility": plan_visibility,
        "ordinary_chart_overlay_status": "pending_windows_visual_confirmation",
        "tq_warning_fallback_active": bool(args.publish_to_tq),
    }
    report_path = write_report_atomic(report, args.report_path)
    return {
        "mode": "live-shadow",
        "symbols": list(engine.symbols),
        "storage_backend": storage_backend,
        "report_path": report_path,
        "collector": collector_report.as_dict(),
        "tq_plan_visibility": plan_visibility,
        "ordinary_chart_overlay_status": "pending_windows_visual_confirmation",
        "tq_warning_fallback_active": bool(args.publish_to_tq),
        **sink.report(),
    }


def _symbols(value: str) -> tuple[str, ...]:
    symbols = tuple(dict.fromkeys(item.strip() for item in value.split(",") if item.strip()))
    if not symbols:
        raise ValueError("--symbols must contain at least one symbol")
    return symbols


def _resolve_symbols(
    explicit: str,
    plan: Mapping[str, Any] | None,
) -> tuple[str, ...]:
    if plan is None:
        return _symbols(explicit)
    planned = experience_plan_symbols(plan)
    if not planned:
        raise ValueError("experience plan contains no candidates")
    if explicit.strip() and _symbols(explicit) != planned:
        raise ValueError("--symbols must exactly match the experience plan when both are supplied")
    return planned


def _prediction_start_timestamp(
    plan: Mapping[str, Any] | None,
    trained_provider: V4WalkForwardProbabilityProvider | None,
) -> str | None:
    plan_start = None
    if plan is not None and plan.get("target_session"):
        plan_start = f"{plan['target_session']}T09:30:00+08:00"
    model_start = (
        str(trained_provider.artifact_metadata["oos_inference_start"])
        if trained_provider is not None
        and trained_provider.qualified
        and trained_provider.artifact_metadata.get("oos_inference_start")
        else None
    )
    if plan_start is None:
        return model_start
    if model_start is None:
        return plan_start
    return max(plan_start, model_start)


def _run_review(
    args: argparse.Namespace,
    provider: TDXLevel1Provider,
    symbols: Sequence[str],
    plan: Mapping[str, Any],
) -> Mapping[str, Any]:
    provider.initialize()
    try:
        bars = provider.get_historical_intraday_bars(
            symbols,
            period="1m",
            fields=("Open", "High", "Low", "Close", "Volume", "Amount"),
            start_time=str(args.start_time),
            end_time=str(args.end_time),
            count=int(args.history_count),
            dividend_type="none",
            fill_data=False,
        )
    finally:
        provider.close()
    signals_path = Path(
        args.signals_path
        or (Path(args.tdx_output_dir) / "latest_prediction.json")
    )
    signal_payload = json.loads(signals_path.read_text(encoding="utf-8"))
    if not isinstance(signal_payload, list):
        raise ValueError("prediction signals file must contain a JSON array")
    state = _load_optional_json(args.state_path)
    review = build_end_of_day_experience_review_v1(
        plan,
        tuple(item for item in signal_payload if isinstance(item, Mapping)),
        bars,
        paper_state=state,
        order_quantity=int(args.order_quantity),
    )
    report_path = write_report_atomic(review, args.report_path)
    outcome_json, outcome_csv = write_prediction_outcomes_atomic(
        tuple(review["outcomes"]),
        args.tdx_output_dir,
    )
    return {
        "mode": "review",
        "symbols": list(symbols),
        "bar_count": len(bars),
        "signals_path": str(signals_path),
        "outcome_count": len(review["outcomes"]),
        "unresolved_count": len(review["unresolved_signals"]),
        "report_path": report_path,
        "outcome_json_path": outcome_json,
        "outcome_csv_path": outcome_csv,
        "hit_rates": review["hit_rates"],
        "after_cost_simulated_profit": review["after_cost_simulated_profit"],
        "deepseek_live_calls": False,
        "broker_or_order_api_calls": False,
    }


def _load_optional_json(path: str | None) -> Mapping[str, Any] | None:
    if path is None:
        return None
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(payload, Mapping):
        raise ValueError(f"JSON input must be an object: {path}")
    return payload


if __name__ == "__main__":
    raise SystemExit(main())
