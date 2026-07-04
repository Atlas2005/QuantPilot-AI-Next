"""Manual comparison for A-share tradability metadata enrichment v1."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field, replace
from pathlib import Path
from typing import Any, Callable, Mapping

import pandas as pd

from quantpilot_core.evaluation.a_share_market_reality_execution import (
    AShareMarketRealityExecutionConfig,
    AShareMarketRealityExecutionReport,
    run_a_share_market_reality_execution_v1,
)
from quantpilot_core.evaluation.ml_ranking_robustness_walkforward import (
    MLRankingRobustnessWalkForwardConfig,
)


DEFAULT_A_SHARE_TRADABILITY_METADATA_ENRICHMENT_REPORT_ARTIFACT_PATH = Path(
    "artifacts/a_share_tradability_metadata_enrichment/latest_report.json"
)


@dataclass(frozen=True)
class AShareTradabilityMetadataEnrichmentConfig:
    robustness_config: MLRankingRobustnessWalkForwardConfig = field(
        default_factory=lambda: MLRankingRobustnessWalkForwardConfig(artifact_path=None)
    )
    artifact_path: str | Path | None = DEFAULT_A_SHARE_TRADABILITY_METADATA_ENRICHMENT_REPORT_ARTIFACT_PATH
    a_share_execution_config: Mapping[str, Any] = field(default_factory=dict)
    metadata_config: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class AShareTradabilityMetadataEnrichmentReport:
    run_status: str
    provider: str
    date_range: tuple[str, str]
    symbols: tuple[str, ...]
    base_summary: Mapping[str, Any]
    limited_reality_summary: Mapping[str, Any]
    enriched_reality_summary: Mapping[str, Any]
    base_vs_limited_reality_order_deltas: Mapping[str, Any]
    limited_vs_enriched_reality_order_deltas: Mapping[str, Any]
    metadata_coverage_section: Mapping[str, Any]
    report_schema_notes: Mapping[str, Any]
    existing_modules_reused: tuple[str, ...]
    provider_precedence: Mapping[str, tuple[str, ...]]
    no_profitability_claim: bool
    artifact_path: str | None = None


def run_a_share_tradability_metadata_enrichment_v1(
    config: AShareTradabilityMetadataEnrichmentConfig | None = None,
    *,
    price_frame: pd.DataFrame | None = None,
    model_backend_factory: Callable[[], Any] | None = None,
    lightgbm_importer: Callable[[str], Any] | None = None,
) -> AShareTradabilityMetadataEnrichmentReport:
    payload = config or AShareTradabilityMetadataEnrichmentConfig()
    limited = run_a_share_market_reality_execution_v1(
        AShareMarketRealityExecutionConfig(
            robustness_config=replace(payload.robustness_config, artifact_path=None),
            artifact_path=None,
            a_share_execution_config=payload.a_share_execution_config,
        ),
        price_frame=price_frame,
        model_backend_factory=model_backend_factory,
        lightgbm_importer=lightgbm_importer,
    )
    enriched_metadata = {
        **dict(payload.robustness_config.metadata),
        "a_share_tradability_metadata_enrichment_v1": True,
        "a_share_tradability_metadata": dict(payload.metadata_config),
    }
    enriched = run_a_share_market_reality_execution_v1(
        AShareMarketRealityExecutionConfig(
            robustness_config=replace(payload.robustness_config, artifact_path=None, metadata=enriched_metadata),
            artifact_path=None,
            a_share_execution_config=payload.a_share_execution_config,
        ),
        price_frame=price_frame,
        model_backend_factory=model_backend_factory,
        lightgbm_importer=lightgbm_importer,
    )
    report = _build_report(payload, limited, enriched)
    artifact_path = _write_report(report, payload.artifact_path)
    return replace(report, artifact_path=artifact_path) if artifact_path is not None else report


def _build_report(
    config: AShareTradabilityMetadataEnrichmentConfig,
    limited: AShareMarketRealityExecutionReport,
    enriched: AShareMarketRealityExecutionReport,
) -> AShareTradabilityMetadataEnrichmentReport:
    run_status = enriched.run_status
    return AShareTradabilityMetadataEnrichmentReport(
        run_status=run_status,
        provider=enriched.provider,
        date_range=enriched.date_range,
        symbols=enriched.symbols,
        base_summary=limited.base_summary,
        limited_reality_summary=limited.reality_summary,
        enriched_reality_summary=enriched.reality_summary,
        base_vs_limited_reality_order_deltas=limited.base_vs_reality_order_deltas,
        limited_vs_enriched_reality_order_deltas={
            "normalized_quantities_changed": _changed(
                limited.base_vs_reality_order_deltas,
                enriched.base_vs_reality_order_deltas,
                "normalized_quantity_changed_order_count",
            ),
            "fill_quantities_changed": _changed(limited.base_vs_reality_order_deltas, enriched.base_vs_reality_order_deltas, "filled_quantity_changed_order_count"),
            "order_statuses_changed": _changed(limited.base_vs_reality_order_deltas, enriched.base_vs_reality_order_deltas, "status_changed_order_count"),
            "execution_prices_changed": _changed(limited.base_vs_reality_order_deltas, enriched.base_vs_reality_order_deltas, "execution_price_changed_order_count"),
            "costs_changed": _changed(limited.aggregate_results, enriched.aggregate_results, "cost_delta_total"),
            "turnover_changed": _changed(limited.aggregate_results, enriched.aggregate_results, "turnover_delta_total"),
            "returns_changed": _changed(limited.aggregate_results, enriched.aggregate_results, "return_delta_mean"),
            "rejections": enriched.aggregate_results.get("rejected_order_count"),
            "deferrals": enriched.aggregate_results.get("deferred_order_count"),
            "partial_fills": enriched.aggregate_results.get("partial_fill_count"),
        },
        metadata_coverage_section=enriched.metadata_coverage_section,
        report_schema_notes={
            "comparison_key_present": False,
            "aggregate_results_key_present": False,
            "comparison_schema_note": (
                "This report does not use top-level comparison or aggregate_results keys; actual comparisons are represented by "
                "base_summary, limited_reality_summary, enriched_reality_summary, base_vs_limited_reality_order_deltas, "
                "and limited_vs_enriched_reality_order_deltas."
            ),
            "comparison_keys": (
                "base_summary",
                "limited_reality_summary",
                "enriched_reality_summary",
                "base_vs_limited_reality_order_deltas",
                "limited_vs_enriched_reality_order_deltas",
            ),
        },
        existing_modules_reused=(
            "quantpilot_core.real_data_provider.baostock_adapter.BaoStockDailyBarProvider",
            "quantpilot_core.real_data_provider.tushare_adapter.TushareDailyBarProvider",
            "quantpilot_core.real_data_provider.akshare_adapter.AkShareDailyBarProvider",
            "quantpilot_core.a_share_market_reality_execution.execute_a_share_reality_proposal",
            "quantpilot_core.evaluation.ml_ranking_robustness_walkforward.run_ml_ranking_robustness_walkforward_v1",
            "quantpilot_core.paper_trading.PaperAccount",
        ),
        provider_precedence={
            "ohlcv": ("baostock",),
            "amount_pct_turnover_optional": ("baostock", "tushare", "akshare"),
            "board_and_st_status": ("provided_point_in_time_security_master", "symbol_prefix_board_only"),
            "daily_suspension_and_price_limits": ("provided_point_in_time_tradability_overrides", "provider_row", "derived_from_point_in_time_board_st"),
            "corporate_actions": ("provided_point_in_time_corporate_actions",),
        },
        no_profitability_claim=True,
    )


def _changed(before: Mapping[str, Any], after: Mapping[str, Any], key: str) -> bool:
    return before.get(key) != after.get(key)


def _write_report(report: AShareTradabilityMetadataEnrichmentReport, path: str | Path | None) -> str | None:
    if path is None:
        return None
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(asdict(report), ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
    return str(target)
