"""Production-boundary helpers for Continuous Paper runtime configuration."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Mapping

from quantpilot_core.data_provider_normalization import canonicalize_a_share_symbol
from quantpilot_core.production_candidate import load_runtime_manifest
from quantpilot_core.real_candidate_pipeline import RealCandidatePipelineConfig
from quantpilot_core.runtime_account import AccountCapabilities


FROZEN_MANIFEST_PARAMETER_NAMES = frozenset(
    {
        "initial_capital",
        "target_symbol_count",
        "max_execution_symbols",
        "target_position_count",
        "max_position_weight",
        "reserve_cash_weight",
        "min_order_lot",
        "capital_profile_id",
        "strategy_id",
    }
)
PRODUCTION_INPUT_PAYLOAD_FIELDS = frozenset(
    {
        "symbols",
        "bars",
        "information_signals",
        "information_provenance",
        "advisory_provenance",
        "quant_firm_context",
    }
)
_ALLOWED_PIPELINE_OPTION_NAMES = frozenset(
    {
        "input_calendar_sessions",
        "input_calendar_provider",
        "account_capabilities",
        "shadow_desk_evidence",
    }
)


def load_production_input_payload(path: str | Path | None) -> dict[str, Any]:
    """Read an optional input JSON object without creating runtime objects."""
    if path is None:
        return {}
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(raw, Mapping):
        raise TypeError(
            f"production input JSON must contain an object, got {type(raw).__name__}"
        )
    normalize_production_input_payload(raw)
    return dict(raw)


def normalize_production_input_payload(
    payload: Mapping[str, Any] | None,
) -> dict[str, Any]:
    """Validate the shared production-input schema and create runtime values."""
    if payload is None:
        payload = {}
    if not isinstance(payload, Mapping):
        raise TypeError(
            f"production input payload must be an object, got {type(payload).__name__}"
        )

    unknown = set(payload) - PRODUCTION_INPUT_PAYLOAD_FIELDS
    if unknown:
        raise ValueError(
            "unknown production input fields: " + ", ".join(sorted(map(str, unknown)))
        )

    symbols = tuple(
        dict.fromkeys(
            _normalize_symbol(symbol)
            for symbol in _array_field(payload, "symbols")
            if str(symbol).strip()
        )
    )
    bars = _mapping_array_field(payload, "bars")
    information_signals = _mapping_array_field(payload, "information_signals")

    return {
        "symbols": symbols,
        "input_bars": bars,
        "information_signals": information_signals,
        "information_provenance": _mapping_field(
            payload, "information_provenance"
        ),
        "advisory_provenance": _mapping_field(payload, "advisory_provenance"),
        "quant_firm_context": _mapping_field(payload, "quant_firm_context"),
    }


def load_production_pipeline_config(
    *,
    manifest_path: str | Path,
    decision_session: str,
    state_path: str | Path = ".cache/real_candidate_daily_paper/state.json",
    report_path: str | Path | None = (
        ".cache/real_candidate_daily_paper/latest_report.json"
    ),
    live_market_data: bool = False,
    input_payload: Mapping[str, Any] | None = None,
    pipeline_options: Mapping[str, Any] | None = None,
) -> RealCandidatePipelineConfig:
    """Bind a manifest file and shared input payload to the real pipeline."""
    raw_manifest = json.loads(Path(manifest_path).read_text(encoding="utf-8"))
    if not isinstance(raw_manifest, Mapping):
        raise TypeError(
            "production manifest must be a JSON object, "
            f"got {type(raw_manifest).__name__}"
        )
    manifest = load_runtime_manifest(raw_manifest)

    frozen: dict[str, Any] = {}
    for group in (
        manifest.frozen_strategy_parameters,
        manifest.frozen_portfolio_parameters,
        manifest.frozen_execution_parameters,
    ):
        frozen.update(dict(group))

    initial_capital = float(frozen["initial_capital"])
    target_symbol_count = int(frozen["target_symbol_count"])
    max_execution_symbols = int(frozen["max_execution_symbols"])
    target_position_count = int(frozen["target_position_count"])
    max_position_weight = float(frozen["max_position_weight"])
    reserve_cash_weight = float(frozen["reserve_cash_weight"])
    min_order_lot = int(frozen["min_order_lot"])
    strategy_id = str(frozen["strategy_id"])

    if target_symbol_count > max_execution_symbols:
        raise ValueError(
            f"production manifest target_symbol_count ({target_symbol_count}) "
            f"exceeds max_execution_symbols ({max_execution_symbols}); "
            "rebuild the manifest with compatible values"
        )

    normalized_input = normalize_production_input_payload(input_payload)
    symbols = normalized_input["symbols"]
    if live_market_data and not symbols:
        raise ValueError(
            "live_market_data requires an explicit non-empty symbols list"
        )
    if live_market_data and len(symbols) > min(max_execution_symbols, 6):
        raise ValueError("--live-market-data supports at most 6 explicit symbols")

    options = _normalize_pipeline_options(pipeline_options)
    options = _with_serialized_daily_input_calendar(normalized_input, options)
    return RealCandidatePipelineConfig(
        decision_session=decision_session,
        initial_capital=initial_capital,
        state_path=state_path,
        report_path=report_path,
        strategy_id=strategy_id,
        production_strategy_id=manifest.strategy_candidate_id,
        target_position_count=target_position_count,
        max_position_weight=max_position_weight,
        reserve_cash_weight=reserve_cash_weight,
        min_order_lot=min_order_lot,
        capital_profile_id=manifest.capital_profile_id,
        max_execution_symbols=max_execution_symbols,
        target_symbol_count=target_symbol_count,
        live_market_data=live_market_data,
        production_manifest=manifest,
        **normalized_input,
        **options,
    )


def _with_serialized_daily_input_calendar(
    normalized_input: Mapping[str, Any], options: Mapping[str, Any]
) -> dict[str, Any]:
    """Recover the bridge calendar without adding top-level input fields."""
    context = normalized_input.get("quant_firm_context", {})
    bridge = (
        context.get("daily_production_input_v1", {})
        if isinstance(context, Mapping)
        else {}
    )
    if not isinstance(bridge, Mapping):
        raise TypeError(
            "quant_firm_context.daily_production_input_v1 must be an object"
        )
    sessions = bridge.get("calendar_sessions")
    provider = bridge.get("calendar_provider")
    if sessions is None and provider is None:
        return dict(options)
    if not isinstance(sessions, (list, tuple)) or not sessions:
        raise TypeError(
            "daily_production_input_v1.calendar_sessions must be a non-empty array"
        )
    if not str(provider or "").strip():
        raise ValueError(
            "daily_production_input_v1.calendar_provider must be non-empty"
        )
    inferred = {
        "input_calendar_sessions": tuple(str(item) for item in sessions),
        "input_calendar_provider": str(provider),
    }
    combined = dict(options)
    for key, value in inferred.items():
        if key in combined and combined[key] != value:
            raise ValueError(
                f"pipeline_options.{key} conflicts with serialized daily input calendar"
            )
        combined[key] = value
    return combined


def _normalize_pipeline_options(
    pipeline_options: Mapping[str, Any] | None,
) -> dict[str, Any]:
    if pipeline_options is None:
        return {}
    if not isinstance(pipeline_options, Mapping):
        raise TypeError("pipeline_options must be an object")

    frozen_conflicts = FROZEN_MANIFEST_PARAMETER_NAMES.intersection(pipeline_options)
    if frozen_conflicts:
        raise ValueError(
            "pipeline_options conflict with frozen manifest parameters: "
            + ", ".join(sorted(frozen_conflicts))
        )
    unknown = set(pipeline_options) - _ALLOWED_PIPELINE_OPTION_NAMES
    if unknown:
        raise ValueError(
            "unsupported pipeline_options: " + ", ".join(sorted(map(str, unknown)))
        )

    normalized = dict(pipeline_options)
    if "input_calendar_sessions" in normalized:
        value = normalized["input_calendar_sessions"]
        if not isinstance(value, (list, tuple)):
            raise TypeError("pipeline_options.input_calendar_sessions must be an array")
        normalized["input_calendar_sessions"] = tuple(str(item) for item in value)
    if "input_calendar_provider" in normalized:
        normalized["input_calendar_provider"] = str(
            normalized["input_calendar_provider"]
        )
    if "shadow_desk_evidence" in normalized:
        value = normalized["shadow_desk_evidence"]
        if not isinstance(value, Mapping):
            raise TypeError("pipeline_options.shadow_desk_evidence must be an object")
        normalized["shadow_desk_evidence"] = dict(value)
    if "account_capabilities" in normalized:
        value = normalized["account_capabilities"]
        if value is not None and not isinstance(value, Mapping):
            raise TypeError("pipeline_options.account_capabilities must be an object")
        if isinstance(value, Mapping):
            account_payload = dict(value)
            if "supported_order_types" in account_payload:
                order_types = account_payload["supported_order_types"]
                if not isinstance(order_types, (list, tuple)):
                    raise TypeError(
                        "pipeline_options.account_capabilities.supported_order_types "
                        "must be an array"
                    )
                account_payload["supported_order_types"] = tuple(
                    str(item) for item in order_types
                )
            normalized["account_capabilities"] = AccountCapabilities(**account_payload)
    return normalized


def _array_field(payload: Mapping[str, Any], name: str) -> tuple[Any, ...]:
    value = payload.get(name, [])
    if not isinstance(value, (list, tuple)):
        raise TypeError(f"production input field {name} must be an array")
    return tuple(value)


def _mapping_array_field(
    payload: Mapping[str, Any], name: str
) -> tuple[Mapping[str, Any], ...]:
    values = _array_field(payload, name)
    for index, value in enumerate(values):
        if not isinstance(value, Mapping):
            raise TypeError(
                f"production input field {name}[{index}] must be an object"
            )
    return tuple(dict(value) for value in values)


def _mapping_field(payload: Mapping[str, Any], name: str) -> dict[str, Any]:
    value = payload.get(name, {})
    if not isinstance(value, Mapping):
        raise TypeError(f"production input field {name} must be an object")
    return dict(value)


def _normalize_symbol(symbol: Any) -> str:
    normalized = canonicalize_a_share_symbol(symbol)
    if not re.fullmatch(r"\d{6}\.(SH|SZ)", normalized):
        raise ValueError(f"invalid A-share symbol: {symbol}")
    return normalized
