#!/usr/bin/env python3
"""Run the shared TDX prediction engine in historical replay or live shadow."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Mapping, Sequence

from quantpilot_core.daily_paper_loop.report import write_report_atomic
from quantpilot_core.real_data_provider import LiveLevel1Collector, TDXLevel1Provider
from quantpilot_core.tdx_manual_signal_bridge import write_prediction_signals_atomic
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
from scripts.run_tdx_level1_adapter_v1 import _store


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="TDX historical replay and live-shadow prediction integration v1.",
    )
    parser.add_argument("--mode", required=True, choices=("replay", "live-shadow"))
    parser.add_argument("--symbols", required=True, help="Comma-separated explicit symbols.")
    parser.add_argument("--tdx-user-dir", required=True)
    parser.add_argument("--start-time", default="")
    parser.add_argument("--end-time", default="")
    parser.add_argument("--history-count", type=int, default=500)
    parser.add_argument("--duration", type=float, default=60.0)
    parser.add_argument("--feature-interval", type=int, default=5, choices=(3, 5, 15, 30))
    parser.add_argument("--initial-cash", type=float, default=100_000.0)
    parser.add_argument("--order-quantity", type=int, default=100)
    parser.add_argument(
        "--candidate-report",
        default=None,
        help="Optional existing daily-paper/candidate JSON report.",
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
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        symbols = _symbols(args.symbols)
        if args.history_count <= 0:
            raise ValueError("--history-count must be positive")
        if args.duration < 0:
            raise ValueError("--duration must be non-negative")
        context = PredictionContext(
            candidates=candidate_context_from_report(_load_optional_json(args.candidate_report)),
            deepseek_evidence=cached_deepseek_evidence_from_payload(
                _load_optional_json(args.deepseek_evidence)
            ),
            deepseek_live_calls_enabled=False,
        )
        engine = TDXPredictionEngineV1(
            symbols,
            config=PredictionEngineConfig(
                feature_interval_minutes=int(args.feature_interval),
            ),
            context=context,
        )
        provider = TDXLevel1Provider(args.tdx_user_dir)
        if args.mode == "replay":
            summary = _run_replay(args, provider, engine)
        else:
            summary = _run_live_shadow(args, provider, engine)
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
        ),
    )
    report_path = write_report_atomic(result.report, args.report_path)
    records = tuple(prediction_signal_record(signal) for signal in result.material_signals)
    json_path, csv_path = write_prediction_signals_atomic(records, args.tdx_output_dir)
    return {
        "mode": "replay",
        "symbols": list(engine.symbols),
        "bar_count": len(bars),
        "material_signal_count": len(result.material_signals),
        "report_path": report_path,
        "tdx_json_path": json_path,
        "tdx_csv_path": csv_path,
        "prediction_evaluation": result.report["prediction_evaluation"],
        "trade_executability": result.report["trade_executability"],
        "net_profitability": result.report["net_profitability"],
        "no_lookahead_audit": result.report["no_lookahead_audit"],
    }


def _run_live_shadow(
    args: argparse.Namespace,
    provider: TDXLevel1Provider,
    engine: TDXPredictionEngineV1,
) -> Mapping[str, Any]:
    store, storage_backend = _store(args.store_provider)
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
        sink = LiveShadowPredictionSink(
            store,
            engine,
            output_dir=str(args.tdx_output_dir),
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
    }
    report_path = write_report_atomic(report, args.report_path)
    return {
        "mode": "live-shadow",
        "symbols": list(engine.symbols),
        "storage_backend": storage_backend,
        "report_path": report_path,
        "collector": collector_report.as_dict(),
        **sink.report(),
    }


def _symbols(value: str) -> tuple[str, ...]:
    symbols = tuple(dict.fromkeys(item.strip() for item in value.split(",") if item.strip()))
    if not symbols:
        raise ValueError("--symbols must contain at least one symbol")
    return symbols


def _load_optional_json(path: str | None) -> Mapping[str, Any] | None:
    if path is None:
        return None
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(payload, Mapping):
        raise ValueError(f"JSON input must be an object: {path}")
    return payload


if __name__ == "__main__":
    raise SystemExit(main())
