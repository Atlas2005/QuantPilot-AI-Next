"""Bridge R8 daily-bar providers into the R7 small-sample data gate."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from quantpilot_core.real_data_provider.contracts import (
    DailyBarProvider,
    DailyBarRequest,
    NormalizedDailyBar,
    ProviderName,
)
from quantpilot_core.small_sample_data_gate import (
    SmallSampleAdjustmentPolicyAudit,
    SmallSampleDataClassification,
    SmallSampleDataGateRequest,
    SmallSampleDataGateStatus,
    SmallSampleDataManifest,
    SmallSampleDataScope,
    SmallSampleDataSourceReview,
    SmallSampleLicenseReview,
    SmallSampleSchemaReview,
    SmallSampleStoragePolicy,
    SmallSampleSymbolMappingAudit,
    SmallSampleTimestampAudit,
    validate_small_sample_data_gate_request,
)


EXPECTED_DAILY_BAR_FIELDS = (
    "symbol",
    "trade_date",
    "open",
    "high",
    "low",
    "close",
    "volume",
    "amount",
)


class RealProviderGateBridgeError(Exception):
    """Raised when provider output cannot be bridged into the small-sample gate."""


@dataclass(frozen=True)
class SmallSampleGateBridgeMetadata:
    provider_adapter_probe_plan_reference: str = "R6 provider adapter probe plan"
    approved_r4_gate_decision_reference: str = "R4 approved provider gate decision"
    r3_bridge_compatible: bool = True
    r2_sandbox_fixture_compatible: bool = True
    license_review_status: str = "small_sample_research_only_reviewed"
    commercial_use_notes: str = "Research-only sample; not production approved."
    adjustment_policy_notes: str = "Provider adjustment setting reviewed for sample."
    symbol_mapping_confidence: str = "provider symbol mapped to request symbol"
    timestamp_audit_status: str = "provider trade_date reviewed"
    storage_root: str = "data/small_sample_data_gate"
    storage_version_marker: str = "r9-provider-sample-v1"


@dataclass(frozen=True)
class RealProviderSmallSampleGateResult:
    provider_name: ProviderName
    symbol: str
    start_date: date
    end_date: date
    bar_count: int
    gate_passed: bool
    gate_reasons: tuple[str, ...]


def validate_provider_bars_with_small_sample_gate(
    provider: DailyBarProvider,
    request: DailyBarRequest,
    metadata: SmallSampleGateBridgeMetadata | None = None,
) -> RealProviderSmallSampleGateResult:
    """Fetch provider daily bars and validate their metadata through the R7 gate."""

    bridge_metadata = metadata or SmallSampleGateBridgeMetadata()
    try:
        bars = provider.fetch_daily_bars(request)
    except Exception as exc:
        raise RealProviderGateBridgeError(
            "Provider daily-bar fetch failed before small-sample gate validation."
        ) from exc

    gate_request = _build_gate_request(
        provider_name=provider.provider_name,
        request=request,
        bars=bars,
        metadata=bridge_metadata,
    )
    decision = validate_small_sample_data_gate_request(gate_request)
    return RealProviderSmallSampleGateResult(
        provider_name=provider.provider_name,
        symbol=request.symbol,
        start_date=request.start_date,
        end_date=request.end_date,
        bar_count=len(bars),
        gate_passed=decision.status is SmallSampleDataGateStatus.ALLOWED,
        gate_reasons=tuple(reason.value for reason in decision.rejection_reasons),
    )


def _build_gate_request(
    provider_name: ProviderName,
    request: DailyBarRequest,
    bars: list[NormalizedDailyBar],
    metadata: SmallSampleGateBridgeMetadata,
) -> SmallSampleDataGateRequest:
    min_date = min((bar.trade_date for bar in bars), default=request.start_date)
    max_date = max((bar.trade_date for bar in bars), default=request.end_date)
    symbols = tuple(sorted({bar.symbol for bar in bars}))
    if not symbols:
        symbols = (request.symbol,)

    return SmallSampleDataGateRequest(
        manifest=SmallSampleDataManifest(
            dataset_id=f"r9-{provider_name.value}-{request.symbol}-{request.start_date:%Y%m%d}",
            source_review=SmallSampleDataSourceReview(
                provider_candidate_name=provider_name.value,
                source_project=f"{provider_name.value} optional provider adapter",
                documentation_marker="R9 provider sample bridged through R7 gate",
                provider_adapter_probe_plan_reference=(
                    metadata.provider_adapter_probe_plan_reference
                ),
                approved_r4_gate_decision_reference=(
                    metadata.approved_r4_gate_decision_reference
                ),
                r3_bridge_compatible=metadata.r3_bridge_compatible,
                r2_sandbox_fixture_compatible=metadata.r2_sandbox_fixture_compatible,
            ),
            scope=SmallSampleDataScope(
                symbol_list=symbols,
                start_date=min_date.isoformat(),
                end_date=max_date.isoformat(),
                max_symbols=1,
                max_rows=500,
                max_lookback_days=30,
                declared_row_count=len(bars),
            ),
            license_review=SmallSampleLicenseReview(
                review_status=metadata.license_review_status,
                commercial_use_notes=metadata.commercial_use_notes,
                approved_for_production=False,
            ),
            schema_review=SmallSampleSchemaReview(
                expected_schema_fields=EXPECTED_DAILY_BAR_FIELDS,
                schema_notes="NormalizedDailyBar fields from R8 provider contract.",
                reviewed=bool(bars),
            ),
            timestamp_audit=SmallSampleTimestampAudit(
                audit_status=metadata.timestamp_audit_status,
                timestamp_source="NormalizedDailyBar.trade_date",
                reviewed=bool(bars),
            ),
            adjustment_policy_audit=SmallSampleAdjustmentPolicyAudit(
                adjustment_policy=request.adjustment.value,
                audit_notes=metadata.adjustment_policy_notes,
                reviewed=True,
            ),
            symbol_mapping_audit=SmallSampleSymbolMappingAudit(
                symbol_format="provider symbol equals request symbol",
                mapping_confidence=metadata.symbol_mapping_confidence,
                audit_notes="R9 checks bridged records by manifest scope only.",
                reviewed=all(bar.symbol == request.symbol for bar in bars),
            ),
            storage_policy=SmallSampleStoragePolicy(
                storage_root=metadata.storage_root,
                allowed_storage_path=(
                    f"{metadata.storage_root}/r9_{provider_name.value}_{request.symbol}"
                ),
                version_marker=metadata.storage_version_marker,
            ),
            data_classification=SmallSampleDataClassification.SMALL_SAMPLE_RESEARCH_ONLY,
            no_production_data=True,
            no_broker=True,
            no_live_trading=True,
            no_order_execution=True,
            audit_notes="R9 bridge metadata only; no production data asset is written.",
        ),
        request_notes="R9 provider to small-sample gate integration request.",
    )
