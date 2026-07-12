#!/usr/bin/env python3
"""Explicit Prefect deployment helper; no schedule starts during import."""
from __future__ import annotations
import argparse


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser()
    p.add_argument("--production-manifest", required=True)
    p.add_argument("--state-path", required=True)
    p.add_argument("--report-path", required=True)
    p.add_argument("--dsn-env-var", default="QUANTPILOT_POSTGRES_DSN")
    p.add_argument("--cron", default="30 16 * * 1-5")
    p.add_argument("--timezone", default="Asia/Shanghai")
    p.add_argument("--max-physical-model-calls", type=int, default=0)
    p.add_argument("--max-estimated-api-cost", type=float, default=0.0)
    p.add_argument("--estimated-cost-per-call", type=float, default=0.0)
    return p


def main() -> None:
    args = parser().parse_args()
    # Deliberately lazy: --help stays useful in minimal/offline environments.
    from quantpilot_core.continuous_paper.prefect_flow import continuous_paper_flow
    if not hasattr(continuous_paper_flow, "serve"):
        raise RuntimeError("install quantpilot-ai-next[continuous-paper] to serve a Prefect deployment")
    parameters = {"production_manifest_path": args.production_manifest, "state_path": args.state_path, "report_path": args.report_path, "dsn_env_var": args.dsn_env_var, "active_shadow": {"max_physical_model_calls_per_cycle": args.max_physical_model_calls, "max_estimated_cost_per_cycle": args.max_estimated_api_cost, "estimated_cost_per_call": args.estimated_cost_per_call}}
    continuous_paper_flow.serve(name="quantpilot-continuous-paper-v1", cron=args.cron, timezone=args.timezone, parameters=parameters)


if __name__ == "__main__": main()
