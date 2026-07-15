#coding:gbk
"""QMT built-in Python 3.6 broker-simulation single-intent executor.

Copy this ASCII-only source into the dedicated QMT strategy editor.  The
account and accountType globals are injected by QMT.  This strategy processes
at most one authenticated limit-order intent during one model run.  It relies
on later QMT order/deal readback for acknowledgement; passorder itself is not
treated as broker acceptance.
"""

import datetime
import errno
import hashlib
import hmac
import json
import math
import os
import re
import stat


SCHEMA_VERSION = 1
PROTOCOL_VERSION = "qmt_simulation_order_loop_v1"
ENVIRONMENT = "broker_simulation"
ACCOUNT_TYPE = "STOCK"
ORDER_KIND = "shares_limit"
STRATEGY_NAME = "quantpilot_sim_v1"
DEFAULT_BRIDGE_ROOT = r"D:\QuantPilotQMTBridge"
BRIDGE_ROOT = os.environ.get("QUANTPILOT_QMT_BRIDGE_ROOT", DEFAULT_BRIDGE_ROOT)

ACCOUNT_BINDING_KEY_FILENAME = "account_binding_key_v1.hex"
ACCOUNT_BINDING_HMAC_DOMAIN = b"quantpilot:qmt-account-binding:v1\x00"
INTENT_HMAC_DOMAIN = b"quantpilot:qmt-simulation-order-intent:v1\x00"
ACCEPTANCE_LIMITATION = "qmt_live_trading_mode_with_broker_simulation_account_only"

MAX_INTENT_BYTES = 16 * 1024
MAX_STATE_BYTES = 16 * 1024
MAX_RESULT_BYTES = 64 * 1024
MAX_SNAPSHOT_BYTES = 8 * 1024 * 1024
MAX_BROKER_RECORDS = 10000
MAX_IDENTIFIER_LENGTH = 128
MAX_STATUS_LENGTH = 128
MAX_FAILURE_CODE_LENGTH = 80
MAX_RUN_LABEL_LENGTH = 128
MAX_QUANTITY = 2147483647
MAX_LIMIT_PRICE = 1000000000.0
MAX_FUTURE_SKEW_SECONDS = 300
MAX_INTENT_LIFETIME_SECONDS = 86400

INTENT_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$")
SYMBOL_RE = re.compile(r"^[0-9]{6}\.(SH|SZ|BJ)$")
HEX_64_RE = re.compile(r"^[0-9a-f]{64}$")
ACCOUNT_TOKEN_RE = re.compile(r"^qmtacct-v1-[0-9a-f]{24}$")
UTC_TIMESTAMP_RE = re.compile(
    r"^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z$"
)

BASE_INTENT_KEYS = frozenset(
    (
        "schema_version",
        "protocol_version",
        "intent_id",
        "created_at",
        "expires_at",
        "environment",
        "expected_redacted_account_id",
        "account_type",
        "symbol",
        "side",
        "quantity",
        "order_kind",
        "limit_price",
        "source_order_digest",
        "explicit_submit",
        "intent_hmac",
    )
)
OPTIONAL_INTENT_KEYS = frozenset(("run_label",))
STATE_KEYS = frozenset(
    (
        "schema_version",
        "protocol_version",
        "intent_id",
        "updated_at",
        "status",
        "expected_redacted_account_id",
        "passorder_attempted",
        "failure_code",
    )
)
RESULT_KEYS = frozenset(
    (
        "schema_version",
        "protocol_version",
        "intent_id",
        "generated_at",
        "status",
        "expected_redacted_account_id",
        "symbol",
        "side",
        "requested_quantity",
        "limit_price",
        "strategy_name",
        "user_order_id",
        "passorder_attempted",
        "broker_order_reference",
        "system_order_id",
        "order_status",
        "submission_status",
        "filled_quantity",
        "average_fill_price",
        "deal_count",
        "failure_code",
        "failure_type",
        "latest_snapshot_sequence",
        "acceptance_limitation",
    )
)
STATUSES = frozenset(
    (
        "received",
        "claimed",
        "submission_attempted",
        "broker_acknowledged",
        "partially_filled",
        "filled",
        "rejected",
        "expired",
        "uncertain",
    )
)
TERMINAL_STATUSES = frozenset(("filled", "rejected", "expired"))
PRE_SUBMISSION_STATUSES = frozenset(("received", "claimed"))
READBACK_STATUSES = frozenset(
    ("broker_acknowledged", "partially_filled", "filled", "rejected")
)
SAFE_STATUS_TEXT = {
    "observed": "observed",
    "pending": "pending",
    "submitted": "pending",
    "accepted": "accepted",
    "acknowledged": "acknowledged",
    "reported": "acknowledged",
    "partially_filled": "partially_filled",
    "partial": "partially_filled",
    "filled": "filled",
    "succeeded": "filled",
    "rejected": "rejected",
    "reject": "rejected",
    "invalid": "rejected",
    "waste": "rejected",
    "cancelled": "cancelled",
    "canceled": "cancelled",
    "unknown": "unknown",
}


class _ExecutionState(object):
    def __init__(self):
        self.account_id = None
        self.account_type = None
        self.redacted_account_id = None
        self.binding_key = None
        self.bridge_root = None
        self.intent_id = None
        self.in_handlebar = False
        self.stopped = True
        self.lock_handle = None
        self.lock_fd = None
        self.lock_path = None


G = _ExecutionState()


class _SafeFailure(Exception):
    def __init__(self, code):
        Exception.__init__(self, code)
        self.code = code


def _utc_now_datetime():
    return datetime.datetime.now(datetime.timezone.utc).replace(microsecond=0)


def _utc_text(value=None):
    selected = value if value is not None else _utc_now_datetime()
    return selected.astimezone(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _parse_utc_text(value):
    if (
        not isinstance(value, str)
        or len(value) != 20
        or UTC_TIMESTAMP_RE.fullmatch(value) is None
    ):
        raise _SafeFailure("invalid_timestamp")
    try:
        parsed = datetime.datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ")
    except (TypeError, ValueError):
        raise _SafeFailure("invalid_timestamp")
    return parsed.replace(tzinfo=datetime.timezone.utc)


def _canonical_bytes(payload):
    try:
        text = json.dumps(
            payload,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
            allow_nan=False,
        )
    except (TypeError, ValueError, OverflowError):
        raise _SafeFailure("serialization_failed")
    return text.encode("utf-8")


def _file_bytes(payload):
    return _canonical_bytes(payload) + b"\n"


def _reject_duplicate_json_keys(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise _SafeFailure("duplicate_json_key")
        result[key] = value
    return result


def _reject_json_constant(value):
    del value
    raise _SafeFailure("invalid_json_number")


def _read_bounded_json(path, maximum_bytes, missing_ok=False):
    try:
        item_stat = os.lstat(path)
    except OSError as exc:
        if missing_ok and getattr(exc, "errno", None) == errno.ENOENT:
            return None, None
        raise _SafeFailure("file_read_failed")
    if not stat.S_ISREG(item_stat.st_mode) or item_stat.st_size < 2:
        raise _SafeFailure("invalid_file_type")
    if item_stat.st_size > maximum_bytes:
        raise _SafeFailure("file_too_large")
    try:
        with open(path, "rb") as handle:
            encoded = handle.read(maximum_bytes + 1)
    except Exception:
        raise _SafeFailure("file_read_failed")
    if len(encoded) > maximum_bytes or len(encoded) != item_stat.st_size:
        raise _SafeFailure("file_size_changed")
    try:
        payload = json.loads(
            encoded.decode("utf-8"),
            object_pairs_hook=_reject_duplicate_json_keys,
            parse_constant=_reject_json_constant,
        )
    except _SafeFailure:
        raise
    except Exception:
        raise _SafeFailure("invalid_json")
    if not isinstance(payload, dict):
        raise _SafeFailure("invalid_json_shape")
    return payload, encoded


def _atomic_write_document(path, payload, maximum_bytes):
    if G.bridge_root is not None:
        _require_path_beneath_root(path, G.bridge_root)
    encoded = _file_bytes(payload)
    if len(encoded) > maximum_bytes:
        raise _SafeFailure("serialized_file_too_large")
    temporary = path + ".tmp"
    try:
        try:
            temporary_stat = os.lstat(temporary)
        except OSError as exc:
            if getattr(exc, "errno", None) != errno.ENOENT:
                raise
        else:
            if not stat.S_ISREG(temporary_stat.st_mode):
                raise _SafeFailure("invalid_temporary_file")
            os.unlink(temporary)
        with open(temporary, "wb") as handle:
            handle.write(encoded)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    except _SafeFailure:
        raise
    except Exception:
        raise _SafeFailure("atomic_write_failed")


def _bridge_paths(root=None):
    selected = root if root is not None else BRIDGE_ROOT
    absolute_root = os.path.abspath(selected)
    execution = os.path.join(absolute_root, "execution")
    intents = os.path.join(execution, "intents")
    acknowledgements = os.path.join(execution, "acknowledgements")
    state = os.path.join(execution, "state")
    return {
        "root": absolute_root,
        "intents": intents,
        "acknowledgements": acknowledgements,
        "state": state,
        "binding_key": os.path.join(
            absolute_root, "state", ACCOUNT_BINDING_KEY_FILENAME
        ),
        "snapshot": os.path.join(
            absolute_root, "snapshots", "latest_snapshot_v1.json"
        ),
        "lock": os.path.join(state, "qmt_simulation_executor_v1.lock"),
    }


def _path_is_inside_git_repository(path):
    current = os.path.abspath(path)
    for unused in range(256):
        del unused
        if os.path.exists(os.path.join(current, ".git")):
            return True
        parent = os.path.dirname(current)
        if parent == current:
            return False
        current = parent
    raise _SafeFailure("bridge_root_depth_exceeded")


def _require_path_beneath_root(path, root):
    real_path = os.path.realpath(path)
    real_root = os.path.realpath(root)
    try:
        common = os.path.commonpath((real_path, real_root))
    except (TypeError, ValueError):
        raise _SafeFailure("protocol_path_escape")
    if common != real_root or _path_is_inside_git_repository(real_path):
        raise _SafeFailure("protocol_path_escape")
    return real_path


def _ensure_directories(paths):
    if _path_is_inside_git_repository(paths["root"]) or _path_is_inside_git_repository(
        os.path.realpath(paths["root"])
    ):
        raise _SafeFailure("repository_local_bridge_root")
    for directory in (
        paths["root"],
        os.path.dirname(paths["binding_key"]),
        os.path.dirname(paths["intents"]),
        paths["intents"],
        paths["acknowledgements"],
        paths["state"],
    ):
        if not os.path.isdir(directory):
            try:
                os.makedirs(directory)
            except OSError:
                if not os.path.isdir(directory):
                    raise _SafeFailure("directory_setup_failed")
    for directory in (
        paths["root"],
        os.path.dirname(paths["binding_key"]),
        paths["intents"],
        paths["acknowledgements"],
        paths["state"],
    ):
        _require_path_beneath_root(directory, paths["root"])


def _acquire_lock(paths):
    lock_path = paths["lock"]
    try:
        import msvcrt
    except ImportError:
        msvcrt = None
    if msvcrt is not None:
        handle = None
        try:
            handle = open(lock_path, "a+b")
            if handle.tell() == 0:
                handle.write(b"1")
                handle.flush()
            handle.seek(0)
            msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
        except Exception:
            try:
                handle.close()
            except Exception:
                pass
            return False
        G.lock_handle = handle
    else:
        handle = None
        try:
            import fcntl
            handle = open(lock_path, "a+b")
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            handle.seek(0)
            handle.truncate()
            handle.write(b"quantpilot-qmt-simulation-v1\n")
            handle.flush()
        except Exception:
            try:
                handle.close()
            except Exception:
                pass
            return False
        G.lock_handle = handle
    G.lock_path = lock_path
    return True


def _release_lock():
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
    G.lock_path = None


def _load_binding_key(path):
    try:
        key_stat = os.lstat(path)
        if not stat.S_ISREG(key_stat.st_mode) or key_stat.st_size != 64:
            raise _SafeFailure("invalid_binding_key")
        with open(path, "rb") as handle:
            encoded = handle.read(65)
        if len(encoded) != 64:
            raise _SafeFailure("invalid_binding_key")
        if any(value not in b"0123456789abcdef" for value in encoded):
            raise _SafeFailure("invalid_binding_key")
        decoded = bytes.fromhex(encoded.decode("ascii"))
    except _SafeFailure:
        raise
    except Exception:
        raise _SafeFailure("invalid_binding_key")
    if len(decoded) != 32:
        raise _SafeFailure("invalid_binding_key")
    return decoded


def _account_identity_bytes(account_id):
    if isinstance(account_id, bool) or not isinstance(account_id, (str, int)):
        raise _SafeFailure("invalid_injected_account")
    try:
        encoded = str(account_id).strip().encode("utf-8")
    except Exception:
        raise _SafeFailure("invalid_injected_account")
    if not encoded or len(encoded) > 512:
        raise _SafeFailure("invalid_injected_account")
    return encoded


def _redacted_account_id(account_id, binding_key):
    digest = hmac.new(
        binding_key,
        ACCOUNT_BINDING_HMAC_DOMAIN + _account_identity_bytes(account_id),
        hashlib.sha256,
    ).hexdigest()
    return "qmtacct-v1-" + digest[:24]


def _validate_text(value, maximum, code):
    if not isinstance(value, str) or not value or len(value) > maximum:
        raise _SafeFailure(code)
    if "\x00" in value or "\r" in value or "\n" in value:
        raise _SafeFailure(code)


def _validate_intent(payload, encoded, path, now):
    keys = frozenset(payload)
    if not BASE_INTENT_KEYS.issubset(keys):
        raise _SafeFailure("missing_intent_field")
    if not keys.issubset(BASE_INTENT_KEYS | OPTIONAL_INTENT_KEYS):
        raise _SafeFailure("unknown_intent_field")
    if payload.get("run_label") is None and "run_label" in payload:
        raise _SafeFailure("invalid_run_label")
    if encoded != _file_bytes(payload):
        raise _SafeFailure("noncanonical_intent")
    schema_version = payload.get("schema_version")
    if (
        isinstance(schema_version, bool)
        or not isinstance(schema_version, int)
        or schema_version != SCHEMA_VERSION
    ):
        raise _SafeFailure("unsupported_schema")
    if payload.get("protocol_version") != PROTOCOL_VERSION:
        raise _SafeFailure("unsupported_protocol")
    if payload.get("environment") != ENVIRONMENT:
        raise _SafeFailure("unsupported_environment")
    if payload.get("account_type") != ACCOUNT_TYPE:
        raise _SafeFailure("unsupported_account_type")
    if payload.get("order_kind") != ORDER_KIND:
        raise _SafeFailure("unsupported_order_kind")
    if payload.get("explicit_submit") is not True:
        raise _SafeFailure("explicit_submit_required")

    intent_id = payload.get("intent_id")
    if not isinstance(intent_id, str) or INTENT_ID_RE.fullmatch(intent_id) is None:
        raise _SafeFailure("invalid_intent_id")
    if os.path.basename(path) != intent_id + ".json":
        raise _SafeFailure("intent_filename_mismatch")
    symbol = payload.get("symbol")
    if not isinstance(symbol, str) or SYMBOL_RE.fullmatch(symbol) is None:
        raise _SafeFailure("invalid_symbol")
    side = payload.get("side")
    if side not in ("buy", "sell"):
        raise _SafeFailure("unsupported_side")
    quantity = payload.get("quantity")
    if (
        isinstance(quantity, bool)
        or not isinstance(quantity, int)
        or quantity < 1
        or quantity > MAX_QUANTITY
    ):
        raise _SafeFailure("invalid_quantity")
    if side == "buy" and quantity % 100 != 0:
        raise _SafeFailure("invalid_buy_lot")
    limit_price = payload.get("limit_price")
    if (
        isinstance(limit_price, bool)
        or not isinstance(limit_price, (int, float))
        or not math.isfinite(limit_price)
        or limit_price <= 0
        or limit_price > MAX_LIMIT_PRICE
    ):
        raise _SafeFailure("invalid_limit_price")
    source_digest = payload.get("source_order_digest")
    if not isinstance(source_digest, str) or HEX_64_RE.fullmatch(source_digest) is None:
        raise _SafeFailure("invalid_source_order_digest")
    account_token = payload.get("expected_redacted_account_id")
    if (
        not isinstance(account_token, str)
        or ACCOUNT_TOKEN_RE.fullmatch(account_token) is None
    ):
        raise _SafeFailure("invalid_account_binding")
    if not hmac.compare_digest(account_token, G.redacted_account_id):
        raise _SafeFailure("account_binding_mismatch")
    if "run_label" in payload:
        _validate_text(payload["run_label"], MAX_RUN_LABEL_LENGTH, "invalid_run_label")

    intent_hmac = payload.get("intent_hmac")
    if not isinstance(intent_hmac, str) or HEX_64_RE.fullmatch(intent_hmac) is None:
        raise _SafeFailure("invalid_intent_hmac")
    unsigned = dict(payload)
    del unsigned["intent_hmac"]
    expected_hmac = hmac.new(
        G.binding_key,
        INTENT_HMAC_DOMAIN + _canonical_bytes(unsigned),
        hashlib.sha256,
    ).hexdigest()
    if not hmac.compare_digest(intent_hmac, expected_hmac):
        raise _SafeFailure("invalid_intent_hmac")

    created_at = _parse_utc_text(payload.get("created_at"))
    expires_at = _parse_utc_text(payload.get("expires_at"))
    if expires_at <= created_at:
        raise _SafeFailure("invalid_expiry")
    lifetime = (expires_at - created_at).total_seconds()
    if lifetime > MAX_INTENT_LIFETIME_SECONDS:
        raise _SafeFailure("invalid_expiry")
    if created_at > now + datetime.timedelta(seconds=MAX_FUTURE_SKEW_SECONDS):
        raise _SafeFailure("future_skew")
    return expires_at <= now


def _intent_is_expired(intent):
    return _parse_utc_text(intent["expires_at"]) <= _utc_now_datetime()


def _select_intent_path(paths):
    if G.intent_id is not None:
        selected = os.path.join(paths["intents"], G.intent_id + ".json")
        try:
            _require_path_beneath_root(selected, paths["root"])
        except _SafeFailure:
            return None
        return selected
    try:
        names = os.listdir(paths["intents"])
    except Exception:
        return None
    candidates = []
    for name in names:
        if not name.endswith(".json"):
            continue
        intent_id = name[:-5]
        if INTENT_ID_RE.fullmatch(intent_id) is None:
            continue
        path = os.path.join(paths["intents"], name)
        try:
            _require_path_beneath_root(path, paths["root"])
            item_stat = os.lstat(path)
        except (OSError, _SafeFailure):
            continue
        if stat.S_ISREG(item_stat.st_mode):
            candidates.append(path)
    if len(candidates) != 1:
        return None
    return candidates[0]


def _state_path(paths, intent_id):
    return os.path.join(paths["state"], intent_id + ".json")


def _result_path(paths, intent_id):
    return os.path.join(paths["acknowledgements"], intent_id + ".json")


def _artifact_utc_text(intent, prior_path, prior_field, maximum_bytes):
    current = _utc_now_datetime()
    created = _parse_utc_text(intent["created_at"])
    selected = created if created > current else current
    try:
        payload, encoded = _read_bounded_json(
            prior_path, maximum_bytes, missing_ok=True
        )
        if payload is not None and encoded == _file_bytes(payload):
            schema_version = payload.get("schema_version")
            if (
                isinstance(schema_version, int)
                and not isinstance(schema_version, bool)
                and schema_version == SCHEMA_VERSION
                and payload.get("protocol_version") == PROTOCOL_VERSION
                and payload.get("intent_id") == intent["intent_id"]
                and payload.get("expected_redacted_account_id")
                == G.redacted_account_id
            ):
                prior = _parse_utc_text(payload.get(prior_field))
                if prior > selected:
                    selected = prior
    except _SafeFailure:
        pass
    return _utc_text(selected)


def _read_prior_result(paths, intent):
    try:
        payload, encoded = _read_bounded_json(
            _result_path(paths, intent["intent_id"]),
            MAX_RESULT_BYTES,
            missing_ok=True,
        )
        if payload is None:
            return None
        if frozenset(payload) != RESULT_KEYS or encoded != _file_bytes(payload):
            return None
        schema_version = payload.get("schema_version")
        if (
            isinstance(schema_version, bool)
            or not isinstance(schema_version, int)
            or schema_version != SCHEMA_VERSION
            or payload.get("protocol_version") != PROTOCOL_VERSION
        ):
            return None
        if payload.get("intent_id") != intent["intent_id"]:
            return None
        if payload.get("expected_redacted_account_id") != G.redacted_account_id:
            return None
        if payload.get("status") not in STATUSES:
            return None
        filled = payload.get("filled_quantity")
        if (
            isinstance(filled, bool)
            or not isinstance(filled, int)
            or filled < 0
            or filled > intent["quantity"]
        ):
            return None
        return payload
    except _SafeFailure:
        return None


def _readback_transition_allowed(local_state, prior_result, reconciliation):
    previous = local_state["status"]
    current = reconciliation["status"]
    if prior_result is not None:
        for field in ("broker_order_reference", "system_order_id"):
            prior_identity = prior_result.get(field)
            if (
                prior_identity is not None
                and reconciliation.get(field) != prior_identity
            ):
                return False
        prior_filled = prior_result.get("filled_quantity")
        prior_deals = prior_result.get("deal_count")
        if (
            isinstance(prior_filled, int)
            and reconciliation["filled_quantity"] < prior_filled
        ):
            return False
        if (
            isinstance(prior_deals, int)
            and reconciliation["deal_count"] < prior_deals
        ):
            return False
    if previous == "filled":
        return current == "filled"
    if previous == "rejected":
        return current == "rejected"
    if previous == "partially_filled":
        if current == "filled":
            return True
        if current != "partially_filled":
            return False
        if prior_result is None or prior_result.get("status") != "partially_filled":
            return True
        return reconciliation["filled_quantity"] >= prior_result["filled_quantity"]
    if previous == "broker_acknowledged":
        return current in READBACK_STATUSES
    return True


def _read_local_state(paths, intent):
    path = _state_path(paths, intent["intent_id"])
    payload, encoded = _read_bounded_json(path, MAX_STATE_BYTES, missing_ok=True)
    if payload is None:
        return None
    if frozenset(payload) != STATE_KEYS or encoded != _file_bytes(payload):
        raise _SafeFailure("invalid_local_state")
    schema_version = payload.get("schema_version")
    if (
        isinstance(schema_version, bool)
        or not isinstance(schema_version, int)
        or schema_version != SCHEMA_VERSION
    ):
        raise _SafeFailure("invalid_local_state")
    if payload.get("protocol_version") != PROTOCOL_VERSION:
        raise _SafeFailure("invalid_local_state")
    if payload.get("intent_id") != intent["intent_id"]:
        raise _SafeFailure("invalid_local_state")
    if payload.get("expected_redacted_account_id") != G.redacted_account_id:
        raise _SafeFailure("invalid_local_state")
    if payload.get("status") not in STATUSES:
        raise _SafeFailure("invalid_local_state")
    if not isinstance(payload.get("passorder_attempted"), bool):
        raise _SafeFailure("invalid_local_state")
    if payload.get("status") == "submission_attempted" and not payload.get(
        "passorder_attempted"
    ):
        raise _SafeFailure("invalid_local_state")
    if (
        payload.get("status") in PRE_SUBMISSION_STATUSES
        and payload.get("passorder_attempted")
    ):
        raise _SafeFailure("invalid_local_state")
    failure_code = payload.get("failure_code")
    if failure_code is not None:
        _validate_text(failure_code, MAX_FAILURE_CODE_LENGTH, "invalid_local_state")
    _parse_utc_text(payload.get("updated_at"))
    return payload


def _write_local_state(paths, intent, status, attempted, failure_code=None):
    if status not in STATUSES or not isinstance(attempted, bool):
        raise _SafeFailure("invalid_state_transition")
    payload = {
        "schema_version": SCHEMA_VERSION,
        "protocol_version": PROTOCOL_VERSION,
        "intent_id": intent["intent_id"],
        "updated_at": _artifact_utc_text(
            intent,
            _state_path(paths, intent["intent_id"]),
            "updated_at",
            MAX_STATE_BYTES,
        ),
        "status": status,
        "expected_redacted_account_id": G.redacted_account_id,
        "passorder_attempted": attempted,
        "failure_code": failure_code,
    }
    if frozenset(payload) != STATE_KEYS:
        raise _SafeFailure("invalid_state_shape")
    _atomic_write_document(
        _state_path(paths, intent["intent_id"]), payload, MAX_STATE_BYTES
    )
    return payload


def _safe_exception_type(exc):
    name = exc.__class__.__name__
    if not isinstance(name, str) or len(name) > 80:
        return "Exception"
    if not (name[0] == "_" or "A" <= name[0] <= "Z" or "a" <= name[0] <= "z"):
        return "Exception"
    for character in name[1:]:
        if not (
            character == "_"
            or "0" <= character <= "9"
            or "A" <= character <= "Z"
            or "a" <= character <= "z"
        ):
            return "Exception"
    return name


def _safe_primitive_text(value, maximum=MAX_IDENTIFIER_LENGTH):
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, bytes):
        try:
            text = value.decode("gbk", "replace")
        except Exception:
            return None
    elif isinstance(value, (str, int)):
        text = str(value)
    else:
        return None
    text = text.strip()
    if not text or len(text) > maximum or "\x00" in text:
        return None
    if "\r" in text or "\n" in text:
        return None
    raw_account = G.account_id
    if raw_account is not None:
        try:
            raw_text = str(raw_account).strip()
        except Exception:
            raw_text = None
        if raw_text and raw_text in text:
            return None
    return text


def _safe_status(value):
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, int):
        if value < -2147483648 or value > 2147483647:
            return None
        return value
    text = _safe_primitive_text(value, MAX_STATUS_LENGTH)
    if text is None:
        return None
    stripped = text.strip()
    try:
        numeric = int(stripped)
    except (TypeError, ValueError, OverflowError):
        numeric = None
    if numeric is not None and str(numeric) == stripped:
        if -2147483648 <= numeric <= 2147483647:
            return numeric
        return None
    normalized = stripped.casefold().replace(" ", "_").replace("-", "_")
    if normalized == "\u5e9f\u5355":
        return "rejected"
    return SAFE_STATUS_TEXT.get(normalized, "observed")


def _transient_identity_text(value):
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, bytes):
        try:
            text = value.decode("gbk", "strict")
        except Exception:
            return None
    elif isinstance(value, (str, int)):
        text = str(value)
    else:
        return None
    text = text.strip()
    if (
        not text
        or len(text) > MAX_IDENTIFIER_LENGTH
        or "\x00" in text
        or "\r" in text
        or "\n" in text
    ):
        return None
    return text


def _record_field(record, names):
    for name in names:
        try:
            if isinstance(record, dict):
                if name not in record:
                    continue
                value = record[name]
            else:
                value = getattr(record, name)
        except AttributeError:
            continue
        except Exception:
            raise _SafeFailure("broker_record_inspection_failed")
        if value is not None:
            return value
    return None


def _bounded_records(raw):
    if raw is None:
        return []
    if not isinstance(raw, (list, tuple)):
        raise _SafeFailure("invalid_broker_records")
    if len(raw) > MAX_BROKER_RECORDS:
        raise _SafeFailure("broker_record_limit")
    return list(raw)


def _matching_records(raw, intent_id):
    matches = []
    for record in _bounded_records(raw):
        remark = _record_field(record, ("m_strRemark",))
        if isinstance(remark, bytes):
            try:
                remark_text = remark.decode("gbk", "strict")
            except Exception:
                remark_text = None
        elif isinstance(remark, str):
            remark_text = remark
        else:
            remark_text = None
        if remark_text is not None and len(remark_text) <= 64 and remark_text == intent_id:
            matches.append(record)
    return matches


def _finite_number(value):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    if isinstance(value, float) and not math.isfinite(value):
        return None
    return value


def _nonnegative_integer(value):
    number = _finite_number(value)
    if number is None:
        return None
    if isinstance(number, float) and not number.is_integer():
        return None
    try:
        result = int(number)
    except (TypeError, ValueError, OverflowError):
        return None
    if result < 0:
        return None
    return result


def _normalized_record_symbol(record):
    instrument = _safe_primitive_text(
        _record_field(record, ("m_strInstrumentID",)), 32
    )
    exchange = _safe_primitive_text(_record_field(record, ("m_strExchangeID",)), 16)
    if instrument is None:
        return None
    instrument = instrument.upper().replace(" ", "")
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
    if "." in instrument:
        code, suffix = instrument.rsplit(".", 1)
        return code + "." + suffix_map.get(suffix, suffix)
    if exchange is None:
        return instrument
    return instrument + "." + suffix_map.get(exchange.upper(), exchange.upper())


def _validate_matching_record_shapes(orders, deals, intent):
    for record in orders + deals:
        raw_instrument = _record_field(record, ("m_strInstrumentID",))
        observed_symbol = _normalized_record_symbol(record)
        if raw_instrument is not None:
            if observed_symbol is None:
                raise _SafeFailure("broker_symbol_mismatch")
            if "." in observed_symbol:
                if observed_symbol != intent["symbol"]:
                    raise _SafeFailure("broker_symbol_mismatch")
            elif observed_symbol != intent["symbol"].split(".", 1)[0]:
                raise _SafeFailure("broker_symbol_mismatch")
        raw_side_values = []
        for side_field in ("m_nOffsetFlag", "m_nDirection", "m_strOptName"):
            raw_side = _record_field(record, (side_field,))
            if raw_side is not None:
                raw_side_values.append(raw_side)
        if raw_side_values:
            observed_sides = set()
            for raw_side in raw_side_values:
                side_text = _safe_primitive_text(raw_side, 32)
                if side_text is None:
                    continue
                lowered = side_text.casefold()
                if lowered in (
                    "23",
                    "48",
                    "buy",
                    "b",
                    "purchase",
                    "\u4e70\u5165",
                ):
                    observed_sides.add("buy")
                elif lowered in (
                    "24",
                    "49",
                    "sell",
                    "s",
                    "sale",
                    "\u5356\u51fa",
                ):
                    observed_sides.add("sell")
            if len(observed_sides) != 1 or intent["side"] not in observed_sides:
                raise _SafeFailure("broker_side_mismatch")
    for record in orders:
        original = _record_field(record, ("m_nVolumeTotalOriginal",))
        if original is not None:
            normalized_original = _nonnegative_integer(original)
            if normalized_original is None or normalized_original != intent["quantity"]:
                raise _SafeFailure("broker_quantity_mismatch")
        filled = _record_field(record, ("m_nVolumeTraded",))
        if filled is not None:
            normalized = _nonnegative_integer(filled)
            if normalized is None:
                raise _SafeFailure("invalid_broker_quantity")
            if normalized > intent["quantity"]:
                raise _SafeFailure("broker_quantity_exceeds_request")


def _is_rejected_order(record):
    values = (
        _record_field(record, ("m_nOrderStatus", "m_strOrderStatus")),
        _record_field(record, ("m_nOrderSubmitStatus", "m_strOrderSubmitStatus")),
    )
    for value in values:
        number = _nonnegative_integer(value)
        if number == 57:
            return True
        text = _safe_primitive_text(value, MAX_STATUS_LENGTH)
        if text is None:
            continue
        lowered = text.casefold()
        if (
            lowered == "57"
            or "rejected" in lowered
            or "reject" in lowered
            or "invalid" in lowered
            or "waste" in lowered
            or "\u5e9f\u5355" in lowered
        ):
            return True
    return False


def _deduplicated_deals(deals):
    result = []
    identities = {}
    broker_references = set()
    system_order_ids = set()
    for deal in deals:
        quantity = _nonnegative_integer(
            _record_field(deal, ("m_nVolume", "m_nVolumeTraded"))
        )
        price = _finite_number(
            _record_field(deal, ("m_dPrice", "m_dTradedPrice"))
        )
        if quantity is None or quantity == 0:
            raise _SafeFailure("invalid_broker_quantity")
        if price is None or price <= 0 or price > MAX_LIMIT_PRICE:
            raise _SafeFailure("invalid_broker_fill_price")
        raw_deal_id = _record_field(
            deal, ("m_strTradeID", "m_nTradeID", "m_strDealNo")
        )
        deal_id = _transient_identity_text(raw_deal_id)
        if raw_deal_id is not None and deal_id is None:
            raise _SafeFailure("invalid_broker_deal_identity")
        broker_reference = _transient_identity_text(
            _record_field(deal, ("m_strOrderRef", "m_nRef"))
        )
        system_order_id = _transient_identity_text(
            _record_field(deal, ("m_strOrderSysID", "m_strOrderSysId"))
        )
        signature = (quantity, float(price), broker_reference, system_order_id)
        if deal_id is not None and deal_id in identities:
            if identities[deal_id] != signature:
                raise _SafeFailure("conflicting_deal_identity")
            continue
        if deal_id is not None:
            identities[deal_id] = signature
        if broker_reference is not None:
            broker_references.add(broker_reference)
        if system_order_id is not None:
            system_order_ids.add(system_order_id)
        result.append(deal)
    if len(broker_references) > 1 or len(system_order_ids) > 1:
        raise _SafeFailure("conflicting_deal_identity")
    return result


def _reconcile(orders, deals, intent):
    if len(orders) > 1:
        raise _SafeFailure("multiple_broker_orders")
    _validate_matching_record_shapes(orders, deals, intent)
    deals = _deduplicated_deals(deals)
    if orders and deals:
        order_broker_reference = _transient_identity_text(
            _record_field(orders[0], ("m_strOrderRef", "m_nRef"))
        )
        order_system_id = _transient_identity_text(
            _record_field(orders[0], ("m_strOrderSysID", "m_strOrderSysId"))
        )
        for deal in deals:
            deal_broker_reference = _transient_identity_text(
                _record_field(deal, ("m_strOrderRef", "m_nRef"))
            )
            deal_system_id = _transient_identity_text(
                _record_field(deal, ("m_strOrderSysID", "m_strOrderSysId"))
            )
            if (
                order_broker_reference is not None
                and deal_broker_reference is not None
                and order_broker_reference != deal_broker_reference
            ):
                raise _SafeFailure("multiple_broker_orders")
            if (
                order_system_id is not None
                and deal_system_id is not None
                and order_system_id != deal_system_id
            ):
                raise _SafeFailure("multiple_broker_orders")
    total_quantity = 0
    weighted_amount = 0.0
    for deal in deals:
        raw_quantity = _record_field(deal, ("m_nVolume", "m_nVolumeTraded"))
        quantity = _nonnegative_integer(raw_quantity)
        total_quantity += quantity
        if total_quantity > intent["quantity"]:
            raise _SafeFailure("broker_quantity_exceeds_request")
        raw_price = _record_field(deal, ("m_dPrice", "m_dTradedPrice"))
        price = _finite_number(raw_price)
        weighted_increment = float(price) * quantity
        if not math.isfinite(weighted_increment):
            raise _SafeFailure("invalid_broker_fill_price")
        weighted_amount += weighted_increment
        if not math.isfinite(weighted_amount):
            raise _SafeFailure("invalid_broker_fill_price")

    average_price = None
    if total_quantity > 0:
        average_price = weighted_amount / total_quantity
        if not math.isfinite(average_price) or average_price <= 0:
            raise _SafeFailure("invalid_broker_fill_price")
    order = orders[0] if orders else None
    broker_reference = None
    system_order_id = None
    order_status = None
    submission_status = None
    if order is not None:
        broker_reference = _safe_primitive_text(
            _record_field(order, ("m_strOrderRef", "m_nRef"))
        )
        system_order_id = _safe_primitive_text(
            _record_field(order, ("m_strOrderSysID", "m_strOrderSysId"))
        )
        order_status = _safe_status(
            _record_field(order, ("m_nOrderStatus", "m_strOrderStatus"))
        )
        submission_status = _safe_status(
            _record_field(
                order, ("m_nOrderSubmitStatus", "m_strOrderSubmitStatus")
            )
        )
        if (
            broker_reference is None
            and system_order_id is None
            and order_status is None
            and submission_status is None
        ):
            order_status = "observed"
    elif deals:
        broker_reference = _safe_primitive_text(
            _record_field(deals[0], ("m_strOrderRef", "m_nRef"))
        )
        system_order_id = _safe_primitive_text(
            _record_field(deals[0], ("m_strOrderSysID", "m_strOrderSysId"))
        )

    if total_quantity == intent["quantity"] and len(deals) > 0:
        status = "filled"
    elif total_quantity > 0:
        status = "partially_filled"
    elif order is not None and _is_rejected_order(order):
        status = "rejected"
    elif order is not None:
        status = "broker_acknowledged"
    else:
        raise _SafeFailure("broker_record_not_found")
    return {
        "status": status,
        "broker_order_reference": broker_reference,
        "system_order_id": system_order_id,
        "order_status": order_status,
        "submission_status": submission_status,
        "filled_quantity": total_quantity,
        "average_fill_price": average_price,
        "deal_count": len(deals),
    }


def _latest_snapshot_sequence(paths):
    try:
        payload, encoded = _read_bounded_json(
            paths["snapshot"], MAX_SNAPSHOT_BYTES, missing_ok=True
        )
        del encoded
    except _SafeFailure:
        return None
    if payload is None:
        return None
    sequence = payload.get("sequence")
    if (
        isinstance(sequence, bool)
        or not isinstance(sequence, int)
        or sequence < 1
        or sequence > MAX_QUANTITY
    ):
        return None
    return sequence


def _result_payload(
    paths,
    intent,
    status,
    attempted,
    reconciliation=None,
    failure_code=None,
    failure_type=None,
):
    observed = reconciliation or {}
    payload = {
        "schema_version": SCHEMA_VERSION,
        "protocol_version": PROTOCOL_VERSION,
        "intent_id": intent["intent_id"],
        "generated_at": _artifact_utc_text(
            intent,
            _result_path(paths, intent["intent_id"]),
            "generated_at",
            MAX_RESULT_BYTES,
        ),
        "status": status,
        "expected_redacted_account_id": G.redacted_account_id,
        "symbol": intent["symbol"],
        "side": intent["side"],
        "requested_quantity": intent["quantity"],
        "limit_price": intent["limit_price"],
        "strategy_name": STRATEGY_NAME,
        "user_order_id": intent["intent_id"],
        "passorder_attempted": attempted,
        "broker_order_reference": observed.get("broker_order_reference"),
        "system_order_id": observed.get("system_order_id"),
        "order_status": observed.get("order_status"),
        "submission_status": observed.get("submission_status"),
        "filled_quantity": observed.get("filled_quantity", 0),
        "average_fill_price": observed.get("average_fill_price"),
        "deal_count": observed.get("deal_count", 0),
        "failure_code": failure_code,
        "failure_type": failure_type,
        "latest_snapshot_sequence": _latest_snapshot_sequence(paths),
        "acceptance_limitation": ACCEPTANCE_LIMITATION,
    }
    if frozenset(payload) != RESULT_KEYS:
        raise _SafeFailure("invalid_result_shape")
    return payload


def _safe_write_result(paths, payload):
    try:
        _atomic_write_document(
            _result_path(paths, payload["intent_id"]), payload, MAX_RESULT_BYTES
        )
        return True
    except Exception:
        return False


def init(ContextInfo):
    del ContextInfo
    raw_account = globals().get("account")
    raw_account_type = globals().get("accountType")
    try:
        _account_identity_bytes(raw_account)
        if not isinstance(raw_account_type, str):
            raise _SafeFailure("unsupported_account_type")
        normalized_account_type = raw_account_type.strip().upper()
        if normalized_account_type != ACCOUNT_TYPE:
            raise _SafeFailure("unsupported_account_type")
        paths = _bridge_paths(BRIDGE_ROOT)
        _ensure_directories(paths)
        if not _acquire_lock(paths):
            raise _SafeFailure("executor_already_running")
        binding_key = _load_binding_key(paths["binding_key"])
        redacted_account = _redacted_account_id(raw_account, binding_key)
    except Exception:
        _release_lock()
        G.account_id = None
        G.account_type = None
        G.redacted_account_id = None
        G.binding_key = None
        G.bridge_root = None
        G.intent_id = None
        G.stopped = True
        raise RuntimeError("QMT simulation executor initialization failed")
    G.account_id = raw_account
    G.account_type = raw_account_type
    G.redacted_account_id = redacted_account
    G.binding_key = binding_key
    G.bridge_root = paths["root"]
    G.intent_id = None
    G.in_handlebar = False
    G.stopped = False


def handlebar(ContextInfo):
    if not ContextInfo.is_last_bar():
        return
    if G.stopped or G.in_handlebar:
        return
    G.in_handlebar = True
    try:
        paths = _bridge_paths(G.bridge_root)
        intent_path = _select_intent_path(paths)
        if intent_path is None:
            return
        try:
            intent, encoded = _read_bounded_json(intent_path, MAX_INTENT_BYTES)
            _validate_intent(intent, encoded, intent_path, _utc_now_datetime())
        except _SafeFailure:
            return
        if G.intent_id is None:
            G.intent_id = intent["intent_id"]
        if G.intent_id != intent["intent_id"]:
            return

        try:
            local_state = _read_local_state(paths, intent)
        except _SafeFailure:
            try:
                _write_local_state(
                    paths, intent, "uncertain", True, "invalid_local_state"
                )
            except _SafeFailure:
                pass
            result = _result_payload(
                paths,
                intent,
                "uncertain",
                True,
                failure_code="invalid_local_state",
            )
            _safe_write_result(paths, result)
            return

        if local_state is None or local_state["status"] == "received":
            try:
                local_state = _write_local_state(paths, intent, "claimed", False)
            except _SafeFailure:
                return

        try:
            raw_orders = get_trade_detail_data(
                G.account_id,
                G.account_type,
                "order",
            )
            raw_deals = get_trade_detail_data(
                G.account_id,
                G.account_type,
                "deal",
            )
            matching_orders = _matching_records(raw_orders, intent["intent_id"])
            matching_deals = _matching_records(raw_deals, intent["intent_id"])
        except _SafeFailure as exc:
            if local_state["status"] == "uncertain":
                if _read_prior_result(paths, intent) is None:
                    result = _result_payload(
                        paths,
                        intent,
                        "uncertain",
                        local_state["passorder_attempted"],
                        failure_code=(local_state["failure_code"] or exc.code),
                    )
                    _safe_write_result(paths, result)
                return
            if (
                local_state["status"] in READBACK_STATUSES
                or local_state["status"] == "expired"
            ):
                return
            attempted = local_state["passorder_attempted"]
            try:
                local_state = _write_local_state(
                    paths, intent, "uncertain", attempted, exc.code
                )
            except _SafeFailure:
                pass
            result = _result_payload(
                paths,
                intent,
                "uncertain",
                attempted,
                failure_code=exc.code,
            )
            _safe_write_result(paths, result)
            return
        except Exception as exc:
            if local_state["status"] == "uncertain":
                if _read_prior_result(paths, intent) is None:
                    result = _result_payload(
                        paths,
                        intent,
                        "uncertain",
                        local_state["passorder_attempted"],
                        failure_code=(
                            local_state["failure_code"]
                            or "broker_evidence_uncertain"
                        ),
                        failure_type=_safe_exception_type(exc),
                    )
                    _safe_write_result(paths, result)
                return
            if (
                local_state["status"] in READBACK_STATUSES
                or local_state["status"] == "expired"
            ):
                return
            attempted = local_state["passorder_attempted"]
            if attempted:
                try:
                    local_state = _write_local_state(
                        paths, intent, "uncertain", True, "broker_query_failed"
                    )
                except _SafeFailure:
                    pass
            failure_status = "uncertain" if attempted else "claimed"
            result = _result_payload(
                paths,
                intent,
                failure_status,
                attempted,
                failure_code="broker_query_failed",
                failure_type=_safe_exception_type(exc),
            )
            _safe_write_result(paths, result)
            return

        if matching_orders or matching_deals:
            prior_state = local_state
            prior_result = _read_prior_result(paths, intent)
            try:
                reconciliation = _reconcile(matching_orders, matching_deals, intent)
                if not _readback_transition_allowed(
                    prior_state, prior_result, reconciliation
                ):
                    return
                reconciliation_failure = None
                if reconciliation["status"] == "rejected":
                    reconciliation_failure = "broker_order_rejected"
                local_state = _write_local_state(
                    paths,
                    intent,
                    reconciliation["status"],
                    local_state["passorder_attempted"],
                    reconciliation_failure,
                )
                result = _result_payload(
                    paths,
                    intent,
                    reconciliation["status"],
                    local_state["passorder_attempted"],
                    reconciliation=reconciliation,
                    failure_code=reconciliation_failure,
                )
            except _SafeFailure as exc:
                if prior_state["status"] in READBACK_STATUSES or prior_state[
                    "status"
                ] == "expired":
                    return
                attempted = local_state["passorder_attempted"]
                failure_status = "uncertain"
                try:
                    _write_local_state(
                        paths, intent, failure_status, attempted, exc.code
                    )
                except _SafeFailure:
                    pass
                result = _result_payload(
                    paths,
                    intent,
                    failure_status,
                    attempted,
                    failure_code=exc.code,
                )
            _safe_write_result(paths, result)
            return

        if local_state["status"] == "uncertain":
            if _read_prior_result(paths, intent) is None:
                result = _result_payload(
                    paths,
                    intent,
                    "uncertain",
                    local_state["passorder_attempted"],
                    failure_code=(
                        local_state["failure_code"] or "broker_evidence_uncertain"
                    ),
                )
                _safe_write_result(paths, result)
            return
        if (
            local_state["status"] in READBACK_STATUSES
            or local_state["status"] == "expired"
        ):
            return
        can_submit = (
            local_state["status"] in PRE_SUBMISSION_STATUSES
            and not local_state["passorder_attempted"]
            and local_state["failure_code"] is None
        )
        if _intent_is_expired(intent) and can_submit:
            try:
                _write_local_state(paths, intent, "expired", False, "intent_expired")
            except _SafeFailure:
                return
            result = _result_payload(
                paths,
                intent,
                "expired",
                False,
                failure_code="intent_expired",
            )
            _safe_write_result(paths, result)
            return

        if local_state["status"] in TERMINAL_STATUSES:
            return
        if not can_submit:
            try:
                _write_local_state(
                    paths, intent, "uncertain", True, "broker_readback_pending"
                )
            except _SafeFailure:
                pass
            result = _result_payload(
                paths,
                intent,
                "uncertain",
                True,
                failure_code="broker_readback_pending",
            )
            _safe_write_result(paths, result)
            return

        try:
            local_state = _write_local_state(
                paths, intent, "submission_attempted", True
            )
        except _SafeFailure:
            return
        operation_code = 23 if intent["side"] == "buy" else 24
        if _intent_is_expired(intent):
            try:
                _write_local_state(
                    paths, intent, "uncertain", True, "intent_expired_before_call"
                )
            except _SafeFailure:
                pass
            result = _result_payload(
                paths,
                intent,
                "uncertain",
                True,
                failure_code="intent_expired_before_call",
            )
            _safe_write_result(paths, result)
            return
        passorder(
            operation_code,
            1101,
            G.account_id,
            intent["symbol"],
            11,
            intent["limit_price"],
            intent["quantity"],
            STRATEGY_NAME,
            1,
            intent["intent_id"],
            ContextInfo,
        )
        try:
            _write_local_state(
                paths, intent, "uncertain", True, "broker_readback_pending"
            )
        except _SafeFailure:
            pass
        result = _result_payload(
            paths,
            intent,
            "uncertain",
            True,
            failure_code="broker_readback_pending",
        )
        _safe_write_result(paths, result)
    except Exception as exc:
        if (
            "intent" in locals()
            and isinstance(intent, dict)
            and "local_state" in locals()
            and isinstance(local_state, dict)
        ):
            attempted = local_state.get("passorder_attempted") is True
            current_status = local_state.get("status")
            if current_status in READBACK_STATUSES or current_status in (
                "expired",
                "uncertain",
            ):
                return
            failure_status = "uncertain" if attempted else "claimed"
            try:
                _write_local_state(
                    paths,
                    intent,
                    failure_status,
                    attempted,
                    "submission_uncertain" if attempted else "executor_failure",
                )
            except Exception:
                pass
            try:
                result = _result_payload(
                    paths,
                    intent,
                    failure_status,
                    attempted,
                    failure_code=(
                        "submission_uncertain" if attempted else "executor_failure"
                    ),
                    failure_type=_safe_exception_type(exc),
                )
                _safe_write_result(paths, result)
            except Exception:
                pass
    finally:
        G.in_handlebar = False


def stop(ContextInfo):
    del ContextInfo
    G.stopped = True
    _release_lock()
    G.account_id = None
    G.account_type = None
    G.redacted_account_id = None
    G.binding_key = None
    G.bridge_root = None
    G.intent_id = None
    G.in_handlebar = False
