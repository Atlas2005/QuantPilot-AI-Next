"""Run one real PIT factor-candidate daily paper lifecycle."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Mapping

from quantpilot_core.real_candidate_pipeline import RealCandidatePipelineConfig, run_real_candidate_daily_paper


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run real PIT factor candidates through the durable daily paper loop.")
    parser.add_argument("--state-path", default=".cache/real_candidate_daily_paper/state.json")
    parser.add_argument("--report-path", default=".cache/real_candidate_daily_paper/latest_report.json")
    parser.add_argument("--input-json", default=None)
    parser.add_argument("--decision-session", default=None)
    parser.add_argument("--initial-capital", type=float, default=100_000.0)
    parser.add_argument("--live-market-data", action="store_true")
    args = parser.parse_args(argv)

    payload: Mapping[str, Any] = _load_payload(args.input_json) if args.input_json else {}
    symbols = tuple(str(symbol) for symbol in payload.get("symbols", ()))
    decision_session = args.decision_session
    if args.live_market_data and decision_session is None:
        parser.error("--live-market-data requires --decision-session")
    if args.live_market_data and not symbols:
        parser.error("--live-market-data requires --input-json with an explicit symbols list")
    if decision_session is None:
        decision_session = "2026-04-03"

    config = RealCandidatePipelineConfig(
        decision_session=decision_session,
        symbols=symbols,
        initial_capital=args.initial_capital,
        state_path=args.state_path,
        report_path=args.report_path,
        live_market_data=args.live_market_data,
        input_bars=tuple(payload.get("bars", ())),
        information_signals=tuple(payload.get("information_signals", ())),
        information_provenance=dict(payload.get("information_provenance", {})),
        advisory_provenance=dict(payload.get("advisory_provenance", {})),
        quant_firm_context=dict(payload.get("quant_firm_context", {})),
    )
    result = run_real_candidate_daily_paper(config)
    status = result.daily_paper_loop_result.status.value if result.daily_paper_loop_result is not None else "not_run"
    print(json.dumps({"status": status, "report_path": args.report_path, "state_path": args.state_path}, sort_keys=True))
    return 0


def _load_payload(path: str | None) -> Mapping[str, Any]:
    if path is None:
        return {}
    return json.loads(Path(path).read_text(encoding="utf-8"))


if __name__ == "__main__":
    raise SystemExit(main())
