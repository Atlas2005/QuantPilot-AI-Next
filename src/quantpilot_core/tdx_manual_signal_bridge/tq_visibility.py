"""Supported TQ visibility fallback for candidate blocks and lifecycle warnings."""

from __future__ import annotations

import inspect
from pathlib import Path
from typing import Any, Mapping, Sequence

from quantpilot_core.real_data_provider import canonicalize_tdx_level1_symbol
from quantpilot_core.tdx_manual_signal_bridge.tq_publisher import (
    normalize_tq_response,
    publish_to_tq,
)


VISIBLE_WARNING_STATES = frozenset({"ENTRY", "WEAKENING", "EXIT", "INVALIDATED"})
DEFAULT_TQ_BLOCK_CODE = "QPTY"
DEFAULT_TQ_BLOCK_NAME = "QP候选"
STATE_LABEL_ZH = {
    "ENTRY": "买",
    "WEAKENING": "弱",
    "EXIT": "卖",
    "INVALIDATED": "失效",
}


class TQVisibilityContractError(RuntimeError):
    """The installed public method cannot be bound without guessing."""


def publish_experience_plan_visibility(
    plan: Mapping[str, Any],
    *,
    api: Any | None = None,
    block_code: str = DEFAULT_TQ_BLOCK_CODE,
    block_name: str = DEFAULT_TQ_BLOCK_NAME,
    show: bool = True,
) -> dict[str, Any]:
    """Publish the already-selected plan as a TDX user block and summary message."""

    resolved = _resolve_api(api)
    candidates = tuple(
        candidate
        for candidate in plan.get("candidates", ())
        if isinstance(candidate, Mapping) and str(candidate.get("symbol", "")).strip()
    )
    symbols = tuple(
        dict.fromkeys(
            canonicalize_tdx_level1_symbol(candidate["symbol"])
            for candidate in candidates
        )
    )
    if not symbols:
        raise ValueError("experience plan contains no candidate symbols")
    normalized_block_code = str(block_code).strip()
    normalized_block_name = str(block_name).strip()
    if not normalized_block_code:
        raise ValueError("block_code must be non-empty")
    if not normalized_block_name:
        raise ValueError("block_name must be non-empty")
    sector = _invoke_visibility_api(
        resolved,
        "create_sector",
        {
            "block_code": normalized_block_code,
            "block_name": normalized_block_name,
        },
        raise_on_api_failure=False,
    )
    sector_already_existed = _is_explicit_already_exists(sector)
    sector_can_be_checked = bool(sector["succeeded"] or sector_already_existed)
    block = _not_attempted_call("sector_creation_failed")
    if sector_can_be_checked:
        block = _invoke_visibility_api(
            resolved,
            "send_user_block",
            {
                "block_code": normalized_block_code,
                "stocks": list(symbols),
                "show": bool(show),
            },
            raise_on_api_failure=False,
        )
    sector_usable = bool(
        sector["succeeded"]
        or (sector_already_existed and block["succeeded"])
    )
    visibility_success = bool(sector_usable and block["succeeded"])
    message_text = build_after_close_message(plan, candidates=candidates)
    try:
        message = _invoke_visibility_api(
            resolved,
            "send_message",
            {"message": message_text},
            required=False,
            raise_on_api_failure=False,
        )
    except TQVisibilityContractError as exc:
        message = _failed_call(exc)
    return {
        "schema_version": "tq_visibility_fallback_v1",
        "status": (
            "candidate_block_published"
            if visibility_success
            else "candidate_block_publish_failed"
        ),
        "block_code": normalized_block_code,
        "block_name": normalized_block_name,
        "show": bool(show),
        "symbols": list(symbols),
        "published_symbols": list(symbols) if visibility_success else [],
        "candidate_count": len(symbols),
        "visibility_success": visibility_success,
        "sector_already_existed": sector_already_existed,
        "sector_usable": sector_usable,
        "sector_create_response": sector.get("response"),
        "user_block_response": block.get("response"),
        "message_response": message.get("response"),
        "create_sector": sector,
        "send_user_block": block,
        "send_message": message,
        "full_provenance": "existing_experience_plan_and_json_csv",
        "broker_or_order_api_calls": False,
    }


def publish_transition_warnings(
    records: Sequence[Mapping[str, Any]],
    *,
    api: Any | None = None,
) -> dict[str, Any]:
    """Publish only visible lifecycle transitions through ``send_warn``."""

    resolved = _resolve_api(api)
    warnings = build_transition_warning_payloads(records)
    results = [
        _invoke_visibility_api(resolved, "send_warn", warning)
        for warning in warnings
    ]
    return {
        "schema_version": "tq_visibility_fallback_v1",
        "status": "warnings_published" if warnings else "no_warning_transition",
        "warning_count": len(warnings),
        "states": [warning["state"] for warning in warnings],
        "symbols": [warning["stock_code"] for warning in warnings],
        "results": results,
        "broker_or_order_api_calls": False,
    }


def build_after_close_message(
    plan: Mapping[str, Any],
    *,
    candidates: Sequence[Mapping[str, Any]] | None = None,
) -> str:
    rows = tuple(candidates or ()) or tuple(
        candidate
        for candidate in plan.get("candidates", ())
        if isinstance(candidate, Mapping)
    )
    summaries = []
    for position, candidate in enumerate(rows, start=1):
        rank = candidate.get("candidate_rank") or position
        stance = candidate.get("deepseek_stance") or candidate.get("stance") or "neutral"
        symbol = canonicalize_tdx_level1_symbol(candidate.get("symbol", ""))
        summaries.append(f"{rank}:{symbol}:{stance}")
    target = str(plan.get("target_session", "next session"))
    text = f"QuantPilot {target} 候选 | " + "; ".join(summaries)
    return text[:500]


def build_transition_warning_payloads(
    records: Sequence[Mapping[str, Any]],
) -> tuple[dict[str, Any], ...]:
    output: list[dict[str, Any]] = []
    seen: set[str] = set()
    for record in records:
        state = str(record.get("state", "")).upper()
        if state not in VISIBLE_WARNING_STATES:
            continue
        symbol = canonicalize_tdx_level1_symbol(record.get("symbol", ""))
        timestamp = str(
            record.get("timestamp")
            or record.get("decision_timestamp")
            or ""
        )
        signal_id = str(record.get("signal_id") or f"{symbol}:{timestamp}:{state}")
        if signal_id in seen:
            continue
        seen.add(signal_id)
        rank = record.get("candidate_rank")
        stance = str(record.get("deepseek_stance") or "neutral")
        price = record.get("decision_price")
        price_text = "0" if price in (None, "") else str(price)
        reason = (
            f"QP {STATE_LABEL_ZH[state]}/{state} | rank={rank if rank is not None else '-'} "
            f"| DeepSeek={stance} | price={price_text} | time={timestamp} "
            "| provenance=latest_prediction.json/csv"
        )
        output.append(
            {
                "stock_code": symbol,
                "timestamp": timestamp,
                "price": price_text,
                "state": state,
                "reason": reason[:500],
            }
        )
    return tuple(output)


class LiveTQVisibilityPublisher:
    """Keep chart transport optional while making warnings independently usable."""

    def __init__(self, *, api: Any | None = None, tdx_plugin_dir: str | None = None) -> None:
        self.api = api
        self.tdx_plugin_dir = tdx_plugin_dir
        self._warned_keys: set[str] = set()
        self.last_report: dict[str, Any] | None = None

    def __call__(self, records: Sequence[Mapping[str, Any]]) -> Mapping[str, Any]:
        return self._publish(records, historical_baseline=False)

    def publish_baseline(
        self,
        records: Sequence[Mapping[str, Any]],
    ) -> Mapping[str, Any]:
        """Populate the pending overlay without emitting stale startup warnings."""

        return self._publish(records, historical_baseline=True)

    def _publish(
        self,
        records: Sequence[Mapping[str, Any]],
        *,
        historical_baseline: bool,
    ) -> Mapping[str, Any]:
        overlay_result: Mapping[str, Any] | None = None
        overlay_error: dict[str, str] | None = None
        try:
            overlay_result = publish_to_tq(
                records,
                tdx_plugin_dir=self.tdx_plugin_dir,
                dry_run=False,
                manage_tq_lifecycle=False,
            )
        except Exception as exc:
            overlay_error = {
                "error_type": type(exc).__name__,
                "sanitized_error": " ".join(str(exc).split())[:500],
            }
        new_records = []
        new_keys = []
        for record in records:
            state = str(record.get("state", "")).upper()
            if state not in VISIBLE_WARNING_STATES:
                continue
            key = str(
                record.get("signal_id")
                or f"{record.get('symbol')}:{record.get('timestamp')}:{state}"
            )
            if key in self._warned_keys:
                continue
            new_records.append(record)
            new_keys.append(key)
        if historical_baseline:
            self._warned_keys.update(new_keys)
            warning_result = {
                "schema_version": "tq_visibility_fallback_v1",
                "status": "historical_baseline_registered",
                "warning_count": 0,
                "suppressed_historical_transition_count": len(new_records),
                "broker_or_order_api_calls": False,
            }
        else:
            warning_result = publish_transition_warnings(new_records, api=self.api)
            self._warned_keys.update(new_keys)
        self.last_report = {
            "ordinary_chart_overlay_status": "pending_windows_visual_confirmation",
            "overlay_transport": overlay_result,
            "overlay_error": overlay_error,
            "warning_fallback": warning_result,
            "warning_fallback_active": True,
            "historical_baseline": historical_baseline,
        }
        return self.last_report


def publish_plan_to_installed_tq(
    plan: Mapping[str, Any],
    *,
    tdx_user_dir: str | Path,
    initialize_path: str,
    block_code: str = DEFAULT_TQ_BLOCK_CODE,
    block_name: str = DEFAULT_TQ_BLOCK_NAME,
    show: bool = True,
) -> dict[str, Any]:
    """Open one exact local TQ session, publish the plan, then close it."""

    from quantpilot_core.tdx_manual_signal_bridge.tq_display_smoke import (
        inspect_tqcenter_api,
        load_installed_tqcenter,
    )

    _, api, module_path = load_installed_tqcenter(tdx_user_dir)
    audit = inspect_tqcenter_api(api, module_path)
    initialized = False
    try:
        api.initialize(str(Path(initialize_path).resolve()))
        initialized = True
        report = publish_experience_plan_visibility(
            plan,
            api=api,
            block_code=block_code,
            block_name=block_name,
            show=show,
        )
    finally:
        if initialized:
            api.close()
    return {
        **report,
        "tqcenter_module_path": audit["module_path"],
        "tqcenter_module_sha256": audit["module_sha256"],
        "api_signatures": {
            name: details.get("signature")
            for name, details in audit["functions"].items()
            if details.get("available")
        },
    }


def _resolve_api(api: Any | None) -> Any:
    if api is not None:
        return api
    try:
        from tqcenter import tq  # type: ignore[import-untyped]
    except ImportError as exc:
        raise RuntimeError("tqcenter is unavailable for TQ visibility fallback") from exc
    return tq


def _invoke_visibility_api(
    api: Any,
    method_name: str,
    semantic_values: Mapping[str, Any],
    *,
    required: bool = True,
    raise_on_api_failure: bool = True,
) -> dict[str, Any]:
    method = getattr(api, method_name, None)
    if not callable(method):
        if required:
            raise TQVisibilityContractError(f"tqcenter.tq does not expose {method_name}")
        return {"attempted": False, "succeeded": False, "reason": "api_unavailable"}
    try:
        signature = inspect.signature(method)
    except (TypeError, ValueError) as exc:
        raise TQVisibilityContractError(
            f"cannot inspect {method_name} signature"
        ) from exc
    args: list[Any] = []
    kwargs: dict[str, Any] = {}
    explicit_parameters = tuple(
        parameter
        for parameter in signature.parameters.values()
        if parameter.name not in {"self", "cls"}
        and parameter.kind
        not in {inspect.Parameter.VAR_POSITIONAL, inspect.Parameter.VAR_KEYWORD}
    )
    has_only_variadic = not explicit_parameters and any(
        parameter.kind == inspect.Parameter.VAR_KEYWORD
        for parameter in signature.parameters.values()
    )
    has_only_positional_variadic = not explicit_parameters and any(
        parameter.kind == inspect.Parameter.VAR_POSITIONAL
        for parameter in signature.parameters.values()
    ) and not has_only_variadic
    if has_only_variadic:
        kwargs = _canonical_kwargs(method_name, semantic_values)
    elif has_only_positional_variadic:
        raise TQVisibilityContractError(
            f"cannot bind opaque positional-only {method_name} signature"
        )
    elif not explicit_parameters:
        raise TQVisibilityContractError(
            f"{method_name} signature exposes no bindable arguments"
        )
    else:
        for parameter in explicit_parameters:
            semantic_key = _semantic_key(method_name, parameter.name)
            if semantic_key is None:
                if parameter.default is not inspect.Parameter.empty:
                    continue
                raise TQVisibilityContractError(
                    f"unsupported required {method_name} parameter: {parameter.name}"
                )
            value = semantic_values[semantic_key]
            if parameter.kind is inspect.Parameter.POSITIONAL_ONLY:
                args.append(value)
            else:
                kwargs[parameter.name] = value
    raw = method(*args, **kwargs)
    response = normalize_tq_response(raw)
    succeeded = response.get("accepted") is True
    result = {
        "attempted": True,
        "succeeded": succeeded,
        "signature": str(signature),
        "argument_names": list(kwargs),
        "positional_argument_count": len(args),
        "response": response,
    }
    if not succeeded:
        result["error_type"] = str(
            response.get("error_type") or "IndeterminateTQResponse"
        )
        result["sanitized_error"] = str(
            response.get("sanitized_error")
            or response.get("message")
            or f"{method_name} did not return ErrorId=0"
        )
    if not succeeded and raise_on_api_failure:
        raise RuntimeError(
            f"{method_name} failed: {response.get('sanitized_error', 'TQ API error')}"
        )
    return result


def _canonical_kwargs(method_name: str, values: Mapping[str, Any]) -> dict[str, Any]:
    if method_name == "create_sector":
        return {
            "block_code": values["block_code"],
            "block_name": values["block_name"],
        }
    if method_name == "send_user_block":
        return {
            "block_code": values["block_code"],
            "stocks": values["stocks"],
            "show": values["show"],
        }
    if method_name == "send_message":
        return {"message": values["message"]}
    if method_name == "send_warn":
        return {
            "stock_code": values["stock_code"],
            "timestamp": values["timestamp"],
            "price": values["price"],
            "state": values["state"],
            "reason": values["reason"],
        }
    raise TQVisibilityContractError(f"unsupported TQ visibility method: {method_name}")


def _semantic_key(method_name: str, parameter_name: str) -> str | None:
    normalized = "".join(character for character in parameter_name.lower() if character.isalnum())
    if method_name == "create_sector":
        if normalized in {"blockcode", "sectorcode", "code"}:
            return "block_code"
        if normalized in {"blockname", "sectorname", "name"}:
            return "block_name"
    elif method_name == "send_user_block":
        if normalized in {"blockcode", "sectorcode", "code"}:
            return "block_code"
        if normalized in {
            "stocks",
            "stocklist",
            "codelist",
            "stockcodes",
            "codes",
            "stocks",
            "symbols",
        }:
            return "stocks"
        if normalized in {"show", "display", "visible", "open"}:
            return "show"
    elif method_name == "send_message":
        if normalized in {"message", "msg", "content", "text", "info"}:
            return "message"
    elif method_name == "send_warn":
        if normalized in {"stockcode", "code", "symbol", "securitycode"}:
            return "stock_code"
        if normalized in {"time", "datetime", "timestamp", "warntime", "signaltime"}:
            return "timestamp"
        if normalized in {"price", "signalprice", "lastprice"}:
            return "price"
        if normalized in {"state", "direction", "action", "signal", "signaltype", "bstype", "type"}:
            return "state"
        if normalized in {"reason", "message", "msg", "content", "text", "info", "remark"}:
            return "reason"
    return None


def _is_explicit_already_exists(call: Mapping[str, Any]) -> bool:
    if call.get("succeeded") is True:
        return False
    response = call.get("response")
    if not isinstance(response, Mapping):
        return False
    message = str(response.get("message") or "").casefold()
    return any(
        marker in message
        for marker in (
            "already exists",
            "already exist",
            "sector exists",
            "block exists",
            "已存在",
            "已经存在",
            "重复创建",
        )
    )


def _not_attempted_call(reason: str) -> dict[str, Any]:
    return {
        "attempted": False,
        "succeeded": False,
        "reason": reason,
        "response": None,
    }


def _failed_call(exc: Exception) -> dict[str, Any]:
    return {
        "attempted": True,
        "succeeded": False,
        "error_type": type(exc).__name__,
        "sanitized_error": " ".join(str(exc).split())[:500],
        "response": None,
    }
