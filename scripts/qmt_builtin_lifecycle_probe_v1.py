#coding:gbk
"""QMT built-in read-only lifecycle probe for Python 3.6.

Copy this ASCII-only source into the QMT strategy editor.  The account and
accountType globals are supplied by QMT when the strategy is added from the
model-trading screen.  The probe writes only bounded lifecycle and query
status evidence; provider-returned values are never inspected or retained.
"""

import datetime
import errno
import json
import os


SCHEMA_VERSION = 1
PROTOCOL_VERSION = "qmt_builtin_lifecycle_probe_v1"
DEFAULT_BRIDGE_ROOT = r"D:\QuantPilotQMTBridge"
BRIDGE_ROOT = os.environ.get("QUANTPILOT_QMT_BRIDGE_ROOT", DEFAULT_BRIDGE_ROOT)
PROBE_FILENAME = "lifecycle_probe_v1.json"
PROBE_INTERVAL_SECONDS = 30
MAX_EXCEPTION_TYPE_LENGTH = 80
MAX_CALLBACK_COUNT = 2147483647
MAX_EVIDENCE_BYTES = 64 * 1024
CALLBACK_NAMES = (
    "init",
    "after_init",
    "timer_callback",
    "handlebar",
    "stop",
)
QUERY_NAMES = ("account", "position", "order", "deal")


def _new_lifecycle_evidence():
    return {
        name: {"count": 0, "latest_at": None}
        for name in CALLBACK_NAMES
    }


def _new_query_evidence():
    result = {}
    for callback_name in CALLBACK_NAMES:
        callback_result = {"attempted": False}
        for query_name in QUERY_NAMES:
            callback_result[query_name] = {
                "attempted": False,
                "succeeded": None,
                "exception_type": None,
            }
        result[callback_name] = callback_result
    return result


class _ProbeState(object):
    def __init__(self):
        self.account_id = None
        self.account_type = None
        self.bridge_root = None
        self.started_at = None
        self.updated_at = None
        self.lifecycle = _new_lifecycle_evidence()
        self.queries = _new_query_evidence()
        self.timer_registration_attempted = False
        self.timer_registration_succeeded = False
        self.timer_registration_exception_type = None
        self.is_last_bar_call_attempted = False
        self.is_last_bar_callable = None
        self.is_last_bar_exception_type = None
        self.initialized = False
        self.stopped = False
        self.in_write = False


G = _ProbeState()


def _utc_now_text():
    value = datetime.datetime.utcnow().replace(microsecond=0)
    return value.strftime("%Y-%m-%dT%H:%M:%SZ")


def _safe_exception_type(exc):
    try:
        name = type(exc).__name__
    except Exception:
        return "Exception"
    if not isinstance(name, str) or not name or len(name) > MAX_EXCEPTION_TYPE_LENGTH:
        return "Exception"
    first = name[0]
    if not (
        first == "_"
        or "A" <= first <= "Z"
        or "a" <= first <= "z"
    ):
        return "Exception"
    for character in name[1:]:
        if not (
            character == "_"
            or "0" <= character <= "9"
            or "A" <= character <= "Z"
            or "a" <= character <= "z"
        ):
            return "Exception"
    lowered_name = name.casefold()
    for value in (G.account_id, G.account_type):
        if isinstance(value, bool) or not isinstance(value, (str, int)):
            continue
        sensitive = str(value).strip()
        if sensitive and sensitive.casefold() in lowered_name:
            return "Exception"
    return name


def _reset_state(raw_account, raw_account_type, bridge_root, started_at):
    G.account_id = raw_account
    G.account_type = raw_account_type
    G.bridge_root = os.path.abspath(bridge_root)
    G.started_at = started_at
    G.updated_at = started_at
    G.lifecycle = _new_lifecycle_evidence()
    G.queries = _new_query_evidence()
    G.timer_registration_attempted = False
    G.timer_registration_succeeded = False
    G.timer_registration_exception_type = None
    G.is_last_bar_call_attempted = False
    G.is_last_bar_callable = None
    G.is_last_bar_exception_type = None
    G.initialized = True
    G.stopped = False
    G.in_write = False


def _record_callback(callback_name, observed_at):
    evidence = G.lifecycle[callback_name]
    if evidence["count"] < MAX_CALLBACK_COUNT:
        evidence["count"] += 1
    evidence["latest_at"] = observed_at
    G.updated_at = observed_at


def _attempt_query(callback_name, query_name):
    evidence = G.queries[callback_name][query_name]
    evidence["attempted"] = True
    try:
        returned = get_trade_detail_data(
            G.account_id,
            G.account_type,
            query_name,
        )
        del returned
    except Exception as exc:
        evidence["succeeded"] = False
        evidence["exception_type"] = _safe_exception_type(exc)
    else:
        evidence["succeeded"] = True
        evidence["exception_type"] = None


def _attempt_callback_queries(callback_name):
    evidence = G.queries[callback_name]
    if evidence["attempted"]:
        return
    evidence["attempted"] = True
    for query_name in QUERY_NAMES:
        _attempt_query(callback_name, query_name)


def _evidence_payload():
    return {
        "schema_version": SCHEMA_VERSION,
        "protocol_version": PROTOCOL_VERSION,
        "started_at": G.started_at,
        "updated_at": G.updated_at,
        "lifecycle": G.lifecycle,
        "timer_registration": {
            "attempted": G.timer_registration_attempted,
            "succeeded": G.timer_registration_succeeded,
            "exception_type": G.timer_registration_exception_type,
        },
        "handlebar_state": {
            "is_last_bar_call_attempted": G.is_last_bar_call_attempted,
            "is_last_bar_callable": G.is_last_bar_callable,
            "is_last_bar_exception_type": G.is_last_bar_exception_type,
        },
        "queries": G.queries,
        "safety": {
            "order_submission_enabled": False,
            "cancel_enabled": False,
            "passorder_invoked": False,
            "cancel_invoked": False,
        },
    }


def _canonical_bytes(payload):
    encoded = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    ).encode("utf-8")
    if len(encoded) > MAX_EVIDENCE_BYTES:
        raise ValueError("lifecycle evidence exceeds fixed bound")
    return encoded


def _bridge_paths(root=None):
    selected = root if root is not None else BRIDGE_ROOT
    absolute_root = os.path.abspath(selected)
    directory = os.path.join(absolute_root, "probe")
    final_path = os.path.join(directory, PROBE_FILENAME)
    return {
        "directory": directory,
        "final": final_path,
        "temporary": final_path + ".tmp",
    }


def _ensure_probe_directory(path):
    try:
        os.makedirs(path)
    except OSError as exc:
        if getattr(exc, "errno", None) != errno.EEXIST or not os.path.isdir(path):
            raise


def _atomic_write(payload, root=None):
    paths = _bridge_paths(root)
    _ensure_probe_directory(paths["directory"])
    encoded = _canonical_bytes(payload)
    with open(paths["temporary"], "wb") as handle:
        handle.write(encoded)
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(paths["temporary"], paths["final"])
    return paths["final"]


def _write_current_evidence():
    if G.in_write:
        return False
    G.in_write = True
    try:
        _atomic_write(_evidence_payload(), G.bridge_root)
        return True
    except Exception:
        return False
    finally:
        G.in_write = False


def _observe_callback(callback_name):
    if not G.initialized or G.stopped:
        return False
    observed_at = _utc_now_text()
    _record_callback(callback_name, observed_at)
    _attempt_callback_queries(callback_name)
    _write_current_evidence()
    return True


def lifecycle_probe_timer_callback(ContextInfo):
    del ContextInfo
    _observe_callback("timer_callback")


def init(ContextInfo):
    observed_at = _utc_now_text()
    _reset_state(
        globals().get("account"),
        globals().get("accountType"),
        BRIDGE_ROOT,
        observed_at,
    )
    _record_callback("init", observed_at)
    G.timer_registration_attempted = True
    try:
        ContextInfo.run_time(
            "lifecycle_probe_timer_callback",
            "{0}nSecond".format(PROBE_INTERVAL_SECONDS),
            "2019-10-14 13:20:00",
        )
    except Exception as exc:
        G.timer_registration_succeeded = False
        G.timer_registration_exception_type = _safe_exception_type(exc)
    else:
        G.timer_registration_succeeded = True
        G.timer_registration_exception_type = None
    _attempt_callback_queries("init")
    _write_current_evidence()


def after_init(ContextInfo):
    del ContextInfo
    _observe_callback("after_init")


def handlebar(ContextInfo):
    if not G.initialized or G.stopped:
        return
    observed_at = _utc_now_text()
    _record_callback("handlebar", observed_at)
    G.is_last_bar_call_attempted = True
    try:
        ContextInfo.is_last_bar()
    except Exception as exc:
        G.is_last_bar_callable = False
        G.is_last_bar_exception_type = _safe_exception_type(exc)
    else:
        G.is_last_bar_callable = True
        G.is_last_bar_exception_type = None
    _attempt_callback_queries("handlebar")
    _write_current_evidence()


def stop(ContextInfo):
    del ContextInfo
    if not G.initialized or G.stopped:
        return
    try:
        observed_at = _utc_now_text()
        _record_callback("stop", observed_at)
        _attempt_callback_queries("stop")
        _write_current_evidence()
    finally:
        G.stopped = True
        G.account_id = None
        G.account_type = None
