"""Strict, side-effect-free reader for completed QMT bridge snapshots."""

from __future__ import annotations

import hmac
import json
import math
import re
import threading
from collections.abc import Mapping, Sequence
from datetime import datetime, timezone
from pathlib import Path
from types import MappingProxyType
from typing import Any, NoReturn

from .constants import (
    BRIDGE_VERSION,
    ENVIRONMENT_ID,
    LATEST_SNAPSHOT_RELATIVE_PATH,
    MAX_ERROR_MESSAGE_LENGTH,
    MAX_FAILURES,
    MAX_FUTURE_SKEW_SECONDS,
    MAX_METADATA_ENTRIES,
    MAX_METADATA_KEY_LENGTH,
    MAX_METADATA_TEXT_LENGTH,
    MAX_ORDERS,
    MAX_POSITIONS,
    MAX_PROVENANCE_FIELDS,
    MAX_PROVENANCE_SOURCES,
    MAX_SNAPSHOT_BYTES,
    MAX_TEXT_LENGTH,
    MAX_TRADES,
    PROVIDER_ID,
    QUERY_SECTIONS,
    SCHEMA_VERSION,
    TEMP_SNAPSHOT_RELATIVE_PATH,
)
from .errors import (
    AccountIdentityMismatchError,
    DuplicateSequenceError,
    IncompleteAtomicWriteError,
    InvalidSnapshotValueError,
    MalformedSnapshotError,
    MissingSnapshotError,
    RegressingSequenceError,
    StaleSnapshotError,
    UnsupportedSchemaError,
)
from .records import (
    AccountRecord,
    FailureInfo,
    OrderRecord,
    PositionRecord,
    QmtBridgeSnapshot,
    QueryStatus,
    QueryStatusBundle,
    ReadOnlySafetyState,
    RuntimeMetadata,
    TradeRecord,
)
from .redaction import is_redacted_account_identity, is_sensitive_field_name


_TRADING_DATE_PATTERN = re.compile(r"\A(?:\d{8}|\d{4}-\d{2}-\d{2})\Z")
_UTC_TIMESTAMP_PATTERN = re.compile(
    r"\A\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?Z\Z"
)
_EXCEPTION_TYPE_PATTERN = re.compile(r"\A[A-Za-z_][A-Za-z0-9_.]{0,127}\Z")
_ALLOWED_QUERY_FAILURE_CODES = frozenset({"qmt_query_failed", "qmt_query_empty"})

_ROOT_KEYS = frozenset(
    {
        "schema_version",
        "bridge_version",
        "generated_at",
        "sequence",
        "snapshot_id",
        "qmt_trading_date",
        "provider",
        "environment",
        "redacted_account_id",
        "account_type",
        "account_status",
        "account",
        "positions",
        "orders",
        "trades",
        "query_status",
        "runtime",
        "source_field_provenance",
        "safety",
        "failures",
    }
)
_ACCOUNT_KEYS = frozenset(
    {
        "redacted_account_id",
        "account_type",
        "enabled",
        "login_state",
        "trading_date",
        "total_assets",
        "available_cash",
        "withdrawable_cash",
        "frozen_cash",
        "frozen_commission",
        "stock_market_value",
        "fund_market_value",
        "bond_market_value",
        "total_instrument_value",
        "position_profit",
        "entrust_asset",
        "assure_asset",
        "provider_status",
        "provider_metadata",
    }
)
_POSITION_KEYS = frozenset(
    {
        "symbol",
        "instrument_name",
        "total_quantity",
        "available_quantity",
        "frozen_quantity",
        "on_road_quantity",
        "yesterday_quantity",
        "average_cost",
        "open_cost",
        "latest_price",
        "market_value",
        "floating_profit",
        "profit_ratio",
        "trading_day",
        "provider_metadata",
    }
)
_ORDER_KEYS = frozenset(
    {
        "broker_order_reference",
        "system_order_id",
        "symbol",
        "side",
        "operation_label",
        "order_price_type",
        "limit_price",
        "original_quantity",
        "filled_quantity",
        "remaining_quantity",
        "cancelled_quantity",
        "average_traded_price",
        "order_status",
        "submission_status",
        "error_id",
        "error_message",
        "cancel_information",
        "insert_date",
        "insert_time",
        "trade_amount",
        "investment_remark",
        "provider_metadata",
    }
)
_TRADE_KEYS = frozenset(
    {
        "trade_id",
        "order_reference",
        "system_order_id",
        "symbol",
        "side",
        "operation_label",
        "fill_price",
        "fill_quantity",
        "fill_amount",
        "commission",
        "trade_date",
        "trade_time",
        "investment_remark",
        "provider_metadata",
    }
)
_RUNTIME_KEYS = frozenset(
    {
        "python_version",
        "python_implementation",
        "qmt_runtime",
        "qmt_version",
        "platform",
        "metadata",
    }
)
_SAFETY_KEYS = frozenset(
    {
        "order_submission_enabled",
        "cancel_enabled",
        "passorder_invoked",
        "cancel_invoked",
    }
)
_FAILURE_KEYS = frozenset({"section", "code", "message", "exception_type"})
_QUERY_STATUS_KEYS = frozenset({"ok", "error"})


class SequenceTracker:
    """Thread-safe in-memory enforcement of strictly increasing snapshots."""

    def __init__(self, last_sequence: int | None = None, last_snapshot_id: str | None = None) -> None:
        if last_sequence is not None and (isinstance(last_sequence, bool) or not isinstance(last_sequence, int) or last_sequence <= 0):
            raise ValueError("last_sequence must be a positive integer")
        if last_sequence is None and last_snapshot_id is not None:
            raise ValueError("last_snapshot_id requires last_sequence")
        expected_id = f"qmt-{last_sequence}" if last_sequence is not None else None
        if last_snapshot_id is not None and last_snapshot_id != expected_id:
            raise ValueError("last_snapshot_id does not match last_sequence")
        self._last_sequence = last_sequence
        self._last_snapshot_id = last_snapshot_id or expected_id
        self._lock = threading.Lock()

    @property
    def last_sequence(self) -> int | None:
        with self._lock:
            return self._last_sequence

    @property
    def last_snapshot_id(self) -> str | None:
        with self._lock:
            return self._last_snapshot_id

    def observe(self, sequence: int, snapshot_id: str) -> None:
        """Record a validated snapshot or raise on duplicate/regressing input."""

        if isinstance(sequence, bool) or not isinstance(sequence, int) or sequence <= 0:
            raise ValueError("sequence must be a positive integer")
        if snapshot_id != f"qmt-{sequence}":
            raise ValueError("snapshot_id does not match sequence")
        with self._lock:
            previous = self._last_sequence
            if previous is not None and sequence == previous:
                raise DuplicateSequenceError("completed snapshot sequence is a duplicate")
            if previous is not None and sequence < previous:
                raise RegressingSequenceError("completed snapshot sequence regressed")
            self._last_sequence = sequence
            self._last_snapshot_id = snapshot_id


class QmtBuiltinBridgeReader:
    """Read and validate the latest atomically completed bridge heartbeat."""

    def __init__(
        self,
        bridge_root: str | Path,
        *,
        max_snapshot_age_seconds: float,
        expected_account_type: str | None = None,
        expected_redacted_account_id: str | None = None,
        sequence_tracker: SequenceTracker | None = None,
    ) -> None:
        if isinstance(max_snapshot_age_seconds, bool) or not isinstance(max_snapshot_age_seconds, (int, float)):
            raise ValueError("max_snapshot_age_seconds must be a positive finite number")
        max_age = float(max_snapshot_age_seconds)
        if not math.isfinite(max_age) or max_age <= 0:
            raise ValueError("max_snapshot_age_seconds must be a positive finite number")
        if expected_account_type is not None and (
            not isinstance(expected_account_type, str) or not expected_account_type.strip()
        ):
            raise ValueError("expected_account_type must be a non-empty string")
        if expected_redacted_account_id is not None and not is_redacted_account_identity(
            expected_redacted_account_id
        ):
            raise ValueError("expected account binding is not a valid redacted identity")

        self.bridge_root = Path(bridge_root).expanduser()
        self.max_snapshot_age_seconds = max_age
        self.expected_account_type = expected_account_type
        self.expected_redacted_account_id = expected_redacted_account_id
        self.sequence_tracker = sequence_tracker

    @property
    def snapshot_path(self) -> Path:
        return self.bridge_root / LATEST_SNAPSHOT_RELATIVE_PATH

    @property
    def temporary_path(self) -> Path:
        return self.bridge_root / TEMP_SNAPSHOT_RELATIVE_PATH

    def read_latest(self, *, now: datetime | None = None) -> QmtBridgeSnapshot:
        """Read only the completed file; an adjacent temporary file is ignored."""

        path = self.snapshot_path
        if not path.is_file():
            if self.temporary_path.is_file():
                raise IncompleteAtomicWriteError(
                    "temporary snapshot exists without a completed snapshot",
                    path=self.temporary_path,
                )
            raise MissingSnapshotError("completed QMT bridge snapshot is missing", path=path)

        try:
            size = path.stat().st_size
        except OSError as exc:
            raise MissingSnapshotError("completed QMT bridge snapshot is unavailable", path=path) from exc
        if size <= 0 or size > MAX_SNAPSHOT_BYTES:
            raise InvalidSnapshotValueError("completed snapshot size is outside protocol bounds", path=path)

        try:
            raw_text = path.read_text(encoding="utf-8")
        except UnicodeError as exc:
            raise MalformedSnapshotError("completed snapshot is not valid UTF-8 JSON", path=path) from exc
        except OSError as exc:
            raise MissingSnapshotError("completed QMT bridge snapshot is unavailable", path=path) from exc
        if len(raw_text.encode("utf-8")) > MAX_SNAPSHOT_BYTES:
            raise InvalidSnapshotValueError(
                "completed snapshot size is outside protocol bounds", path=path
            )

        try:
            payload = json.loads(raw_text, object_pairs_hook=_object_without_duplicate_keys)
        except (json.JSONDecodeError, RecursionError, ValueError) as exc:
            raise MalformedSnapshotError("completed snapshot contains malformed JSON", path=path) from exc

        return snapshot_from_mapping(
            payload,
            now=now,
            max_snapshot_age_seconds=self.max_snapshot_age_seconds,
            expected_account_type=self.expected_account_type,
            expected_redacted_account_id=self.expected_redacted_account_id,
            sequence_tracker=self.sequence_tracker,
            source_path=path,
        )


def snapshot_from_mapping(
    payload: object,
    *,
    max_snapshot_age_seconds: float,
    now: datetime | None = None,
    expected_account_type: str | None = None,
    expected_redacted_account_id: str | None = None,
    sequence_tracker: SequenceTracker | None = None,
    source_path: str | Path | None = None,
) -> QmtBridgeSnapshot:
    """Validate a decoded v1 payload and return deeply stable canonical records."""

    if isinstance(max_snapshot_age_seconds, bool) or not isinstance(
        max_snapshot_age_seconds, (int, float)
    ):
        raise ValueError("max_snapshot_age_seconds must be a positive finite number")
    max_age = float(max_snapshot_age_seconds)
    if not math.isfinite(max_age) or max_age <= 0:
        raise ValueError("max_snapshot_age_seconds must be a positive finite number")

    root = _exact_object(payload, _ROOT_KEYS, "root")

    schema_version = _strict_int(root["schema_version"], "schema_version")
    if schema_version != SCHEMA_VERSION:
        raise UnsupportedSchemaError("snapshot schema version is unsupported", path=source_path)
    bridge_version = _required_string(root["bridge_version"], "bridge_version")
    if bridge_version != BRIDGE_VERSION:
        raise UnsupportedSchemaError("snapshot bridge version is unsupported", path=source_path)
    provider = _required_string(root["provider"], "provider")
    if provider != PROVIDER_ID:
        _invalid("snapshot provider is not qmt_builtin_bridge", source_path)
    environment = _required_string(root["environment"], "environment")
    if environment != ENVIRONMENT_ID:
        _invalid("snapshot environment is not simulation_signal", source_path)

    generated_at = _utc_timestamp(root["generated_at"], "generated_at", source_path)
    current_time = now or datetime.now(timezone.utc)
    if current_time.tzinfo is None or current_time.utcoffset() is None:
        raise ValueError("now must be timezone-aware")
    current_time = current_time.astimezone(timezone.utc)
    age_seconds = (current_time - generated_at).total_seconds()
    if age_seconds < -MAX_FUTURE_SKEW_SECONDS:
        _invalid("snapshot timestamp is unreasonably far in the future", source_path)
    if age_seconds > max_age:
        raise StaleSnapshotError("completed QMT bridge heartbeat is stale", path=source_path)

    sequence = _strict_int(root["sequence"], "sequence")
    if sequence <= 0:
        _invalid("sequence must be a positive integer", source_path)
    snapshot_id = _required_string(root["snapshot_id"], "snapshot_id")
    if snapshot_id != f"qmt-{sequence}":
        _invalid("snapshot_id does not match sequence", source_path)

    redacted_account_id = _required_string(root["redacted_account_id"], "redacted_account_id")
    if not is_redacted_account_identity(redacted_account_id):
        _invalid("redacted_account_id does not use the v1 binding format", source_path)
    account_type = _required_string(root["account_type"], "account_type", maximum=64)
    account_status = _optional_string(root["account_status"], "account_status")
    qmt_trading_date = _optional_trading_date(root["qmt_trading_date"], "qmt_trading_date", source_path)

    if expected_account_type is not None and account_type != expected_account_type:
        _invalid("account_type does not match the configured expectation", source_path)
    if expected_redacted_account_id is not None:
        if not is_redacted_account_identity(expected_redacted_account_id):
            _invalid("configured account binding is not a redacted v1 identity", source_path)
        if not hmac.compare_digest(redacted_account_id, expected_redacted_account_id):
            raise AccountIdentityMismatchError(
                "snapshot account identity does not match the configured redacted binding",
                path=source_path,
            )

    query_status = _query_status_bundle(root["query_status"], source_path)
    failures = _failures(root["failures"], query_status, source_path)
    account = _account(root["account"], query_status.account, source_path)
    positions = _positions(root["positions"], query_status.positions, source_path)
    orders = _orders(root["orders"], query_status.orders, source_path)
    trades = _trades(root["trades"], query_status.trades, source_path)
    runtime = _runtime(root["runtime"], source_path)
    provenance = _source_field_provenance(root["source_field_provenance"], source_path)
    safety = _safety(root["safety"], source_path)

    if account is not None:
        if account.redacted_account_id != redacted_account_id:
            _invalid("root and account redacted identities differ", source_path)
        if account.account_type != account_type:
            _invalid("root and account account types differ", source_path)
        if account.provider_status != account_status:
            _invalid("root and account statuses differ", source_path)
        if account.trading_date != qmt_trading_date:
            _invalid("root and account trading dates differ", source_path)
    elif account_status is not None or qmt_trading_date is not None:
        _invalid("a missing account record requires null root account state", source_path)

    snapshot = QmtBridgeSnapshot(
        schema_version=schema_version,
        bridge_version=bridge_version,
        generated_at=generated_at,
        sequence=sequence,
        snapshot_id=snapshot_id,
        qmt_trading_date=qmt_trading_date,
        provider=provider,
        environment=environment,
        redacted_account_id=redacted_account_id,
        account_type=account_type,
        account_status=account_status,
        account=account,
        positions=positions,
        orders=orders,
        trades=trades,
        query_status=query_status,
        runtime=runtime,
        source_field_provenance=provenance,
        safety=safety,
        failures=failures,
        source_path=Path(source_path) if source_path is not None else None,
    )
    if sequence_tracker is not None:
        sequence_tracker.observe(sequence, snapshot_id)
    return snapshot


def _object_without_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON object key")
        result[key] = value
    return result


def _exact_object(value: object, keys: frozenset[str], field: str) -> Mapping[str, Any]:
    if not isinstance(value, dict):
        _invalid(f"{field} must be a JSON object")
    if frozenset(value) != keys:
        _invalid(f"{field} does not match the v1 protocol fields")
    return value


def _array(value: object, field: str, maximum: int) -> list[Any]:
    if not isinstance(value, list):
        _invalid(f"{field} must be a JSON array")
    if len(value) > maximum:
        _invalid(f"{field} exceeds the v1 collection bound")
    return value


def _required_string(value: object, field: str, *, maximum: int = MAX_TEXT_LENGTH) -> str:
    if not isinstance(value, str) or not value.strip() or len(value) > maximum or "\x00" in value:
        _invalid(f"{field} must be a bounded non-empty string")
    return value


def _optional_string(value: object, field: str, *, maximum: int = MAX_TEXT_LENGTH) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str) or len(value) > maximum or "\x00" in value:
        _invalid(f"{field} must be null or a bounded string")
    return value


def _strict_int(value: object, field: str, *, nonnegative: bool = False) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        _invalid(f"{field} must be an integer")
    if nonnegative and value < 0:
        _invalid(f"{field} must be non-negative")
    return value


def _optional_quantity(value: object, field: str) -> int | None:
    if value is None:
        return None
    return _strict_int(value, field, nonnegative=True)


def _optional_number(value: object, field: str, *, nonnegative: bool = False) -> float | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        _invalid(f"{field} must be null or numeric")
    try:
        converted = float(value)
    except OverflowError:
        _invalid(f"{field} must be finite")
    if not math.isfinite(converted):
        _invalid(f"{field} must be finite")
    if nonnegative and converted < 0:
        _invalid(f"{field} must be non-negative")
    return converted


def _optional_code(value: object, field: str) -> str | int | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (str, int)):
        _invalid(f"{field} must be null, a string, or an integer")
    if isinstance(value, str) and (len(value) > MAX_TEXT_LENGTH or "\x00" in value):
        _invalid(f"{field} is outside string bounds")
    return value


def _utc_timestamp(value: object, field: str, source_path: str | Path | None) -> datetime:
    text = _required_string(value, field, maximum=64)
    if _UTC_TIMESTAMP_PATTERN.fullmatch(text) is None:
        _invalid(f"{field} must be a UTC timestamp ending in Z", source_path)
    try:
        parsed = datetime.fromisoformat(text[:-1] + "+00:00")
    except ValueError as exc:
        raise InvalidSnapshotValueError(f"{field} is not a valid timestamp", path=source_path) from exc
    if parsed.utcoffset() != timezone.utc.utcoffset(parsed):
        _invalid(f"{field} must be UTC", source_path)
    return parsed


def _optional_trading_date(
    value: object,
    field: str,
    source_path: str | Path | None,
) -> str | None:
    text = _optional_string(value, field, maximum=10)
    if text is None:
        return None
    if _TRADING_DATE_PATTERN.fullmatch(text) is None:
        _invalid(f"{field} must use YYYYMMDD or YYYY-MM-DD", source_path)
    compact = text.replace("-", "")
    try:
        datetime.strptime(compact, "%Y%m%d")
    except ValueError as exc:
        raise InvalidSnapshotValueError(f"{field} is not a valid calendar date", path=source_path) from exc
    return text


def _primitive_metadata(
    value: object,
    field: str,
    source_path: str | Path | None,
) -> Mapping[str, str | int | float | bool | None]:
    if not isinstance(value, dict):
        _invalid(f"{field} must be a JSON object", source_path)
    if len(value) > MAX_METADATA_ENTRIES:
        _invalid(f"{field} exceeds the metadata entry bound", source_path)
    result: dict[str, str | int | float | bool | None] = {}
    for key, item in value.items():
        if (
            not isinstance(key, str)
            or not key
            or len(key) > MAX_METADATA_KEY_LENGTH
            or is_sensitive_field_name(key)
        ):
            _invalid(f"{field} contains a prohibited metadata key", source_path)
        if item is None or isinstance(item, (bool, int)):
            result[key] = item
        elif isinstance(item, float):
            if not math.isfinite(item):
                _invalid(f"{field} contains a non-finite number", source_path)
            result[key] = item
        elif isinstance(item, str):
            if len(item) > MAX_METADATA_TEXT_LENGTH or "\x00" in item:
                _invalid(f"{field} contains an over-bound string", source_path)
            result[key] = item
        else:
            _invalid(f"{field} may contain only primitive values", source_path)
    return MappingProxyType(result)


def _query_status_bundle(value: object, source_path: str | Path | None) -> QueryStatusBundle:
    status_map = _exact_object(value, frozenset(QUERY_SECTIONS), "query_status")
    statuses: dict[str, QueryStatus] = {}
    for section in QUERY_SECTIONS:
        item = _exact_object(status_map[section], _QUERY_STATUS_KEYS, f"query_status.{section}")
        ok = item["ok"]
        if not isinstance(ok, bool):
            _invalid(f"query_status.{section}.ok must be a boolean", source_path)
        error = _optional_string(
            item["error"],
            f"query_status.{section}.error",
            maximum=MAX_ERROR_MESSAGE_LENGTH,
        )
        if ok and error is not None:
            _invalid(f"query_status.{section} cannot report an error when successful", source_path)
        if not ok and (error is None or not error.strip()):
            _invalid(f"query_status.{section} requires a bounded error when failed", source_path)
        if error is not None and error not in _ALLOWED_QUERY_FAILURE_CODES:
            _invalid(f"query_status.{section} uses an unsupported failure code", source_path)
        if error == "qmt_query_empty" and section != "account":
            _invalid("qmt_query_empty is valid only for the account section", source_path)
        statuses[section] = QueryStatus(ok=ok, error=error)
    return QueryStatusBundle(**statuses)


def _failures(
    value: object,
    query_status: QueryStatusBundle,
    source_path: str | Path | None,
) -> tuple[FailureInfo, ...]:
    items = _array(value, "failures", MAX_FAILURES)
    failures: list[FailureInfo] = []
    seen: set[str] = set()
    for raw in items:
        item = _exact_object(raw, _FAILURE_KEYS, "failure")
        section = _required_string(item["section"], "failure.section", maximum=32)
        if section not in QUERY_SECTIONS or section in seen:
            _invalid("failures must contain at most one entry per query section", source_path)
        code = _required_string(item["code"], "failure.code", maximum=64)
        message = _required_string(
            item["message"], "failure.message", maximum=MAX_ERROR_MESSAGE_LENGTH
        )
        exception_type = _optional_string(
            item["exception_type"], "failure.exception_type", maximum=128
        )
        if query_status.for_section(section).ok:
            _invalid("successful query sections cannot appear in failures", source_path)
        if code != query_status.for_section(section).error:
            _invalid("failure code must match its query status error", source_path)
        expected_message = (
            "QMT read-only account query returned no records"
            if code == "qmt_query_empty"
            else f"QMT read-only {section} query failed"
        )
        if message != expected_message:
            _invalid("failure message does not match the safe v1 protocol phrase", source_path)
        if code == "qmt_query_empty":
            if exception_type is not None:
                _invalid("empty-query failures cannot include an exception type", source_path)
        elif exception_type is None or _EXCEPTION_TYPE_PATTERN.fullmatch(exception_type) is None:
            _invalid("query failure exception_type must be a bounded class name", source_path)
        seen.add(section)
        failures.append(FailureInfo(section, code, message, exception_type))
    failed_sections = {
        section for section in QUERY_SECTIONS if not query_status.for_section(section).ok
    }
    if seen != failed_sections:
        _invalid("failures must correspond exactly to failed query sections", source_path)
    return tuple(failures)


def _account(
    value: object,
    status: QueryStatus,
    source_path: str | Path | None,
) -> AccountRecord | None:
    if value is None:
        if status.ok:
            _invalid("a successful account query requires an account record", source_path)
        return None
    if not status.ok:
        _invalid("a failed account query cannot include an account record", source_path)
    item = _exact_object(value, _ACCOUNT_KEYS, "account")
    redacted_id = _required_string(item["redacted_account_id"], "account.redacted_account_id")
    if not is_redacted_account_identity(redacted_id):
        _invalid("account redacted identity does not use the v1 binding format", source_path)
    enabled = item["enabled"]
    if enabled is not None and not isinstance(enabled, bool):
        _invalid("account.enabled must be null or a boolean", source_path)
    return AccountRecord(
        redacted_account_id=redacted_id,
        account_type=_required_string(item["account_type"], "account.account_type", maximum=64),
        enabled=enabled,
        login_state=_optional_string(item["login_state"], "account.login_state"),
        trading_date=_optional_trading_date(
            item["trading_date"], "account.trading_date", source_path
        ),
        total_assets=_optional_number(item["total_assets"], "account.total_assets"),
        available_cash=_optional_number(item["available_cash"], "account.available_cash"),
        withdrawable_cash=_optional_number(
            item["withdrawable_cash"], "account.withdrawable_cash"
        ),
        frozen_cash=_optional_number(item["frozen_cash"], "account.frozen_cash"),
        frozen_commission=_optional_number(
            item["frozen_commission"], "account.frozen_commission"
        ),
        stock_market_value=_optional_number(
            item["stock_market_value"], "account.stock_market_value"
        ),
        fund_market_value=_optional_number(
            item["fund_market_value"], "account.fund_market_value"
        ),
        bond_market_value=_optional_number(
            item["bond_market_value"], "account.bond_market_value"
        ),
        total_instrument_value=_optional_number(
            item["total_instrument_value"], "account.total_instrument_value"
        ),
        position_profit=_optional_number(item["position_profit"], "account.position_profit"),
        entrust_asset=_optional_number(item["entrust_asset"], "account.entrust_asset"),
        assure_asset=_optional_number(item["assure_asset"], "account.assure_asset"),
        provider_status=_optional_string(item["provider_status"], "account.provider_status"),
        provider_metadata=_primitive_metadata(
            item["provider_metadata"], "account.provider_metadata", source_path
        ),
    )


def _positions(
    value: object,
    status: QueryStatus,
    source_path: str | Path | None,
) -> tuple[PositionRecord, ...]:
    items = _array(value, "positions", MAX_POSITIONS)
    if not status.ok and items:
        _invalid("a failed positions query cannot include records", source_path)
    result: list[PositionRecord] = []
    for raw in items:
        item = _exact_object(raw, _POSITION_KEYS, "position")
        result.append(
            PositionRecord(
                symbol=_optional_string(item["symbol"], "position.symbol"),
                instrument_name=_optional_string(
                    item["instrument_name"], "position.instrument_name"
                ),
                total_quantity=_optional_quantity(
                    item["total_quantity"], "position.total_quantity"
                ),
                available_quantity=_optional_quantity(
                    item["available_quantity"], "position.available_quantity"
                ),
                frozen_quantity=_optional_quantity(
                    item["frozen_quantity"], "position.frozen_quantity"
                ),
                on_road_quantity=_optional_quantity(
                    item["on_road_quantity"], "position.on_road_quantity"
                ),
                yesterday_quantity=_optional_quantity(
                    item["yesterday_quantity"], "position.yesterday_quantity"
                ),
                average_cost=_optional_number(
                    item["average_cost"], "position.average_cost", nonnegative=True
                ),
                open_cost=_optional_number(
                    item["open_cost"], "position.open_cost", nonnegative=True
                ),
                latest_price=_optional_number(
                    item["latest_price"], "position.latest_price", nonnegative=True
                ),
                market_value=_optional_number(
                    item["market_value"], "position.market_value", nonnegative=True
                ),
                floating_profit=_optional_number(
                    item["floating_profit"], "position.floating_profit"
                ),
                profit_ratio=_optional_number(item["profit_ratio"], "position.profit_ratio"),
                trading_day=_optional_trading_date(
                    item["trading_day"], "position.trading_day", source_path
                ),
                provider_metadata=_primitive_metadata(
                    item["provider_metadata"], "position.provider_metadata", source_path
                ),
            )
        )
    return tuple(result)


def _orders(
    value: object,
    status: QueryStatus,
    source_path: str | Path | None,
) -> tuple[OrderRecord, ...]:
    items = _array(value, "orders", MAX_ORDERS)
    if not status.ok and items:
        _invalid("a failed orders query cannot include records", source_path)
    result: list[OrderRecord] = []
    for raw in items:
        item = _exact_object(raw, _ORDER_KEYS, "order")
        result.append(
            OrderRecord(
                broker_order_reference=_optional_string(
                    item["broker_order_reference"], "order.broker_order_reference"
                ),
                system_order_id=_optional_string(
                    item["system_order_id"], "order.system_order_id"
                ),
                symbol=_optional_string(item["symbol"], "order.symbol"),
                side=_optional_string(item["side"], "order.side"),
                operation_label=_optional_string(
                    item["operation_label"], "order.operation_label"
                ),
                order_price_type=_optional_code(
                    item["order_price_type"], "order.order_price_type"
                ),
                limit_price=_optional_number(
                    item["limit_price"], "order.limit_price", nonnegative=True
                ),
                original_quantity=_optional_quantity(
                    item["original_quantity"], "order.original_quantity"
                ),
                filled_quantity=_optional_quantity(
                    item["filled_quantity"], "order.filled_quantity"
                ),
                remaining_quantity=_optional_quantity(
                    item["remaining_quantity"], "order.remaining_quantity"
                ),
                cancelled_quantity=_optional_quantity(
                    item["cancelled_quantity"], "order.cancelled_quantity"
                ),
                average_traded_price=_optional_number(
                    item["average_traded_price"],
                    "order.average_traded_price",
                    nonnegative=True,
                ),
                order_status=_optional_code(item["order_status"], "order.order_status"),
                submission_status=_optional_code(
                    item["submission_status"], "order.submission_status"
                ),
                error_id=_optional_code(item["error_id"], "order.error_id"),
                error_message=_optional_string(item["error_message"], "order.error_message"),
                cancel_information=_optional_string(
                    item["cancel_information"], "order.cancel_information"
                ),
                insert_date=_optional_string(item["insert_date"], "order.insert_date"),
                insert_time=_optional_string(item["insert_time"], "order.insert_time"),
                trade_amount=_optional_number(
                    item["trade_amount"], "order.trade_amount", nonnegative=True
                ),
                investment_remark=_optional_string(
                    item["investment_remark"], "order.investment_remark"
                ),
                provider_metadata=_primitive_metadata(
                    item["provider_metadata"], "order.provider_metadata", source_path
                ),
            )
        )
    return tuple(result)


def _trades(
    value: object,
    status: QueryStatus,
    source_path: str | Path | None,
) -> tuple[TradeRecord, ...]:
    items = _array(value, "trades", MAX_TRADES)
    if not status.ok and items:
        _invalid("a failed trades query cannot include records", source_path)
    result: list[TradeRecord] = []
    for raw in items:
        item = _exact_object(raw, _TRADE_KEYS, "trade")
        result.append(
            TradeRecord(
                trade_id=_optional_string(item["trade_id"], "trade.trade_id"),
                order_reference=_optional_string(
                    item["order_reference"], "trade.order_reference"
                ),
                system_order_id=_optional_string(
                    item["system_order_id"], "trade.system_order_id"
                ),
                symbol=_optional_string(item["symbol"], "trade.symbol"),
                side=_optional_string(item["side"], "trade.side"),
                operation_label=_optional_string(
                    item["operation_label"], "trade.operation_label"
                ),
                fill_price=_optional_number(
                    item["fill_price"], "trade.fill_price", nonnegative=True
                ),
                fill_quantity=_optional_quantity(
                    item["fill_quantity"], "trade.fill_quantity"
                ),
                fill_amount=_optional_number(
                    item["fill_amount"], "trade.fill_amount", nonnegative=True
                ),
                commission=_optional_number(
                    item["commission"], "trade.commission", nonnegative=True
                ),
                trade_date=_optional_string(item["trade_date"], "trade.trade_date"),
                trade_time=_optional_string(item["trade_time"], "trade.trade_time"),
                investment_remark=_optional_string(
                    item["investment_remark"], "trade.investment_remark"
                ),
                provider_metadata=_primitive_metadata(
                    item["provider_metadata"], "trade.provider_metadata", source_path
                ),
            )
        )
    return tuple(result)


def _runtime(value: object, source_path: str | Path | None) -> RuntimeMetadata:
    item = _exact_object(value, _RUNTIME_KEYS, "runtime")
    qmt_runtime = _required_string(item["qmt_runtime"], "runtime.qmt_runtime", maximum=128)
    if qmt_runtime != "builtin_python":
        _invalid("runtime.qmt_runtime must identify QMT built-in Python", source_path)
    return RuntimeMetadata(
        python_version=_required_string(
            item["python_version"], "runtime.python_version", maximum=64
        ),
        python_implementation=_optional_string(
            item["python_implementation"], "runtime.python_implementation", maximum=64
        ),
        qmt_runtime=qmt_runtime,
        qmt_version=_optional_string(
            item["qmt_version"], "runtime.qmt_version", maximum=128
        ),
        platform=_optional_string(item["platform"], "runtime.platform", maximum=128),
        metadata=_primitive_metadata(item["metadata"], "runtime.metadata", source_path),
    )


def _source_field_provenance(
    value: object,
    source_path: str | Path | None,
) -> Mapping[str, Mapping[str, tuple[str, ...]]]:
    sections = _exact_object(value, frozenset(QUERY_SECTIONS), "source_field_provenance")
    result: dict[str, Mapping[str, tuple[str, ...]]] = {}
    for section in QUERY_SECTIONS:
        fields = sections[section]
        if not isinstance(fields, dict):
            _invalid(f"source_field_provenance.{section} must be an object", source_path)
        if len(fields) > MAX_PROVENANCE_FIELDS:
            _invalid(f"source_field_provenance.{section} exceeds its field bound", source_path)
        converted: dict[str, tuple[str, ...]] = {}
        for canonical_name, sources in fields.items():
            if (
                not isinstance(canonical_name, str)
                or not canonical_name
                or len(canonical_name) > MAX_METADATA_KEY_LENGTH
                or is_sensitive_field_name(canonical_name)
            ):
                _invalid("source provenance contains a prohibited canonical field", source_path)
            if (
                not isinstance(sources, list)
                or not sources
                or len(sources) > MAX_PROVENANCE_SOURCES
            ):
                _invalid("source provenance aliases must be a bounded array", source_path)
            converted_sources: list[str] = []
            for source in sources:
                source_name = _required_string(
                    source, "source provenance alias", maximum=MAX_METADATA_KEY_LENGTH
                )
                if is_sensitive_field_name(source_name):
                    _invalid("source provenance contains a prohibited provider field", source_path)
                converted_sources.append(source_name)
            converted[canonical_name] = tuple(converted_sources)
        result[section] = MappingProxyType(converted)
    return MappingProxyType(result)


def _safety(value: object, source_path: str | Path | None) -> ReadOnlySafetyState:
    item = _exact_object(value, _SAFETY_KEYS, "safety")
    for field in _SAFETY_KEYS:
        if item[field] is not False:
            _invalid("all QMT bridge mutation safety flags must be false", source_path)
    return ReadOnlySafetyState()


def _invalid(message: str, path: str | Path | None = None) -> NoReturn:
    raise InvalidSnapshotValueError(message, path=path)
