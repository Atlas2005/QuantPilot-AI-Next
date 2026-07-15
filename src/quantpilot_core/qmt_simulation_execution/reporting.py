"""Bounded reporting facts for broker simulation results (never paper fills)."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from .contracts import QmtSimulationOrderResult
from .validation import result_from_mapping, result_to_mapping


QMT_FACT_TABLES = ("qmt_orders", "qmt_fills", "qmt_reconciliation")


def result_to_reporting_facts(
    result: QmtSimulationOrderResult,
) -> dict[str, tuple[Mapping[str, Any], ...]]:
    """Map one validated result into deterministic non-paper fact vocabulary."""

    if not isinstance(result, QmtSimulationOrderResult):
        raise TypeError("result must be QmtSimulationOrderResult")
    validated = result_from_mapping(result_to_mapping(result))
    from .validation import format_utc_timestamp

    generated_at = format_utc_timestamp(validated.generated_at)
    order = {
        "order_id": validated.intent_id,
        "user_order_id": validated.user_order_id,
        "symbol": validated.symbol,
        "side": validated.side,
        "status": validated.status,
        "requested_quantity": validated.requested_quantity,
        "limit_price": validated.limit_price,
        "filled_quantity": validated.filled_quantity,
        "average_fill_price": validated.average_fill_price,
        "order_status": validated.order_status,
        "submission_status": validated.submission_status,
        "broker_order_reference": validated.broker_order_reference,
        "system_order_id": validated.system_order_id,
        "passorder_attempted": validated.passorder_attempted,
        "generated_at": generated_at,
    }
    fills: tuple[Mapping[str, Any], ...] = ()
    if validated.filled_quantity > 0 and validated.deal_count > 0:
        fills = (
            {
                "fill_id": validated.intent_id + ":reconciled",
                "order_id": validated.intent_id,
                "symbol": validated.symbol,
                "side": validated.side,
                "status": validated.status,
                "filled_quantity": validated.filled_quantity,
                "average_fill_price": validated.average_fill_price,
                "deal_count": validated.deal_count,
                "source": "qmt_broker_readback",
                "generated_at": generated_at,
            },
        )
    reconciliation = {
        "reconciliation_id": validated.intent_id,
        "order_id": validated.intent_id,
        "status": validated.status,
        "requested_quantity": validated.requested_quantity,
        "filled_quantity": validated.filled_quantity,
        "deal_count": validated.deal_count,
        "failure_code": validated.failure_code,
        "failure_type": validated.failure_type,
        "latest_snapshot_sequence": validated.latest_snapshot_sequence,
        "checks": {
            "identity_bound": validated.user_order_id == validated.intent_id,
            "quantity_within_request": validated.filled_quantity
            <= validated.requested_quantity,
            "filled_has_deal_evidence": validated.status != "filled"
            or validated.deal_count > 0,
            "classified_as_paper_fill": False,
        },
        "acceptance_limitation": validated.acceptance_limitation,
        "generated_at": generated_at,
    }
    return {
        "qmt_orders": (order,),
        "qmt_fills": fills,
        "qmt_reconciliation": (reconciliation,),
    }


map_result_to_reporting_facts = result_to_reporting_facts
