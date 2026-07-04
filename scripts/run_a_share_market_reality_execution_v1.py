#!/usr/bin/env python3
"""Manual BaoStock runner for A-share market-reality execution comparison."""

from __future__ import annotations

import json

from quantpilot_core.evaluation import (
    DEFAULT_A_SHARE_MARKET_REALITY_EXECUTION_REPORT_ARTIFACT_PATH,
    AShareMarketRealityExecutionConfig,
    MLRankingRobustnessWalkForwardConfig,
    run_a_share_market_reality_execution_v1,
)


def main() -> int:
    robustness_config = MLRankingRobustnessWalkForwardConfig(
        start_date="2019-01-01",
        end_date="2024-12-31",
        provider="baostock",
        artifact_path=None,
        metadata={
            "manual_runner": "run_a_share_market_reality_execution_v1",
            "no_broker_live_execution": True,
            "no_profitability_claim": True,
        },
    )
    report = run_a_share_market_reality_execution_v1(
        AShareMarketRealityExecutionConfig(
            robustness_config=robustness_config,
            artifact_path=DEFAULT_A_SHARE_MARKET_REALITY_EXECUTION_REPORT_ARTIFACT_PATH,
            a_share_execution_config={
                "max_participation_rate": 0.10,
                "default_price_limit_pct": 0.10,
                "block_one_price_limit": True,
                "enforce_t_plus_one": True,
            },
        )
    )
    print(
        json.dumps(
            {
                "run_status": report.run_status,
                "artifact_path": report.artifact_path,
                "base_summary": report.base_summary,
                "reality_summary": report.reality_summary,
                "aggregate_results": report.aggregate_results,
                "no_profitability_claim": report.no_profitability_claim,
            },
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
