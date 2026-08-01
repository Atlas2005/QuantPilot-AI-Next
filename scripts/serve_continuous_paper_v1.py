#!/usr/bin/env python3
"""Explicit Prefect deployment helper; no schedule starts during import."""

from __future__ import annotations

import argparse
from typing import Any


def parser() -> argparse.ArgumentParser:
    value = argparse.ArgumentParser()
    value.add_argument("--production-manifest", required=True)
    value.add_argument("--decision-session", required=True)
    value.add_argument("--state-path", required=True)
    value.add_argument("--report-path", required=True)
    value.add_argument("--run-id", required=True)
    value.add_argument("--input-json", default=None)
    value.add_argument("--live-market-data", action="store_true")
    value.add_argument("--dsn-env-var", default="QUANTPILOT_POSTGRES_DSN")
    value.add_argument("--cron", default="30 16 * * 1-5")
    value.add_argument("--timezone", default="Asia/Shanghai")
    value.add_argument("--cache-path", default=".cache/quantpilot/active_shadow")
    value.add_argument("--timeout", type=float, default=30.0)
    value.add_argument("--allowed-roles", default="")
    value.add_argument("--enable-active-shadow", action="store_true")
    value.add_argument("--enable-live-ai", action="store_true")
    value.add_argument("--max-physical-model-calls", type=int, default=0)
    value.add_argument("--max-estimated-api-cost", type=float, default=0.0)
    value.add_argument("--estimated-cost-per-call", type=float, default=0.0)
    return value


def main() -> None:
    argument_parser = parser()
    args = argument_parser.parse_args()

    # Deliberately lazy: --help stays useful in minimal/offline environments.
    from quantpilot_core.continuous_paper import (
        ActiveShadowConfig,
        load_production_input_payload,
        normalize_active_shadow_roles,
    )

    try:
        shadow = ActiveShadowConfig(
            enabled=args.enable_active_shadow,
            enable_live_calls=args.enable_live_ai,
            max_physical_model_calls_per_cycle=args.max_physical_model_calls,
            max_estimated_cost_per_cycle=args.max_estimated_api_cost,
            estimated_cost_per_call=args.estimated_cost_per_call,
            cache_path=args.cache_path,
            allow_roles=normalize_active_shadow_roles(args.allowed_roles),
            timeout=args.timeout,
        )
    except ValueError as exc:
        argument_parser.error(str(exc))

    from quantpilot_core.continuous_paper.prefect_flow import continuous_paper_flow

    if not hasattr(continuous_paper_flow, "serve"):
        raise RuntimeError(
            "install quantpilot-ai-next[continuous-paper] to serve a Prefect deployment"
        )
    from prefect.schedules import Cron

    parameters: dict[str, Any] = {
        "production_manifest_path": args.production_manifest,
        "decision_session": args.decision_session,
        "state_path": args.state_path,
        "report_path": args.report_path,
        "run_id": args.run_id,
        "dsn_env_var": args.dsn_env_var,
        "live_market_data": args.live_market_data,
        "input_payload": load_production_input_payload(args.input_json),
        "active_shadow": {
            "enabled": shadow.enabled,
            "enable_live_calls": shadow.enable_live_calls,
            "max_physical_model_calls_per_cycle": (
                shadow.max_physical_model_calls_per_cycle
            ),
            "max_estimated_cost_per_cycle": shadow.max_estimated_cost_per_cycle,
            "estimated_cost_per_call": shadow.estimated_cost_per_call,
            "cache_path": str(shadow.cache_path),
            "allow_roles": [role.value for role in shadow.allow_roles],
            "timeout": shadow.timeout,
            "failure_policy": shadow.failure_policy,
        },
    }
    continuous_paper_flow.serve(
        name="quantpilot-continuous-paper-v1",
        schedules=[Cron(args.cron, timezone=args.timezone)],
        parameters=parameters,
    )


if __name__ == "__main__":
    main()
