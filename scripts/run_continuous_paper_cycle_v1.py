#!/usr/bin/env python3
"""Manual, offline-safe entry point for one continuous paper cycle."""
from __future__ import annotations
import argparse
import os
from pathlib import Path
from quantpilot_core.continuous_paper import ActiveShadowConfig, ContinuousPaperCycle, ContinuousPaperCycleConfig, InMemoryReportingStore, PostgreSQLReportingStore
from quantpilot_core.production_candidate import load_runtime_manifest
from quantpilot_core.real_candidate_pipeline import RealCandidatePipelineConfig


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--production-manifest", required=True); p.add_argument("--decision-session", required=True)
    p.add_argument("--state-path", required=True); p.add_argument("--report-path", required=True)
    p.add_argument("--dsn-env-var", default="QUANTPILOT_POSTGRES_DSN"); p.add_argument("--test-store", action="store_true")
    p.add_argument("--cache-path", default=".cache/quantpilot/active_shadow"); p.add_argument("--timeout", type=float, default=30.0)
    p.add_argument("--allowed-roles", default=""); p.add_argument("--enable-active-shadow", action="store_true"); p.add_argument("--enable-live-ai", action="store_true")
    p.add_argument("--max-physical-model-calls", type=int, default=0); p.add_argument("--max-estimated-api-cost", type=float, default=0.0); p.add_argument("--estimated-cost-per-call", type=float, default=0.0)
    args = p.parse_args()
    if args.enable_live_ai and (not args.enable_active_shadow or args.max_physical_model_calls <= 0 or args.max_estimated_api_cost <= 0 or args.estimated_cost_per_call <= 0):
        p.error("live AI requires active shadow and positive explicit call, cycle-cost, and per-call cost limits")
    dsn = os.environ.get(args.dsn_env_var)
    if not args.test_store and not dsn: p.error("set the DSN environment variable or use explicit --test-store")
    manifest = load_runtime_manifest(Path(args.production_manifest))
    pipeline = RealCandidatePipelineConfig(decision_session=args.decision_session, state_path=args.state_path, report_path=args.report_path, production_manifest=manifest)
    store = InMemoryReportingStore() if args.test_store else PostgreSQLReportingStore(dsn)
    shadow = ActiveShadowConfig(enabled=args.enable_active_shadow, enable_live_calls=args.enable_live_ai, max_physical_model_calls_per_cycle=args.max_physical_model_calls, max_estimated_cost_per_cycle=args.max_estimated_api_cost, estimated_cost_per_call=args.estimated_cost_per_call, cache_path=args.cache_path, timeout=args.timeout)
    result = ContinuousPaperCycle(store).run_once(ContinuousPaperCycleConfig(pipeline, run_id=f"manual-{args.decision_session}", active_shadow=shadow))
    print(f"session_id={result.session_id} status={result.status} run_id={result.run_id}")


if __name__ == "__main__": main()
