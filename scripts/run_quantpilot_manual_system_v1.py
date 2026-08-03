#!/usr/bin/env python3
"""Run the broker-free QuantPilot Windows manual-trading workflow."""

from __future__ import annotations

import argparse
import json
import os
import re
from pathlib import Path
from typing import Any, Mapping, Sequence

from quantpilot_core.manual_trading_system import (
    AfterCloseConfig,
    EndOfDayConfig,
    IntradayConfig,
    acceptance_summary,
    run_after_close,
    run_end_of_day,
    run_intraday,
    write_json_atomic,
)


DEFAULT_SYSTEM_DIR = ".cache/quantpilot_manual_system_v1"


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="QuantPilot one-command manual-trading system (no broker or orders)."
    )
    subparsers = parser.add_subparsers(dest="phase", required=True)

    after = subparsers.add_parser("after-close", help="Run seven desks and publish QPTY.")
    _add_after_close_arguments(after)

    intraday = subparsers.add_parser("intraday", help="Monitor QPTY with TDX Level1.")
    _add_intraday_arguments(intraday)

    end = subparsers.add_parser("end-of-day", help="Finalize outcomes and accuracy.")
    end.add_argument("--system-dir", default=DEFAULT_SYSTEM_DIR)

    run_day = subparsers.add_parser("run-day", help="Run after-close, intraday, and review.")
    _add_after_close_arguments(run_day)
    _add_intraday_arguments(run_day, include_system_dir=False, include_tdx_dir=False)

    acceptance = subparsers.add_parser(
        "acceptance", help="Bounded real Windows DeepSeek + TDX acceptance run."
    )
    _add_after_close_arguments(acceptance, live_ai_default=True)
    _add_intraday_arguments(acceptance, include_system_dir=False, include_tdx_dir=False)
    acceptance.set_defaults(duration=5.0, live_ai=True, publish_to_tq=True)
    return parser


def _add_after_close_arguments(
    parser: argparse.ArgumentParser, *, live_ai_default: bool = True
) -> None:
    parser.add_argument("--production-input", required=True)
    parser.add_argument("--system-dir", default=DEFAULT_SYSTEM_DIR)
    parser.add_argument("--tdx-user-dir", required=True)
    parser.add_argument(
        "--enable-live-ai",
        "--live-ai",
        dest="live_ai",
        action=argparse.BooleanOptionalAction,
        default=live_ai_default,
        help="Use the seven live DeepSeek advisory calls (enabled by default).",
    )
    parser.add_argument("--deepseek-model", default=None)
    parser.add_argument("--deepseek-timeout", type=float, default=60.0)
    parser.add_argument("--tq-block-code", default="QPTY")
    parser.add_argument("--tq-block-name", default="QP候选")
    parser.add_argument(
        "--tq-block-show", action=argparse.BooleanOptionalAction, default=True
    )


def _add_intraday_arguments(
    parser: argparse.ArgumentParser,
    *,
    include_system_dir: bool = True,
    include_tdx_dir: bool = True,
) -> None:
    if include_system_dir:
        parser.add_argument("--system-dir", default=DEFAULT_SYSTEM_DIR)
    if include_tdx_dir:
        parser.add_argument("--tdx-user-dir", required=True)
    parser.add_argument("--duration", type=float, default=14_400.0)
    parser.add_argument("--start-time", default="")
    parser.add_argument("--end-time", default="")
    parser.add_argument("--history-count", type=int, default=500)
    parser.add_argument("--feature-interval", type=int, choices=(3, 5, 15, 30), default=5)
    parser.add_argument("--poll-interval", type=float, default=1.0)
    parser.add_argument("--holdings", default=None)
    parser.add_argument(
        "--publish-to-tq", action=argparse.BooleanOptionalAction, default=True
    )


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        if args.phase == "after-close":
            result: Mapping[str, Any] = _run_after(args)
        elif args.phase == "intraday":
            result = _run_intraday(args)
        elif args.phase == "end-of-day":
            result = run_end_of_day(EndOfDayConfig(system_dir=args.system_dir))
        else:
            after = _run_after(args)
            intraday = _run_intraday(args)
            end = run_end_of_day(EndOfDayConfig(system_dir=args.system_dir))
            result = {
                "schema_version": "quantpilot_manual_run_day_v1",
                "phase": args.phase,
                "after_close": after,
                "intraday": intraday,
                "end_of_day": end,
                "broker_calls": 0,
                "order_submission_calls": 0,
            }
            if args.phase == "acceptance":
                acceptance = acceptance_summary(after, intraday)
                acceptance_path = write_json_atomic(
                    acceptance, Path(args.system_dir) / "windows_acceptance.json"
                )
                result = {**acceptance, "acceptance_report_path": acceptance_path}
        print(json.dumps({"status": "ok", **result}, ensure_ascii=True, sort_keys=True))
        if args.phase == "acceptance" and not result.get("automated_checks_passed"):
            return 3
        return 0
    except KeyboardInterrupt:
        print(
            json.dumps(
                {
                    "status": "cancelled",
                    "phase": args.phase,
                    "broker_calls": 0,
                    "order_submission_calls": 0,
                },
                ensure_ascii=True,
                sort_keys=True,
            )
        )
        return 130
    except Exception as exc:
        secret = os.environ.get("DEEPSEEK_API_KEY")
        print(
            json.dumps(
                {
                    "status": "error",
                    "phase": args.phase,
                    "error_type": type(exc).__name__,
                    "sanitized_error": _sanitize_error(exc, secret),
                    "broker_calls": 0,
                    "order_submission_calls": 0,
                },
                ensure_ascii=True,
                sort_keys=True,
            )
        )
        return 2


def _run_after(args: argparse.Namespace) -> Mapping[str, Any]:
    if args.deepseek_timeout <= 0:
        raise ValueError("--deepseek-timeout must be positive")
    return run_after_close(
        AfterCloseConfig(
            production_input_path=args.production_input,
            system_dir=args.system_dir,
            live_ai=bool(args.live_ai),
            deepseek_model=args.deepseek_model,
            deepseek_timeout_seconds=float(args.deepseek_timeout),
            tdx_user_dir=args.tdx_user_dir,
            tq_block_code=args.tq_block_code,
            tq_block_name=args.tq_block_name,
            tq_block_show=bool(args.tq_block_show),
        )
    )


def _run_intraday(args: argparse.Namespace) -> Mapping[str, Any]:
    if args.poll_interval <= 0:
        raise ValueError("--poll-interval must be positive")
    return run_intraday(
        IntradayConfig(
            system_dir=args.system_dir,
            tdx_user_dir=args.tdx_user_dir,
            duration_seconds=float(args.duration),
            start_time=args.start_time,
            end_time=args.end_time,
            history_count=int(args.history_count),
            feature_interval_minutes=int(args.feature_interval),
            poll_interval_seconds=float(args.poll_interval),
            publish_to_tq=bool(args.publish_to_tq),
            holdings_path=args.holdings,
        )
    )


def _sanitize_error(exc: Exception, secret: str | None) -> str:
    text = " ".join(str(exc).split())
    if secret:
        text = text.replace(secret, "<redacted>")
    text = re.sub(
        r"(?i)(api[_-]?key|token|authorization)\s*[:=]\s*[^\s,;]+",
        r"\1=<redacted>",
        text,
    )
    return text[:500]


if __name__ == "__main__":
    raise SystemExit(main())
