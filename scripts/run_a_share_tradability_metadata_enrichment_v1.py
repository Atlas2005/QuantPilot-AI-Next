#!/usr/bin/env python3
"""Manual BaoStock runner for A-share tradability metadata enrichment v1."""

from __future__ import annotations

import json

from quantpilot_core.evaluation import (
    DEFAULT_A_SHARE_TRADABILITY_METADATA_ENRICHMENT_REPORT_ARTIFACT_PATH,
    AShareTradabilityMetadataEnrichmentConfig,
    MLRankingRobustnessWalkForwardConfig,
    run_a_share_tradability_metadata_enrichment_v1,
)


def main() -> int:
    robustness_config = MLRankingRobustnessWalkForwardConfig(
        start_date="2019-01-01",
        end_date="2024-12-31",
        provider="baostock",
        artifact_path=None,
        metadata={
            "manual_runner": "run_a_share_tradability_metadata_enrichment_v1",
            "no_broker_live_execution": True,
            "no_profitability_claim": True,
        },
    )
    report = run_a_share_tradability_metadata_enrichment_v1(
        AShareTradabilityMetadataEnrichmentConfig(
            robustness_config=robustness_config,
            artifact_path=DEFAULT_A_SHARE_TRADABILITY_METADATA_ENRICHMENT_REPORT_ARTIFACT_PATH,
            a_share_execution_config={
                "max_participation_rate": 0.10,
                "default_price_limit_pct": 0.10,
                "block_one_price_limit": True,
                "enforce_t_plus_one": True,
            },
            metadata_config={
                "primary_price_provider": "baostock",
                "infer_board_from_symbol_prefix": True,
                "fetched_at": "manual_run",
            },
        )
    )
    print(
        json.dumps(
            {
                "run_status": report.run_status,
                "artifact_path": report.artifact_path,
                "metadata_coverage_section": report.metadata_coverage_section,
                "limited_vs_enriched_reality_order_deltas": report.limited_vs_enriched_reality_order_deltas,
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
