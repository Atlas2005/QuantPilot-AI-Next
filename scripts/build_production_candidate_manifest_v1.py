#!/usr/bin/env python3
"""Offline builder for the compact PR #123 production manifest."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Mapping

from quantpilot_core.production_candidate import build_production_candidate_manifest, load_runtime_manifest, verify_manifest_digest, write_manifest_atomic


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--pr121-artifact", required=True)
    parser.add_argument("--pr122-artifact", required=True)
    parser.add_argument("--output", default="artifacts/production_candidate/latest_manifest.json")
    parser.add_argument("--code-revision", required=True)
    parser.add_argument("--created-at", required=True)
    parser.add_argument("--snapshot-digest")
    parser.add_argument("--capital-profile-id", default="default_paper_capital")
    parser.add_argument("--initial-capital", type=float, required=True)
    parser.add_argument("--target-symbol-count", type=int, required=True)
    parser.add_argument("--target-position-count", type=int, required=True)
    parser.add_argument("--max-execution-symbols", type=int, required=True)
    parser.add_argument("--max-position-weight", type=float, required=True)
    parser.add_argument("--reserve-cash-weight", type=float, required=True)
    parser.add_argument("--min-order-lot", type=int, required=True)
    parser.add_argument("--fee-policy-json", required=True)
    parser.add_argument("--account-policy-json", required=True)
    parser.add_argument("--benchmark-json", required=True)
    args = parser.parse_args()
    pr121 = _load(args.pr121_artifact)
    pr122 = _load(args.pr122_artifact)
    try:
        benchmark = json.loads(args.benchmark_json)
    except json.JSONDecodeError as exc:
        raise SystemExit("--benchmark-json must be valid JSON") from exc
    if not isinstance(benchmark, Mapping) or not benchmark:
        raise SystemExit("--benchmark-json must be a non-empty JSON object")
    if pr121.get("run_status") != "completed" or pr121.get("recommendation") != "equal_weight_baseline" or not pr121.get("common_folds"):
        raise SystemExit("PR #121 artifact must contain recommendation=equal_weight_baseline")
    if pr122.get("mode") not in {"offline_replay", "offline_cached_replay"} or pr122.get("recommendation") != "no_ai_arm" or not isinstance(pr122.get("usage"), Mapping) or "physical_model_calls" not in pr122["usage"]:
        raise SystemExit("PR #122 artifact must contain recommendation=no_ai_arm")
    manifest = build_production_candidate_manifest(
        code_revision=args.code_revision,
        created_at=args.created_at,
        capital_profile_id=args.capital_profile_id,
        snapshot_digest=args.snapshot_digest,
        benchmark=benchmark,
        limitations=("AI incremental profitability is not proven.", "Production execution remains the validated non-LLM arm.", "No snapshot digest was supplied.") if args.snapshot_digest is None else ("AI incremental profitability is not proven.", "Production execution remains the validated non-LLM arm."),
        frozen_strategy_parameters={"initial_capital": args.initial_capital, "target_symbol_count": args.target_symbol_count, "max_execution_symbols": args.max_execution_symbols, "strategy_id": "equal_weight_baseline"},
        frozen_portfolio_parameters={"target_position_count": args.target_position_count, "max_position_weight": args.max_position_weight, "reserve_cash_weight": args.reserve_cash_weight},
        frozen_execution_parameters={"min_order_lot": args.min_order_lot},
        fee_profile_policy=json.loads(args.fee_policy_json),
        account_capability_policy=json.loads(args.account_policy_json),
        source_artifacts={"pr121": args.pr121_artifact, "pr122": args.pr122_artifact},
        evidence_scope={
            "pr121_recommendation": "equal_weight_baseline",
            "pr122_recommendation": "no_ai_arm",
            "pr122_physical_model_calls": pr122["usage"]["physical_model_calls"],
        },
    )
    load_runtime_manifest(manifest)
    if not verify_manifest_digest(manifest): raise SystemExit("manifest digest verification failed")
    print(write_manifest_atomic(manifest, args.output))
    return 0


def _load(path: str) -> Mapping[str, Any]:
    with Path(path).open(encoding="utf-8") as handle:
        value = json.load(handle)
    if not isinstance(value, Mapping): raise SystemExit("artifact must be a JSON object")
    return value


if __name__ == "__main__":
    raise SystemExit(main())
