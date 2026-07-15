#coding:gbk
"""QMT built-in Python 3.6 read-only snapshot exporter.

Copy this ASCII-only source into the QMT strategy editor.  The account and
accountType globals are supplied by QMT when the strategy is added from the
model-trading screen.  Runtime output is written outside the repository.  A
64-character lowercase hex binding key must already exist at
state/account_binding_key_v1.hex beneath the configured bridge root.
"""

import datetime
import errno
import hashlib
import hmac
import json
import math
import os
import platform
import struct
import sys
import time


SCHEMA_VERSION = 1
BRIDGE_VERSION = "qmt_builtin_readonly_bridge_v1"
PROVIDER = "qmt_builtin_bridge"
ENVIRONMENT = "simulation_signal"
DEFAULT_BRIDGE_ROOT = r"D:\QuantPilotQMTBridge"
BRIDGE_ROOT = os.environ.get("QUANTPILOT_QMT_BRIDGE_ROOT", DEFAULT_BRIDGE_ROOT)
SNAPSHOT_FILENAME = "latest_snapshot_v1.json"
LOCK_FILENAME = "qmt_builtin_exporter_v1.lock"
ACCOUNT_BINDING_KEY_FILENAME = "account_binding_key_v1.hex"
MAX_RECORDS_PER_SECTION = 5000
MAX_PROVIDER_METADATA_FIELDS = 32
MAX_PROVIDER_ATTRIBUTES_SCANNED = 512
MAX_STRING_LENGTH = 256
MAX_IDENTIFIER_LENGTH = 128
MAX_FAILURES = 16
MIN_INTERVAL_SECONDS = 5
MAX_INTERVAL_SECONDS = 3600
ACCOUNT_BINDING_HMAC_DOMAIN = b"quantpilot:qmt-account-binding:v1\x00"
SAFE_INITIALIZATION_ERROR = "QMT read-only exporter initialization failed"
MAX_EXISTING_SNAPSHOT_BYTES = 8 * 1024 * 1024


def _configured_interval_seconds():
    raw = os.environ.get("QUANTPILOT_QMT_HEARTBEAT_INTERVAL_SECONDS", "30")
    try:
        value = int(raw)
    except (TypeError, ValueError):
        value = 30
    return max(MIN_INTERVAL_SECONDS, min(MAX_INTERVAL_SECONDS, value))


HEARTBEAT_INTERVAL_SECONDS = _configured_interval_seconds()


class _ExporterState(object):
    def __init__(self):
        self.account_id = None
        self.account_type = None
        self.snapshot_account_type = None
        self.redacted_account_id = None
        self.sequence = 0
        self.last_attempt_monotonic = 0.0
        self.timer_registered = False
        self.timer_error_type = None
        self.in_write = False
        self.stopped = False
        self.lock_handle = None
        self.lock_fd = None
        self.lock_mode = None
        self.lock_path = None
        self.bridge_root = None


G = _ExporterState()


SENSITIVE_FIELD_PARTS = (
    "accountid",
    "accountkey",
    "accountnumber",
    "accountno",
    "acctno",
    "fundaccount",
    "stockholder",
    "shareholder",
    "holderaccount",
    "customerid",
    "custid",
    "clientkey",
    "clientid",
    "shareholderid",
    "holderid",
    "identity",
    "certificate",
    "idcard",
    "loginid",
    "phone",
    "mobile",
    "email",
    "address",
    "bankaccount",
    "credential",
    "password",
    "passwd",
    "pwd",
    "secret",
    "token",
    "auth",
    "apikey",
    "privatekey",
)


ACCOUNT_FIELDS = {
    "enabled": ("m_Enable", "m_bEnable"),
    "login_state": ("m_strLoginStatus", "m_nLoginStatus", "m_strStatus"),
    "trading_date": ("m_strTradingDate", "m_strTradingDay"),
    "total_assets": ("m_dBalance", "m_dAssetBalance", "m_dAssureAsset"),
    "available_cash": ("m_dAvailable",),
    "withdrawable_cash": ("m_dFetchBalance",),
    "frozen_cash": ("m_dFrozenCash",),
    "frozen_commission": ("m_dFrozenCommission",),
    "stock_market_value": ("m_dStockValue",),
    "fund_market_value": ("m_dFundValue",),
    "bond_market_value": ("m_dLoanValue", "m_dBondValue"),
    "total_instrument_value": ("m_dInstrumentValue",),
    "position_profit": ("m_dPositionProfit",),
    "entrust_asset": ("m_dEntrustAsset",),
    "assure_asset": ("m_dAssureAsset",),
    "provider_status": ("m_strStatus",),
}


POSITION_FIELDS = {
    "instrument": ("m_strInstrumentID",),
    "exchange": ("m_strExchangeID",),
    "instrument_name": ("m_strInstrumentName",),
    "total_quantity": ("m_nVolume",),
    "available_quantity": ("m_nCanUseVolume",),
    "frozen_quantity": ("m_nFrozenVolume",),
    "on_road_quantity": ("m_nOnRoadVolume",),
    "yesterday_quantity": ("m_nYesterdayVolume", "m_nYestodayVolume"),
    "average_cost": ("m_dAvgOpenPrice", "m_dOpenPrice", "m_dSingleCost"),
    "open_cost": ("m_dOpenPrice", "m_dPositionCost", "m_dOpenCost"),
    "latest_price": ("m_dLastPrice", "m_dSettlementPrice"),
    "market_value": ("m_dMarketValue", "m_dInstrumentValue"),
    "floating_profit": ("m_dFloatProfit", "m_dPositionProfit"),
    "profit_ratio": ("m_dProfitRate",),
    "trading_day": ("m_strTradingDay", "m_strTradingDate"),
}


ORDER_FIELDS = {
    "broker_order_reference": ("m_strOrderRef", "m_nRef"),
    "system_order_id": ("m_strOrderSysID",),
    "instrument": ("m_strInstrumentID",),
    "exchange": ("m_strExchangeID",),
    "side_code": ("m_nOffsetFlag", "m_nDirection"),
    "operation_label": ("m_strOptName",),
    "order_price_type": ("m_nOrderPriceType",),
    "limit_price": ("m_dLimitPrice",),
    "original_quantity": ("m_nVolumeTotalOriginal",),
    "filled_quantity": ("m_nVolumeTraded",),
    "remaining_quantity": ("m_nVolumeTotal",),
    "cancelled_quantity": ("m_dCancelAmount", "m_nCancelAmount"),
    "average_traded_price": ("m_dTradedPrice",),
    "order_status": ("m_nOrderStatus", "m_strOrderStatus"),
    "submission_status": ("m_nOrderSubmitStatus", "m_strOrderSubmitStatus"),
    "error_id": ("m_nErrorID",),
    "error_message": ("m_strErrorMsg",),
    "cancel_information": ("m_strCancelInfo",),
    "insert_date": ("m_strInsertDate",),
    "insert_time": ("m_strInsertTime",),
    "trade_amount": ("m_dTradeAmount",),
    "investment_remark": ("m_strRemark",),
}


TRADE_FIELDS = {
    "trade_id": ("m_strTradeID", "m_nTradeID"),
    "order_reference": ("m_strOrderRef", "m_nRef"),
    "system_order_id": ("m_strOrderSysID",),
    "instrument": ("m_strInstrumentID",),
    "exchange": ("m_strExchangeID",),
    "side_code": ("m_nOffsetFlag", "m_nDirection"),
    "operation_label": ("m_strOptName",),
    "fill_price": ("m_dPrice", "m_dTradedPrice"),
    "fill_quantity": ("m_nVolume", "m_nVolumeTraded"),
    "fill_amount": ("m_dTradeAmount",),
    "commission": ("m_dCommission", "m_dComission"),
    "trade_date": ("m_strTradeDate", "m_strInsertDate"),
    "trade_time": ("m_strTradeTime", "m_strInsertTime"),
    "investment_remark": ("m_strRemark",),
}


def _all_source_fields(field_map):
    result = set()
    for candidates in field_map.values():
        result.update(candidates)
    return result


def _utc_now_text():
    value = datetime.datetime.now(datetime.timezone.utc).replace(microsecond=0).isoformat()
    return value.replace("+00:00", "Z")


def _bounded_string(value, limit=MAX_STRING_LENGTH):
    if value is None:
        return None
    if isinstance(value, bytes):
        try:
            text = value.decode("gbk", "replace")
        except Exception:
            text = value.decode("utf-8", "replace")
    elif isinstance(value, str):
        text = value
    elif isinstance(value, (int, float)) and not isinstance(value, bool):
        if isinstance(value, float) and not math.isfinite(value):
            return None
        text = str(value)
    else:
        return None
    text = text.replace("\x00", "")
    text = text.strip()
    if not text:
        return None
    return text[:limit]


def _finite_number(value):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    if isinstance(value, float) and not math.isfinite(value):
        return None
    return value


def _integer(value):
    value = _finite_number(value)
    if value is None:
        return None
    if isinstance(value, float) and not value.is_integer():
        return None
    try:
        return int(value)
    except (TypeError, ValueError, OverflowError):
        return None


def _boolean(value):
    if isinstance(value, bool):
        return value
    if value in (0, 1):
        return bool(value)
    text = _bounded_string(value, 16)
    if text is None:
        return None
    lowered = text.lower()
    if lowered in ("true", "yes", "enabled", "online", "1"):
        return True
    if lowered in ("false", "no", "disabled", "offline", "0"):
        return False
    return None


def _identifier(value):
    return _provider_string(value, MAX_IDENTIFIER_LENGTH)


def _is_sensitive_field(name):
    normalized = "".join(character for character in name.lower() if character.isalnum())
    return any(part in normalized for part in SENSITIVE_FIELD_PARTS)


def _provider_string(value, limit=MAX_STRING_LENGTH):
    text = _bounded_string(value, limit)
    raw_account = _bounded_string(G.account_id, 512)
    if text is None or raw_account is None or raw_account not in text:
        return text
    replacement = G.redacted_account_id or "[redacted-account]"
    return text.replace(raw_account, replacement)[:limit]


def _read_candidate(obj, candidates, provenance, canonical_field):
    first_present = None
    for name in candidates:
        present = False
        value = None
        if isinstance(obj, dict):
            if name in obj:
                present = True
                value = obj.get(name)
        else:
            try:
                value = getattr(obj, name)
                present = True
            except (AttributeError, TypeError):
                present = False
            except Exception:
                present = False
        if not present:
            continue
        if first_present is None:
            first_present = name
        if value is not None:
            provenance.setdefault(canonical_field, set()).add(name)
            return value
    if first_present is not None:
        provenance.setdefault(canonical_field, set()).add(first_present)
    return None


def _take(obj, field_map, canonical_field, provenance, converter):
    value = _read_candidate(obj, field_map[canonical_field], provenance, canonical_field)
    if converter is _bounded_string:
        return _provider_string(value)
    return converter(value)


def _primitive_metadata_value(value):
    if value is None or isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return _finite_number(value)
    if isinstance(value, (str, bytes)):
        text = _bounded_string(value)
        raw_account = _bounded_string(G.account_id, 512)
        if text is not None and raw_account is not None and raw_account in text:
            return None
        return text
    return None


def _provider_metadata(obj, known_fields):
    if isinstance(obj, dict):
        names = sorted(name for name in obj if isinstance(name, str))
    else:
        try:
            names = sorted(name for name in dir(obj) if isinstance(name, str))
        except Exception:
            names = []
    metadata = {}
    scanned = 0
    for name in names:
        if scanned >= MAX_PROVIDER_ATTRIBUTES_SCANNED:
            break
        scanned += 1
        if len(metadata) >= MAX_PROVIDER_METADATA_FIELDS:
            break
        if (
            not name
            or len(name) > 80
            or "\x00" in name
            or name.startswith("_")
            or name in known_fields
            or _is_sensitive_field(name)
        ):
            continue
        try:
            value = obj.get(name) if isinstance(obj, dict) else getattr(obj, name)
        except Exception:
            continue
        if callable(value):
            continue
        primitive = _primitive_metadata_value(value)
        if primitive is None and value is not None:
            continue
        metadata[name] = primitive
    return metadata


def _normalized_account_identity_bytes(account_id):
    if isinstance(account_id, bool) or not isinstance(account_id, (str, int)):
        raise ValueError(SAFE_INITIALIZATION_ERROR)
    try:
        raw = str(account_id).strip().encode("utf-8")
    except Exception:
        raise ValueError(SAFE_INITIALIZATION_ERROR) from None
    if not raw or len(raw) > 512:
        raise ValueError(SAFE_INITIALIZATION_ERROR)
    return raw


def _redact_account_id(account_id, binding_key):
    if not isinstance(binding_key, bytes) or len(binding_key) != 32:
        raise ValueError(SAFE_INITIALIZATION_ERROR)
    raw = _normalized_account_identity_bytes(account_id)
    digest = hmac.new(
        binding_key,
        ACCOUNT_BINDING_HMAC_DOMAIN + raw,
        hashlib.sha256,
    ).hexdigest()
    return "qmtacct-v1-" + digest[:24]


def _normalize_symbol(instrument, exchange):
    instrument_text = _bounded_string(instrument, 32)
    exchange_text = _bounded_string(exchange, 16)
    if instrument_text is None:
        return None
    instrument_text = instrument_text.upper().replace(" ", "")
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
    if "." in instrument_text:
        code, suffix = instrument_text.rsplit(".", 1)
        suffix = suffix_map.get(suffix, suffix)
        return (code + "." + suffix)[:32]
    if exchange_text is None:
        return instrument_text[:32]
    suffix = suffix_map.get(exchange_text.upper(), exchange_text.upper())
    return (instrument_text + "." + suffix)[:32]


def _normalize_side(side_code, operation_label):
    code = _integer(side_code)
    if code == 48:
        return "BUY"
    if code == 49:
        return "SELL"
    label = _bounded_string(operation_label, 64)
    if label is not None:
        lowered = label.lower()
        if "buy" in lowered or "\u4e70" in label:
            return "BUY"
        if "sell" in lowered or "\u5356" in label:
            return "SELL"
    return "UNKNOWN"


def _normalize_account(obj, redacted_account_id, account_type, provenance=None):
    provenance = provenance if provenance is not None else {}
    known = _all_source_fields(ACCOUNT_FIELDS)
    enabled = _take(obj, ACCOUNT_FIELDS, "enabled", provenance, _boolean)
    return {
        "redacted_account_id": redacted_account_id,
        "account_type": _bounded_string(account_type, 32),
        "enabled": enabled,
        "login_state": _take(obj, ACCOUNT_FIELDS, "login_state", provenance, _bounded_string),
        "trading_date": _take(obj, ACCOUNT_FIELDS, "trading_date", provenance, _bounded_string),
        "total_assets": _take(obj, ACCOUNT_FIELDS, "total_assets", provenance, _finite_number),
        "available_cash": _take(obj, ACCOUNT_FIELDS, "available_cash", provenance, _finite_number),
        "withdrawable_cash": _take(obj, ACCOUNT_FIELDS, "withdrawable_cash", provenance, _finite_number),
        "frozen_cash": _take(obj, ACCOUNT_FIELDS, "frozen_cash", provenance, _finite_number),
        "frozen_commission": _take(obj, ACCOUNT_FIELDS, "frozen_commission", provenance, _finite_number),
        "stock_market_value": _take(obj, ACCOUNT_FIELDS, "stock_market_value", provenance, _finite_number),
        "fund_market_value": _take(obj, ACCOUNT_FIELDS, "fund_market_value", provenance, _finite_number),
        "bond_market_value": _take(obj, ACCOUNT_FIELDS, "bond_market_value", provenance, _finite_number),
        "total_instrument_value": _take(obj, ACCOUNT_FIELDS, "total_instrument_value", provenance, _finite_number),
        "position_profit": _take(obj, ACCOUNT_FIELDS, "position_profit", provenance, _finite_number),
        "entrust_asset": _take(obj, ACCOUNT_FIELDS, "entrust_asset", provenance, _finite_number),
        "assure_asset": _take(obj, ACCOUNT_FIELDS, "assure_asset", provenance, _finite_number),
        "provider_status": _take(obj, ACCOUNT_FIELDS, "provider_status", provenance, _bounded_string),
        "provider_metadata": _provider_metadata(obj, known),
    }


def _empty_account(redacted_account_id, account_type):
    return _normalize_account({}, redacted_account_id, account_type, {})


def _normalize_position(obj, provenance=None):
    provenance = provenance if provenance is not None else {}
    known = _all_source_fields(POSITION_FIELDS)
    instrument = _identifier(
        _read_candidate(obj, POSITION_FIELDS["instrument"], provenance, "symbol")
    )
    exchange = _identifier(
        _read_candidate(obj, POSITION_FIELDS["exchange"], provenance, "symbol")
    )
    return {
        "symbol": _normalize_symbol(instrument, exchange),
        "instrument_name": _take(obj, POSITION_FIELDS, "instrument_name", provenance, _bounded_string),
        "total_quantity": _take(obj, POSITION_FIELDS, "total_quantity", provenance, _integer),
        "available_quantity": _take(obj, POSITION_FIELDS, "available_quantity", provenance, _integer),
        "frozen_quantity": _take(obj, POSITION_FIELDS, "frozen_quantity", provenance, _integer),
        "on_road_quantity": _take(obj, POSITION_FIELDS, "on_road_quantity", provenance, _integer),
        "yesterday_quantity": _take(obj, POSITION_FIELDS, "yesterday_quantity", provenance, _integer),
        "average_cost": _take(obj, POSITION_FIELDS, "average_cost", provenance, _finite_number),
        "open_cost": _take(obj, POSITION_FIELDS, "open_cost", provenance, _finite_number),
        "latest_price": _take(obj, POSITION_FIELDS, "latest_price", provenance, _finite_number),
        "market_value": _take(obj, POSITION_FIELDS, "market_value", provenance, _finite_number),
        "floating_profit": _take(obj, POSITION_FIELDS, "floating_profit", provenance, _finite_number),
        "profit_ratio": _take(obj, POSITION_FIELDS, "profit_ratio", provenance, _finite_number),
        "trading_day": _take(obj, POSITION_FIELDS, "trading_day", provenance, _bounded_string),
        "provider_metadata": _provider_metadata(obj, known),
    }


def _normalize_order(obj, provenance=None):
    provenance = provenance if provenance is not None else {}
    known = _all_source_fields(ORDER_FIELDS)
    instrument = _identifier(
        _read_candidate(obj, ORDER_FIELDS["instrument"], provenance, "symbol")
    )
    exchange = _identifier(
        _read_candidate(obj, ORDER_FIELDS["exchange"], provenance, "symbol")
    )
    side_code = _integer(
        _read_candidate(obj, ORDER_FIELDS["side_code"], provenance, "side")
    )
    operation_label = _take(obj, ORDER_FIELDS, "operation_label", provenance, _bounded_string)
    return {
        "broker_order_reference": _take(obj, ORDER_FIELDS, "broker_order_reference", provenance, _identifier),
        "system_order_id": _take(obj, ORDER_FIELDS, "system_order_id", provenance, _identifier),
        "symbol": _normalize_symbol(instrument, exchange),
        "side": _normalize_side(side_code, operation_label),
        "operation_label": operation_label,
        "order_price_type": _take(obj, ORDER_FIELDS, "order_price_type", provenance, _integer),
        "limit_price": _take(obj, ORDER_FIELDS, "limit_price", provenance, _finite_number),
        "original_quantity": _take(obj, ORDER_FIELDS, "original_quantity", provenance, _integer),
        "filled_quantity": _take(obj, ORDER_FIELDS, "filled_quantity", provenance, _integer),
        "remaining_quantity": _take(obj, ORDER_FIELDS, "remaining_quantity", provenance, _integer),
        "cancelled_quantity": _take(obj, ORDER_FIELDS, "cancelled_quantity", provenance, _integer),
        "average_traded_price": _take(obj, ORDER_FIELDS, "average_traded_price", provenance, _finite_number),
        "order_status": _take(obj, ORDER_FIELDS, "order_status", provenance, _integer),
        "submission_status": _take(obj, ORDER_FIELDS, "submission_status", provenance, _integer),
        "error_id": _take(obj, ORDER_FIELDS, "error_id", provenance, _integer),
        "error_message": _take(obj, ORDER_FIELDS, "error_message", provenance, _bounded_string),
        "cancel_information": _take(obj, ORDER_FIELDS, "cancel_information", provenance, _bounded_string),
        "insert_date": _take(obj, ORDER_FIELDS, "insert_date", provenance, _bounded_string),
        "insert_time": _take(obj, ORDER_FIELDS, "insert_time", provenance, _bounded_string),
        "trade_amount": _take(obj, ORDER_FIELDS, "trade_amount", provenance, _finite_number),
        "investment_remark": _take(obj, ORDER_FIELDS, "investment_remark", provenance, _bounded_string),
        "provider_metadata": _provider_metadata(obj, known),
    }


def _normalize_trade(obj, provenance=None):
    provenance = provenance if provenance is not None else {}
    known = _all_source_fields(TRADE_FIELDS)
    instrument = _identifier(
        _read_candidate(obj, TRADE_FIELDS["instrument"], provenance, "symbol")
    )
    exchange = _identifier(
        _read_candidate(obj, TRADE_FIELDS["exchange"], provenance, "symbol")
    )
    side_code = _integer(
        _read_candidate(obj, TRADE_FIELDS["side_code"], provenance, "side")
    )
    operation_label = _take(obj, TRADE_FIELDS, "operation_label", provenance, _bounded_string)
    return {
        "trade_id": _take(obj, TRADE_FIELDS, "trade_id", provenance, _identifier),
        "order_reference": _take(obj, TRADE_FIELDS, "order_reference", provenance, _identifier),
        "system_order_id": _take(obj, TRADE_FIELDS, "system_order_id", provenance, _identifier),
        "symbol": _normalize_symbol(instrument, exchange),
        "side": _normalize_side(side_code, operation_label),
        "operation_label": operation_label,
        "fill_price": _take(obj, TRADE_FIELDS, "fill_price", provenance, _finite_number),
        "fill_quantity": _take(obj, TRADE_FIELDS, "fill_quantity", provenance, _integer),
        "fill_amount": _take(obj, TRADE_FIELDS, "fill_amount", provenance, _finite_number),
        "commission": _take(obj, TRADE_FIELDS, "commission", provenance, _finite_number),
        "trade_date": _take(obj, TRADE_FIELDS, "trade_date", provenance, _bounded_string),
        "trade_time": _take(obj, TRADE_FIELDS, "trade_time", provenance, _bounded_string),
        "investment_remark": _take(obj, TRADE_FIELDS, "investment_remark", provenance, _bounded_string),
        "provider_metadata": _provider_metadata(obj, known),
    }


def _bounded_records(raw):
    if raw is None:
        return []
    if isinstance(raw, (list, tuple)):
        return list(raw[:MAX_RECORDS_PER_SECTION])
    try:
        result = []
        for item in raw:
            result.append(item)
            if len(result) >= MAX_RECORDS_PER_SECTION:
                break
        return result
    except TypeError:
        return [raw]


def _safe_exception_type(exc):
    name = _bounded_string(exc.__class__.__name__, 80) or "Exception"
    safe = "".join(
        character
        for character in name
        if character in "._" or "0" <= character <= "9" or "A" <= character <= "Z" or "a" <= character <= "z"
    )
    if not safe or not (safe[0] == "_" or "A" <= safe[0] <= "Z" or "a" <= safe[0] <= "z"):
        return "Exception"
    return safe


def _query_failure(section, exc):
    return {
        "section": section,
        "code": "qmt_query_failed",
        "message": "QMT read-only {0} query failed".format(section),
        "exception_type": _safe_exception_type(exc),
    }


def _query_section(section, qmt_data_type, normalizer, provenance, failures):
    try:
        raw = get_trade_detail_data(
            G.account_id,
            G.account_type,
            qmt_data_type,
        )
        records = []
        for item in _bounded_records(raw):
            records.append(normalizer(item, provenance))
        return records, {"ok": True, "error": None}
    except Exception as exc:
        failures.append(_query_failure(section, exc))
        return [], {"ok": False, "error": "qmt_query_failed"}


def _finalize_provenance(provenance):
    result = {}
    for section in ("account", "positions", "orders", "trades"):
        result[section] = {}
        section_values = provenance.get(section, {})
        for canonical_field in sorted(section_values):
            result[section][canonical_field] = sorted(section_values[canonical_field])
    return result


def _runtime_metadata():
    architecture = "{0}-bit".format(struct.calcsize("P") * 8)
    return {
        "python_version": _bounded_string(platform.python_version(), 32) or "unknown",
        "python_implementation": _bounded_string(platform.python_implementation(), 64),
        "qmt_runtime": "builtin_python",
        "qmt_version": None,
        "platform": _bounded_string(sys.platform, 64),
        "metadata": {
            "architecture": architecture,
            "heartbeat_interval_seconds": HEARTBEAT_INTERVAL_SECONDS,
            "timer_registered": G.timer_registered,
            "timer_error_type": _bounded_string(G.timer_error_type, 80),
            "writer_lock_mode": _bounded_string(G.lock_mode, 32),
        },
    }


def _build_snapshot(sequence):
    failures = []
    provenance = {"account": {}, "positions": {}, "orders": {}, "trades": {}}

    account_records, account_query = _query_section(
        "account",
        "account",
        lambda item, fields: _normalize_account(
            item, G.redacted_account_id, G.snapshot_account_type, fields
        ),
        provenance["account"],
        failures,
    )
    account_record = account_records[0] if account_records else None
    if account_query["ok"] and account_record is None:
        account_query = {"ok": False, "error": "qmt_query_empty"}
        failures.append(
            {
                "section": "account",
                "code": "qmt_query_empty",
                "message": "QMT read-only account query returned no records",
                "exception_type": None,
            }
        )
    positions, positions_query = _query_section(
        "positions", "position", _normalize_position, provenance["positions"], failures
    )
    orders, orders_query = _query_section(
        "orders", "order", _normalize_order, provenance["orders"], failures
    )
    trades, trades_query = _query_section(
        "trades", "deal", _normalize_trade, provenance["trades"], failures
    )

    return {
        "schema_version": SCHEMA_VERSION,
        "bridge_version": BRIDGE_VERSION,
        "generated_at": _utc_now_text(),
        "sequence": sequence,
        "snapshot_id": "qmt-{0}".format(sequence),
        "qmt_trading_date": account_record["trading_date"] if account_record else None,
        "provider": PROVIDER,
        "environment": ENVIRONMENT,
        "redacted_account_id": G.redacted_account_id,
        "account_type": G.snapshot_account_type,
        "account_status": account_record["provider_status"] if account_record else None,
        "account": account_record,
        "positions": positions,
        "orders": orders,
        "trades": trades,
        "query_status": {
            "account": account_query,
            "positions": positions_query,
            "orders": orders_query,
            "trades": trades_query,
        },
        "runtime": _runtime_metadata(),
        "source_field_provenance": _finalize_provenance(provenance),
        "safety": {
            "order_submission_enabled": False,
            "cancel_enabled": False,
            "passorder_invoked": False,
            "cancel_invoked": False,
        },
        "failures": failures[:MAX_FAILURES],
    }


def _bridge_paths(root=None):
    selected = root if root is not None else BRIDGE_ROOT
    root_path = os.path.abspath(selected)
    snapshot_dir = os.path.join(root_path, "snapshots")
    state_dir = os.path.join(root_path, "state")
    return {
        "root": root_path,
        "snapshot_dir": snapshot_dir,
        "snapshot": os.path.join(snapshot_dir, SNAPSHOT_FILENAME),
        "temporary": os.path.join(snapshot_dir, SNAPSHOT_FILENAME + ".tmp"),
        "state_dir": state_dir,
        "lock": os.path.join(state_dir, LOCK_FILENAME),
        "account_binding_key": os.path.join(state_dir, ACCOUNT_BINDING_KEY_FILENAME),
    }


def _ensure_directories(paths):
    for path in (paths["root"], paths["snapshot_dir"], paths["state_dir"]):
        if not os.path.isdir(path):
            try:
                os.makedirs(path)
            except OSError:
                if not os.path.isdir(path):
                    raise


def _acquire_writer_lock(root=None):
    if G.lock_handle is not None or G.lock_fd is not None:
        return False
    paths = _bridge_paths(root)
    _ensure_directories(paths)
    lock_path = paths["lock"]
    try:
        import msvcrt
    except ImportError:
        msvcrt = None

    if msvcrt is not None:
        handle = open(lock_path, "a+b")
        try:
            handle.seek(0, os.SEEK_END)
            if handle.tell() == 0:
                handle.write(b"1")
                handle.flush()
            handle.seek(0)
            msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
        except Exception:
            handle.close()
            return False
        G.lock_handle = handle
        G.lock_mode = "msvcrt"
    else:
        flags = os.O_CREAT | os.O_EXCL | os.O_WRONLY
        try:
            fd = os.open(lock_path, flags, 0o600)
        except OSError:
            return False
        try:
            os.write(fd, b"quantpilot-qmt-readonly-v1\n")
        except Exception:
            os.close(fd)
            try:
                os.unlink(lock_path)
            except OSError:
                pass
            raise
        G.lock_fd = fd
        G.lock_mode = "exclusive_create"

    G.lock_path = lock_path
    G.bridge_root = paths["root"]
    return True


def _release_writer_lock():
    lock_path = G.lock_path
    if G.lock_handle is not None:
        handle = G.lock_handle
        try:
            import msvcrt
            handle.seek(0)
            msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
        except Exception:
            pass
        try:
            handle.close()
        except Exception:
            pass
    if G.lock_fd is not None:
        try:
            os.close(G.lock_fd)
        except Exception:
            pass
        if lock_path:
            try:
                os.unlink(lock_path)
            except OSError:
                pass
    G.lock_handle = None
    G.lock_fd = None
    G.lock_mode = None
    G.lock_path = None


def _reject_duplicate_json_keys(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(SAFE_INITIALIZATION_ERROR)
        result[key] = value
    return result


def _reject_json_constant(value):
    del value
    raise ValueError(SAFE_INITIALIZATION_ERROR)


def _load_account_binding_key(key_path):
    try:
        with open(key_path, "rb") as handle:
            encoded = handle.read(65)
        if len(encoded) != 64:
            raise ValueError(SAFE_INITIALIZATION_ERROR)
        if any(value not in b"0123456789abcdef" for value in encoded):
            raise ValueError(SAFE_INITIALIZATION_ERROR)
        decoded = bytes.fromhex(encoded.decode("ascii"))
        if len(decoded) != 32:
            raise ValueError(SAFE_INITIALIZATION_ERROR)
        return decoded
    except Exception:
        raise ValueError(SAFE_INITIALIZATION_ERROR) from None


def _load_last_sequence(snapshot_path):
    try:
        try:
            os.lstat(snapshot_path)
        except OSError as exc:
            if getattr(exc, "errno", None) == errno.ENOENT:
                return 0
            raise ValueError(SAFE_INITIALIZATION_ERROR)
        with open(snapshot_path, "rb") as handle:
            encoded = handle.read(MAX_EXISTING_SNAPSHOT_BYTES + 1)
        if not encoded or len(encoded) > MAX_EXISTING_SNAPSHOT_BYTES:
            raise ValueError(SAFE_INITIALIZATION_ERROR)
        payload = json.loads(
            encoded.decode("utf-8"),
            object_pairs_hook=_reject_duplicate_json_keys,
            parse_constant=_reject_json_constant,
        )
        if not isinstance(payload, dict):
            raise ValueError(SAFE_INITIALIZATION_ERROR)
        schema_version = payload.get("schema_version")
        if (
            isinstance(schema_version, bool)
            or not isinstance(schema_version, int)
            or schema_version != SCHEMA_VERSION
        ):
            raise ValueError(SAFE_INITIALIZATION_ERROR)
        if payload.get("bridge_version") != BRIDGE_VERSION:
            raise ValueError(SAFE_INITIALIZATION_ERROR)
        sequence = payload.get("sequence")
        if isinstance(sequence, bool) or not isinstance(sequence, int) or sequence < 1:
            raise ValueError(SAFE_INITIALIZATION_ERROR)
        if payload.get("snapshot_id") != "qmt-{0}".format(sequence):
            raise ValueError(SAFE_INITIALIZATION_ERROR)
        return sequence
    except Exception:
        raise ValueError(SAFE_INITIALIZATION_ERROR) from None


def _serialize_snapshot(snapshot):
    return json.dumps(
        snapshot,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    ).encode("utf-8")


def _atomic_write(snapshot, root=None):
    paths = _bridge_paths(root)
    _ensure_directories(paths)
    payload = _serialize_snapshot(snapshot)
    with open(paths["temporary"], "wb") as handle:
        handle.write(payload)
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(paths["temporary"], paths["snapshot"])
    return paths["snapshot"]


def export_qmt_snapshot(ContextInfo):
    del ContextInfo
    if G.stopped or G.in_write:
        return
    if G.lock_handle is None and G.lock_fd is None:
        return
    G.in_write = True
    G.last_attempt_monotonic = time.monotonic()
    try:
        next_sequence = G.sequence + 1
        snapshot = _build_snapshot(next_sequence)
        _atomic_write(snapshot, G.bridge_root)
        G.sequence = next_sequence
    finally:
        G.in_write = False


def init(ContextInfo):
    raw_account = globals().get("account")
    raw_account_type = globals().get("accountType")
    try:
        _normalized_account_identity_bytes(raw_account)
        normalized_account_type = _bounded_string(raw_account_type, 32)
        if normalized_account_type is None:
            raise ValueError(SAFE_INITIALIZATION_ERROR)
    except Exception:
        G.stopped = True
        raise RuntimeError(SAFE_INITIALIZATION_ERROR) from None

    G.stopped = False
    try:
        lock_acquired = _acquire_writer_lock(BRIDGE_ROOT)
    except Exception:
        G.stopped = True
        raise RuntimeError(SAFE_INITIALIZATION_ERROR) from None
    if not lock_acquired:
        G.stopped = True
        raise RuntimeError(SAFE_INITIALIZATION_ERROR)
    try:
        paths = _bridge_paths(G.bridge_root)
        binding_key = _load_account_binding_key(paths["account_binding_key"])
        redacted_account_id = _redact_account_id(raw_account, binding_key)
        del binding_key
        sequence = _load_last_sequence(paths["snapshot"])
        G.account_id = raw_account
        G.account_type = raw_account_type
        G.snapshot_account_type = normalized_account_type.upper()
        G.redacted_account_id = redacted_account_id
        G.sequence = sequence
    except Exception:
        _release_writer_lock()
        G.account_id = None
        G.account_type = None
        G.snapshot_account_type = None
        G.redacted_account_id = None
        G.sequence = 0
        G.stopped = True
        raise RuntimeError(SAFE_INITIALIZATION_ERROR) from None

    try:
        ContextInfo.run_time(
            "export_qmt_snapshot",
            "{0}nSecond".format(HEARTBEAT_INTERVAL_SECONDS),
            "2019-10-14 13:20:00",
        )
        G.timer_registered = True
        G.timer_error_type = None
    except Exception as exc:
        G.timer_registered = False
        G.timer_error_type = _safe_exception_type(exc)


def after_init(ContextInfo):
    export_qmt_snapshot(ContextInfo)


def handlebar(ContextInfo):
    if G.stopped:
        return
    now = time.monotonic()
    interval = HEARTBEAT_INTERVAL_SECONDS
    if G.timer_registered:
        interval = HEARTBEAT_INTERVAL_SECONDS * 2
    if now - G.last_attempt_monotonic < interval:
        return
    try:
        is_last = ContextInfo.is_last_bar()
    except Exception:
        is_last = True
    if is_last:
        export_qmt_snapshot(ContextInfo)


def stop(ContextInfo):
    del ContextInfo
    G.stopped = True
    _release_writer_lock()
    G.account_id = None
