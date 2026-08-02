#!/usr/bin/env python3
"""Manual, offline-safe entry point for one continuous paper cycle."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from quantpilot_core.continuous_paper import (
    ActiveShadowConfig,
    ContinuousPaperCycle,
    ContinuousPaperCycleConfig,
    InMemoryReportingStore,
    PostgreSQLReportingStore,
    load_production_input_payload,
    load_production_pipeline_config,
    normalize_active_shadow_roles,
)
from quantpilot_core.daily_paper_loop.report import write_report_atomic
from quantpilot_core.tdx_prediction_integration import build_next_day_experience_plan_v1


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--production-manifest", required=True)
    parser.add_argument("--decision-session", required=True)
    parser.add_argument("--state-path", required=True)
    parser.add_argument("--report-path", required=True)
    parser.add_argument("--input-json", default=None)
    parser.add_argument("--live-market-data", action="store_true")
    parser.add_argument("--dsn-env-var", default="QUANTPILOT_POSTGRES_DSN")
    parser.add_argument("--test-store", action="store_true")
    parser.add_argument("--cache-path", default=".cache/quantpilot/active_shadow")
    parser.add_argument("--timeout", type=float, default=30.0)
    parser.add_argument("--allowed-roles", default="")
    parser.add_argument("--enable-active-shadow", action="store_true")
    parser.add_argument("--enable-live-ai", action="store_true")
    parser.add_argument("--max-physical-model-calls", type=int, default=0)
    parser.add_argument("--max-estimated-api-cost", type=float, default=0.0)
    parser.add_argument("--estimated-cost-per-call", type=float, default=0.0)
    parser.add_argument(
        "--experience-plan-path",
        default=None,
        help="Optional compact next-day TDX experience plan output path.",
    )
    parser.add_argument("--experience-top-n", type=int, default=10)
    args = parser.parse_args()

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
        parser.error(str(exc))

    dsn = os.environ.get(args.dsn_env_var)
    if not args.test_store and not dsn:
        parser.error("set the DSN environment variable or use explicit --test-store")

    pipeline = load_production_pipeline_config(
        manifest_path=args.production_manifest,
        decision_session=args.decision_session,
        state_path=args.state_path,
        report_path=args.report_path,
        live_market_data=args.live_market_data,
        input_payload=load_production_input_payload(args.input_json),
    )

    store = (
        InMemoryReportingStore()
        if args.test_store
        else PostgreSQLReportingStore(dsn)
    )
    result = ContinuousPaperCycle(store).run_once(
        ContinuousPaperCycleConfig(
            pipeline,
            run_id=f"manual-{args.decision_session}",
            active_shadow=shadow,
        )
    )
    experience_plan_path = None
    experience_candidate_count = 0
    if args.experience_plan_path:
        production_report = json.loads(Path(args.report_path).read_text(encoding="utf-8"))
        plan = build_next_day_experience_plan_v1(
            production_report,
            active_shadow_report=result.shadow_report,
            top_n=args.experience_top_n,
        )
        experience_plan_path = write_report_atomic(plan, args.experience_plan_path)
        experience_candidate_count = int(plan["candidate_count"])
    print(
        f"session_id={result.session_id} status={result.status} run_id={result.run_id} "
        f"experience_candidate_count={experience_candidate_count} "
        f"experience_plan_path={experience_plan_path}"
    )


if __name__ == "__main__":
    main()
