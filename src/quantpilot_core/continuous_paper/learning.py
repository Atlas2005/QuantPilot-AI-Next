"""Read-only adapter from existing Quant Firm Learning Desk contracts."""
from __future__ import annotations

from dataclasses import asdict, is_dataclass
from typing import Any, Mapping


def build_learning_payload(report: Mapping[str, Any], session_id: str, shadow_delta: Mapping[str, Any] | None = None) -> Mapping[str, Any]:
    quant_firm = _mapping(report.get("quant_firm"))
    desk = _mapping(quant_firm.get("learning_desk")) or _mapping(report.get("learning_desk"))
    mutation = _mapping(desk.get("strategy_mutation")) or _mapping(desk.get("strategy_mutation_plan"))
    recommendations = mutation.get("recommendations", ())
    proposals = tuple(_proposal(item, session_id) for item in recommendations if isinstance(item, Mapping))
    return {
        "source_session_id": session_id,
        "attribution": _json(desk.get("attribution", {})),
        "experiment": _json(desk.get("experiment", desk.get("experiment_record", {}))),
        "failure_analysis": _json(desk.get("failure_analysis", {})),
        "strategy_mutation": _json(mutation),
        "parameter_proposals": proposals,
        "evidence_refs": tuple(desk.get("evidence_refs", ())) or (f"paper-session://{session_id}",),
        "production_vs_shadow_delta": dict(shadow_delta or {}),
    }


def _proposal(item: Mapping[str, Any], session_id: str) -> Mapping[str, Any]:
    proposed = item.get("proposed_value", item.get("recommended_value", item.get("value")))
    current = item.get("current_value", item.get("baseline_value"))
    return {
        "source_session_id": session_id,
        "parameter_name": item.get("parameter_name", item.get("parameter", "unknown")),
        "current_value": current,
        "proposed_value": proposed,
        "rationale": item.get("rationale", item.get("reason", "")),
        "supporting_evidence_refs": tuple(item.get("supporting_evidence_refs", item.get("evidence_refs", ()))),
        "status": "proposed",
        "requires_offline_validation": True,
    }


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _json(value: Any) -> Any:
    if is_dataclass(value) and not isinstance(value, type): return _json(asdict(value))
    if isinstance(value, Mapping): return {str(k): _json(v) for k, v in value.items()}
    if isinstance(value, (tuple, list)): return [_json(v) for v in value]
    return getattr(value, "value", value)
