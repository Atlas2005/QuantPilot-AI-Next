"""Deterministic QMT order/deal readback reconciliation by user order ID."""

from __future__ import annotations

import math
import re
from collections.abc import Iterable, Mapping
from datetime import datetime, timezone
from typing import Any

from .constants import (
    ACCEPTANCE_LIMITATION,
    MAX_BROKER_REFERENCE_LENGTH,
    MAX_DEAL_RECORDS,
    MAX_ORDER_RECORDS,
    PROTOCOL_VERSION,
    REJECTED_ORDER_STATUS_CODES,
    REJECTED_ORDER_STATUS_TEXT,
    SCHEMA_VERSION,
    STRATEGY_NAME,
)
from .contracts import (
    BrokerDealEvidence,
    BrokerOrderEvidence,
    CodeValue,
    QmtSimulationOrderIntent,
    QmtSimulationOrderResult,
    QmtSimulationOrderState,
)
from .errors import BrokerEvidenceError
from .validation import result_from_mapping, result_to_mapping


def reconcile_broker_records(
    intent: QmtSimulationOrderIntent,
    orders: Iterable[object],
    deals: Iterable[object],
    *,
    passorder_attempted: bool,
    generated_at: datetime | None = None,
    latest_snapshot_sequence: int | None = None,
) -> QmtSimulationOrderResult:
    """Reconcile only records whose QMT remark exactly equals ``intent_id``."""

    if not isinstance(intent, QmtSimulationOrderIntent):
        raise TypeError("intent must be QmtSimulationOrderIntent")
    if not isinstance(passorder_attempted, bool):
        raise BrokerEvidenceError("passorder_attempted must be a boolean")
    now = generated_at or datetime.now(timezone.utc)
    if not isinstance(now, datetime) or now.tzinfo is None or now.utcoffset() is None:
        raise BrokerEvidenceError("generated_at must be timezone-aware")
    try:
        normalized_orders, order_failure = _matching_orders(orders, intent)
        normalized_deals, deal_failure = _matching_deals(deals, intent)
    except Exception:
        # Provider exception text and object representations must never cross the protocol.
        normalized_orders = []
        normalized_deals = []
        order_failure = "broker_shape_mismatch"
        deal_failure = None

    selected_order = normalized_orders[0] if normalized_orders else None
    deal_count = len(normalized_deals)
    total_fill = sum(item.fill_quantity for item in normalized_deals)
    weighted_amount = sum(item.fill_quantity * item.fill_price for item in normalized_deals)
    average_fill_price = weighted_amount / total_fill if total_fill else None

    failure_code: str | None = None
    failure_type: str | None = None
    fixed_failure = order_failure or deal_failure
    if len(normalized_orders) > 1:
        fixed_failure = "multiple_broker_orders"
    broker_refs = {
        value
        for value in (
            *(item.broker_order_reference for item in normalized_orders),
            *(item.broker_order_reference for item in normalized_deals),
        )
        if value is not None
    }
    system_ids = {
        value
        for value in (
            *(item.system_order_id for item in normalized_orders),
            *(item.system_order_id for item in normalized_deals),
        )
        if value is not None
    }
    if len(broker_refs) > 1 or len(system_ids) > 1:
        fixed_failure = "multiple_broker_orders"
    if fixed_failure == "broker_evidence_limit_exceeded":
        status = "uncertain"
        failure_code = "broker_evidence_limit_exceeded"
        failure_type = "BrokerEvidenceLimit"
        safe_fill = 0
        average_fill_price = None
        deal_count = min(deal_count, MAX_DEAL_RECORDS)
    elif fixed_failure == "multiple_broker_orders":
        status = "uncertain"
        failure_code = "multiple_broker_orders"
        failure_type = "DuplicateBrokerOrder"
        safe_fill = 0
        average_fill_price = None
    elif fixed_failure == "conflicting_deal_identity":
        status = "uncertain"
        failure_code = "conflicting_deal_identity"
        failure_type = "BrokerDealIdentityConflict"
        safe_fill = 0
        average_fill_price = None
    elif fixed_failure == "broker_quantity_exceeds_request":
        status = "uncertain"
        failure_code = "broker_quantity_exceeds_request"
        failure_type = "BrokerQuantityMismatch"
        safe_fill = 0
        average_fill_price = None
    elif fixed_failure == "broker_shape_mismatch":
        status = "uncertain"
        failure_code = "broker_shape_mismatch"
        failure_type = "BrokerShapeMismatch"
        safe_fill = 0
        average_fill_price = None
    elif total_fill > intent.quantity:
        status = "uncertain"
        failure_code = "broker_quantity_exceeds_request"
        failure_type = "BrokerQuantityMismatch"
        safe_fill = 0
        average_fill_price = None
    elif total_fill == intent.quantity and deal_count > 0:
        status = "filled"
        safe_fill = total_fill
    elif 0 < total_fill < intent.quantity:
        status = "partially_filled"
        safe_fill = total_fill
    elif selected_order is not None and (
        _is_rejected(selected_order.order_status)
        or _is_rejected(selected_order.submission_status)
    ):
        status = "rejected"
        failure_code = "broker_order_rejected"
        failure_type = "BrokerOrderRejection"
        safe_fill = 0
    elif selected_order is not None:
        status = "broker_acknowledged"
        safe_fill = 0
    elif passorder_attempted:
        status = "uncertain"
        failure_code = "broker_readback_pending"
        failure_type = "BrokerReadbackPending"
        safe_fill = 0
    elif now.astimezone(timezone.utc) >= intent.expires_at:
        status = "expired"
        failure_code = "intent_expired"
        failure_type = "IntentExpired"
        safe_fill = 0
    else:
        status = "received"
        safe_fill = 0

    broker_ref = _first_non_null(
        selected_order.broker_order_reference if selected_order else None,
        *(item.broker_order_reference for item in normalized_deals),
    )
    system_order_id = _first_non_null(
        selected_order.system_order_id if selected_order else None,
        *(item.system_order_id for item in normalized_deals),
    )
    order_status: CodeValue = selected_order.order_status if selected_order else None
    submission_status: CodeValue = selected_order.submission_status if selected_order else None
    if selected_order is not None and all(
        value is None for value in (broker_ref, system_order_id, order_status, submission_status)
    ):
        order_status = "observed"

    payload = {
        "schema_version": SCHEMA_VERSION,
        "protocol_version": PROTOCOL_VERSION,
        "intent_id": intent.intent_id,
        "generated_at": _timestamp(now),
        "status": status,
        "expected_redacted_account_id": intent.expected_redacted_account_id,
        "symbol": intent.symbol,
        "side": intent.side,
        "requested_quantity": intent.quantity,
        "limit_price": intent.limit_price,
        "strategy_name": STRATEGY_NAME,
        "user_order_id": intent.intent_id,
        "passorder_attempted": passorder_attempted,
        "broker_order_reference": broker_ref,
        "system_order_id": system_order_id,
        "order_status": order_status,
        "submission_status": submission_status,
        "filled_quantity": safe_fill,
        "average_fill_price": average_fill_price,
        "deal_count": deal_count,
        "failure_code": failure_code,
        "failure_type": failure_type,
        "latest_snapshot_sequence": latest_snapshot_sequence,
        "acceptance_limitation": ACCEPTANCE_LIMITATION,
    }
    return result_from_mapping(payload)


def reconcile_order_and_deals(*args: Any, **kwargs: Any) -> QmtSimulationOrderResult:
    """Readable alias retained for callers that use the protocol terminology."""

    return reconcile_broker_records(*args, **kwargs)


def state_from_result(result: QmtSimulationOrderResult) -> QmtSimulationOrderState:
    """Project a reconciled result onto the local transition record."""

    from .validation import state_from_mapping

    return state_from_mapping(
        {
            "schema_version": result.schema_version,
            "protocol_version": result.protocol_version,
            "intent_id": result.intent_id,
            "updated_at": _timestamp(result.generated_at),
            "status": result.status,
            "expected_redacted_account_id": result.expected_redacted_account_id,
            "passorder_attempted": result.passorder_attempted,
            "failure_code": result.failure_code,
        }
    )


def _matching_orders(
    records: Iterable[object], intent: QmtSimulationOrderIntent
) -> tuple[list[BrokerOrderEvidence], str | None]:
    result: list[BrokerOrderEvidence] = []
    count = 0
    try:
        iterator = iter(records)
    except TypeError as exc:
        raise BrokerEvidenceError("broker orders must be iterable") from exc
    for raw in iterator:
        count += 1
        if count > MAX_ORDER_RECORDS:
            return result, "broker_evidence_limit_exceeded"
        remark = _field(raw, "user_order_id", "investment_remark", "m_strRemark", "remark")
        if remark != intent.intent_id:
            continue
        if not _shape_matches_intent(raw, intent, deal=False):
            return result, "broker_shape_mismatch"
        original_quantity = _field(
            raw,
            "original_quantity",
            "m_nVolumeTotalOriginal",
            "m_nOrderVolume",
            "m_nOrderAmount",
            "m_nVolume",
        )
        if original_quantity is not None:
            parsed_original = _positive_int(original_quantity)
            if parsed_original != intent.quantity:
                return result, (
                    "broker_quantity_exceeds_request"
                    if parsed_original > intent.quantity
                    else "broker_shape_mismatch"
                )
        raw_filled = _field(
            raw,
            "filled_quantity",
            "m_nVolumeTraded",
            "m_nTradedVolume",
            "m_nDealAmount",
        )
        filled_quantity = _optional_nonnegative_int(raw_filled)
        if filled_quantity is not None and filled_quantity > intent.quantity:
            return result, "broker_quantity_exceeds_request"
        result.append(
            BrokerOrderEvidence(
                user_order_id=intent.intent_id,
                broker_order_reference=_optional_text(
                    _field(raw, "broker_order_reference", "m_strOrderRef", "m_nRef")
                ),
                system_order_id=_optional_text(
                    _field(raw, "system_order_id", "m_strOrderSysID", "m_strOrderSysId")
                ),
                order_status=_code(
                    _field(raw, "order_status", "m_nOrderStatus", "m_strOrderStatus")
                ),
                submission_status=_code(
                    _field(
                        raw,
                        "submission_status",
                        "m_nOrderSubmitStatus",
                        "m_strOrderSubmitStatus",
                        "m_nSubmitStatus",
                    )
                ),
                filled_quantity=filled_quantity,
                average_fill_price=_optional_positive_number(
                    _field(raw, "average_fill_price", "average_traded_price", "m_dTradedPrice")
                ),
            )
        )
    return result, None


def _matching_deals(
    records: Iterable[object], intent: QmtSimulationOrderIntent
) -> tuple[list[BrokerDealEvidence], str | None]:
    result: list[BrokerDealEvidence] = []
    identities: dict[str, tuple[int, float, str | None, str | None]] = {}
    count = 0
    try:
        iterator = iter(records)
    except TypeError as exc:
        raise BrokerEvidenceError("broker deals must be iterable") from exc
    for raw in iterator:
        count += 1
        if count > MAX_DEAL_RECORDS:
            return result, "broker_evidence_limit_exceeded"
        remark = _field(raw, "user_order_id", "investment_remark", "m_strRemark", "remark")
        if remark != intent.intent_id:
            continue
        if not _shape_matches_intent(raw, intent, deal=True):
            return result, "broker_shape_mismatch"
        quantity = _positive_int(
            _field(raw, "fill_quantity", "m_nVolume", "m_nDealAmount", "m_nTradedVolume")
        )
        price = _positive_number(_field(raw, "fill_price", "m_dPrice", "m_dTradedPrice"))
        deal_id = _optional_text(
            _field(
                raw,
                "deal_id",
                "trade_id",
                "m_strTradeID",
                "m_nTradeID",
                "m_strDealNo",
            )
        )
        broker_reference = _optional_text(
            _field(
                raw,
                "broker_order_reference",
                "order_reference",
                "m_strOrderRef",
                "m_nRef",
            )
        )
        system_order_id = _optional_text(
            _field(raw, "system_order_id", "m_strOrderSysID", "m_strOrderSysId")
        )
        if deal_id is not None and deal_id in identities:
            if identities[deal_id] != (
                quantity,
                price,
                broker_reference,
                system_order_id,
            ):
                return result, "conflicting_deal_identity"
            continue
        if deal_id is not None:
            identities[deal_id] = (
                quantity,
                price,
                broker_reference,
                system_order_id,
            )
        result.append(
            BrokerDealEvidence(
                user_order_id=intent.intent_id,
                deal_id=deal_id,
                fill_quantity=quantity,
                fill_price=price,
                broker_order_reference=broker_reference,
                system_order_id=system_order_id,
            )
        )
    return result, None


def _shape_matches_intent(
    raw: object,
    intent: QmtSimulationOrderIntent,
    *,
    deal: bool,
) -> bool:
    symbol = _broker_symbol(raw)
    if symbol is not None and symbol != intent.symbol:
        if not (
            isinstance(symbol, str)
            and re.fullmatch(r"[0-9]{6}", symbol) is not None
            and symbol == intent.symbol.split(".", 1)[0]
        ):
            return False
    if not _record_side_matches(raw, intent.side):
        return False
    if deal:
        requested = _field(raw, "requested_quantity", "original_quantity")
        if requested is not None:
            try:
                if _positive_int(requested) != intent.quantity:
                    return False
            except BrokerEvidenceError:
                return False
    return True


def _record_side_matches(raw: object, expected: str) -> bool:
    present = False
    recognized: list[str] = []
    for name in (
        "side",
        "m_nOperation",
        "operation_code",
        "m_nOffsetFlag",
        "m_nDirection",
        "operation_label",
        "m_strOptName",
    ):
        value = _field(raw, name)
        if value is None:
            continue
        present = True
        normalized = _normalized_side(value)
        if normalized is not None:
            recognized.append(normalized)
    if not present:
        return True
    return bool(recognized) and all(value == expected for value in recognized)


def _normalized_side(value: object) -> str | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        if value in {23, 48}:
            return "buy"
        if value in {24, 49}:
            return "sell"
        return None
    if not isinstance(value, str):
        return None
    normalized = value.strip().casefold()
    buy = {
        "buy",
        "b",
        "23",
        "48",
        "买入",
        "buy display",
        "buy order",
        "buy trade",
        "证券买入",
        "普通买入",
    }
    sell = {
        "sell",
        "s",
        "24",
        "49",
        "卖出",
        "sell display",
        "sell order",
        "sell trade",
        "证券卖出",
        "普通卖出",
    }
    if normalized in buy:
        return "buy"
    if normalized in sell:
        return "sell"
    return None


def _broker_symbol(raw: object) -> object | None:
    symbol = _field(raw, "symbol", "m_strInstrumentID", "m_strStockCode")
    if symbol is None or not isinstance(symbol, str):
        return symbol
    cleaned = symbol.upper().replace(" ", "")
    suffix_map = {
        "SH": "SH",
        "SSE": "SH",
        "SHSE": "SH",
        "XSHG": "SH",
        "SZ": "SZ",
        "SZE": "SZ",
        "SZSE": "SZ",
        "XSHE": "SZ",
        "BJ": "BJ",
        "BSE": "BJ",
        "XBSE": "BJ",
    }
    if "." in cleaned:
        code, suffix = cleaned.rsplit(".", 1)
        return code + "." + suffix_map.get(suffix, suffix)
    exchange = _field(raw, "exchange", "m_strExchangeID")
    if isinstance(exchange, str) and exchange.strip():
        suffix = exchange.strip().upper()
        return cleaned + "." + suffix_map.get(suffix, suffix)
    return cleaned


def _field(value: object, *names: str) -> object | None:
    if isinstance(value, Mapping):
        for name in names:
            if name in value:
                return value[name]
        return None
    for name in names:
        try:
            candidate = getattr(value, name)
        except AttributeError:
            continue
        except Exception as exc:
            raise BrokerEvidenceError("broker evidence field cannot be inspected safely") from exc
        return candidate
    return None


def _optional_text(value: object) -> str | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (str, int)):
        raise BrokerEvidenceError("broker reference is outside protocol bounds")
    text = str(value)
    if (
        not text
        or len(text) > MAX_BROKER_REFERENCE_LENGTH
        or any(character in text for character in ("\x00", "\r", "\n"))
    ):
        raise BrokerEvidenceError("broker reference is outside protocol bounds")
    return text


def _code(value: object) -> CodeValue:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (str, int)):
        raise BrokerEvidenceError("broker status is outside protocol bounds")
    if isinstance(value, int):
        if not (-2_147_483_648 <= value <= 2_147_483_647):
            raise BrokerEvidenceError("broker status is outside protocol bounds")
        return value
    if not value or len(value) > 128 or any(c in value for c in ("\x00", "\r", "\n")):
        raise BrokerEvidenceError("broker status is outside protocol bounds")
    normalized = value.strip().casefold()
    if re.fullmatch(r"-?[0-9]{1,10}", normalized) is not None:
        parsed = int(normalized)
        if -2_147_483_648 <= parsed <= 2_147_483_647:
            return parsed
    if normalized.startswith(("rejected", "reject", "invalid", "waste", "废单")):
        return "rejected"
    if normalized.startswith(("partial", "部成")):
        return "partially_filled"
    if normalized.startswith(("filled", "complete", "已成")):
        return "filled"
    if normalized.startswith(("cancel", "已撤", "部撤")):
        return "cancelled"
    if normalized.startswith(("pending", "wait", "待")):
        return "pending"
    if normalized.startswith(("accept", "ack", "reported", "已报")):
        return "accepted"
    if normalized in {"observed", "unknown"}:
        return normalized
    return "unknown"


def _positive_int(value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or not (0 < value <= 2_147_483_647):
        raise BrokerEvidenceError("broker fill quantity is outside protocol bounds")
    return value


def _optional_nonnegative_int(value: object) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int) or not (0 <= value <= 2_147_483_647):
        raise BrokerEvidenceError("broker quantity is outside protocol bounds")
    return value


def _positive_number(value: object) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise BrokerEvidenceError("broker fill price is outside protocol bounds")
    converted = float(value)
    if not math.isfinite(converted) or converted <= 0 or converted > 1_000_000_000:
        raise BrokerEvidenceError("broker fill price is outside protocol bounds")
    return converted


def _optional_positive_number(value: object) -> float | None:
    if value is None:
        return None
    return _positive_number(value)


def _is_rejected(value: CodeValue) -> bool:
    if value in REJECTED_ORDER_STATUS_CODES:
        return True
    if isinstance(value, str):
        return value.strip().casefold() in REJECTED_ORDER_STATUS_TEXT
    return False


def _first_non_null(*values: str | None) -> str | None:
    return next((value for value in values if value is not None), None)


def _timestamp(value: datetime) -> str:
    from .validation import format_utc_timestamp

    return format_utc_timestamp(value)
