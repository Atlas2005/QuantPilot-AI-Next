"""Run one durable daily multi-agent paper-loop session."""

from __future__ import annotations

import argparse
import json

from quantpilot_core.daily_paper_loop import (
    DailyPaperLoopConfig,
    build_offline_fixture_input,
    run_daily_paper_loop,
)
from quantpilot_core.daily_paper_loop.provider_market_input import (
    attempt_payload as _attempt_payload,
    bar_payload as _bar_payload,
    bars_by_trade_date as _bars_by_trade_date,
    build_provider_market_input as _build_live_market_input,
    candidate_from_payload as _candidate,
    load_daily_loop_input_json as _load_input_json,
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run one offline daily paper-loop lifecycle.")
    parser.add_argument("--state-path", default=".cache/daily_paper_loop/state.json")
    parser.add_argument("--report-path", default=".cache/daily_paper_loop/latest_report.json")
    parser.add_argument("--decision-session", default=None)
    parser.add_argument("--initial-capital", type=float, default=100_000.0)
    parser.add_argument("--input-json", default=None)
    parser.add_argument("--live-market-data", action="store_true")
    args = parser.parse_args(argv)

    if args.live_market_data and not args.decision_session:
        parser.error("--live-market-data requires --decision-session")
    if args.live_market_data and args.input_json is None:
        parser.error("--live-market-data requires --input-json with local/injected candidates")

    decision_session = args.decision_session or "2026-01-02"
    loop_input = (
        _build_live_market_input(
            args.input_json,
            decision_session,
            state_path=args.state_path,
            initial_capital=args.initial_capital,
        )
        if args.live_market_data
        else (_load_input_json(args.input_json) if args.input_json else build_offline_fixture_input(decision_session))
    )
    config = DailyPaperLoopConfig(
        decision_session=decision_session,
        initial_capital=args.initial_capital,
        state_path=args.state_path,
        report_path=args.report_path,
        live_market_data=args.live_market_data,
    )
    result = run_daily_paper_loop(loop_input, config)
    print(json.dumps({"status": result.status.value, "report_path": result.report_path, "state_path": result.state_path}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
