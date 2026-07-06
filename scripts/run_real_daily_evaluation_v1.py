"""Run a bounded real daily evaluation over existing daily paper sessions."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Mapping

from quantpilot_core.daily_evaluation import RealDailyEvaluationConfig, run_real_daily_evaluation


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run real multi-session daily evaluation v1.")
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--start-decision-session", required=True)
    parser.add_argument("--end-decision-session", required=True)
    parser.add_argument("--symbol", action="append", default=[])
    parser.add_argument("--input-json", default=None)
    parser.add_argument("--capital", action="append", type=float, default=None)
    parser.add_argument("--strategy-id", default="real-candidate-defensive-composite-v1")
    parser.add_argument("--live-market-data", action="store_true")
    parser.add_argument("--max-execution-symbols", type=int, default=6)
    parser.add_argument("--target-symbol-count", type=int, default=1)
    args = parser.parse_args(argv)

    payload: Mapping[str, Any] = _load_payload(args.input_json) if args.input_json else {}
    symbols = tuple(str(symbol) for symbol in (tuple(args.symbol) or tuple(payload.get("symbols", ()))))
    if args.live_market_data and not symbols:
        parser.error("--live-market-data requires explicit --symbol or input-json symbols")
    if not symbols:
        symbols = ("600000.SH", "000001.SZ", "600519.SH")
    capitals = tuple(args.capital) if args.capital else (1_000.0, 10_000.0, 100_000.0)
    input_bars = tuple(payload.get("bars", ()))
    offline_calendar_sessions = tuple(payload.get("calendar", {}).get("sessions", payload.get("offline_calendar_sessions", ())))
    provider_mode = "live_market_data" if args.live_market_data else "offline_input_bars" if input_bars else "synthetic_engineering_fixture"

    result = run_real_daily_evaluation(
        RealDailyEvaluationConfig(
            strategy_id=args.strategy_id,
            start_decision_session=args.start_decision_session,
            end_decision_session=args.end_decision_session,
            symbols=symbols,
            capital_values=capitals,
            output_dir=args.output_dir,
            live_market_data=args.live_market_data,
            provider_mode=provider_mode,
            offline_calendar_sessions=offline_calendar_sessions,
            max_execution_symbols=args.max_execution_symbols,
            target_symbol_count=args.target_symbol_count,
            input_bars=input_bars,
            information_signals=tuple(payload.get("information_signals", ())),
            information_provenance=dict(payload.get("information_provenance", {})),
            advisory_provenance=dict(payload.get("advisory_provenance", {})),
            quant_firm_context=dict(payload.get("quant_firm_context", {})),
        )
    )
    print(
        json.dumps(
            {
                "status": result.status,
                "report_path": result.report_path,
                "evaluation_request_digest": result.evaluation_request_digest,
            },
            sort_keys=True,
        )
    )
    return 0


def _load_payload(path: str | None) -> Mapping[str, Any]:
    if path is None:
        return {}
    return json.loads(Path(path).read_text(encoding="utf-8"))


if __name__ == "__main__":
    raise SystemExit(main())
