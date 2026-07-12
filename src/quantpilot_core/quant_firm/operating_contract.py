"""Offline/cached seven-desk operating contract for the Quant Firm shadow arm."""

from __future__ import annotations

from dataclasses import asdict, dataclass, is_dataclass
from datetime import datetime, timezone
import hashlib
import json
import math
from typing import TYPE_CHECKING, Any, Mapping

from quantpilot_core.quant_firm.deepseek_advisory import DeepSeekAdvisoryRole

if TYPE_CHECKING:
    from quantpilot_core.quant_firm.role_skills import QuantFirmRoleSkillRegistry


CANONICAL_DEEPSEEK_DESKS = (
    DeepSeekAdvisoryRole.INFORMATION_DESK,
    DeepSeekAdvisoryRole.RESEARCH_DESK,
    DeepSeekAdvisoryRole.BACKTEST_DESK,
    DeepSeekAdvisoryRole.PORTFOLIO_DESK,
    DeepSeekAdvisoryRole.EXECUTION_SIMULATION_DESK,
    DeepSeekAdvisoryRole.LEARNING_DESK,
    DeepSeekAdvisoryRole.INVESTMENT_COMMITTEE,
)


@dataclass(frozen=True)
class DeskOperatingContract:
    role: DeepSeekAdvisoryRole
    required_evidence_inputs: tuple[str, ...]
    permitted_tools_and_skills: tuple[Mapping[str, Any], ...]
    mature_framework_references: tuple[str, ...]
    structured_output_contract: Mapping[str, Any]
    model_policy: Mapping[str, Any]
    allowed_parameter_proposals: Mapping[str, tuple[float, float]]
    may_influence_production_execution: bool
    provenance_requirements: tuple[str, ...]
    pit_evidence_timestamp_requirements: tuple[str, ...]
    fallback_and_abstention: str


@dataclass(frozen=True)
class QuantFirmOperatingContract:
    schema_version: str
    ai_firm_mode: str
    production_execution_arm: str
    desks: tuple[DeskOperatingContract, ...]
    limitations: tuple[str, ...]


def build_quant_firm_operating_contract(registry: QuantFirmRoleSkillRegistry | None = None) -> QuantFirmOperatingContract:
    if registry is None:
        from quantpilot_core.quant_firm.role_skills import build_default_role_skill_registry

        registry = build_default_role_skill_registry()
    contracts = tuple(_desk_contract(role, registry) for role in CANONICAL_DEEPSEEK_DESKS)
    return QuantFirmOperatingContract(
        schema_version="quant_firm_operating_contract_v1",
        ai_firm_mode="shadow_bound",
        production_execution_arm="non_llm_baseline",
        desks=contracts,
        limitations=(
            "All desk outputs are supplied/cached evidence only in this PR; no live model call is enabled.",
            "Shadow outputs cannot mutate orders, account state, fills, reconciliation, or frozen parameters.",
            "Learning Desk proposals require later shadow/OOS validation and explicit version promotion.",
        ),
    )


def validate_cached_desk_evidence(evidence: Mapping[str, Any] | None, *, execution_timestamp: str | datetime) -> Mapping[str, Mapping[str, Any]]:
    """Validate role and PIT boundary; invalid packets abstain rather than block production."""
    cutoff = _as_aware_datetime(execution_timestamp)
    source = evidence or {}
    output: dict[str, Mapping[str, Any]] = {}
    for role in CANONICAL_DEEPSEEK_DESKS:
        raw = source.get(role.value)
        if not isinstance(raw, Mapping):
            output[role.value] = _abstention(role, "missing_cached_evidence")
            continue
        if "role" not in raw or str(raw.get("role")) != role.value:
            output[role.value] = _abstention(role, "role_mismatch")
            continue
        timestamp = raw.get("pit_timestamp", raw.get("evidence_timestamp", raw.get("as_of_timestamp")))
        try:
            evidence_time = _as_aware_datetime(timestamp)
        except (TypeError, ValueError):
            output[role.value] = _abstention(role, "missing_or_invalid_pit_timestamp")
            continue
        if evidence_time >= cutoff:
            output[role.value] = _abstention(role, "pit_timestamp_not_before_execution")
            continue
        confidence = raw.get("confidence")
        if isinstance(confidence, bool) or not isinstance(confidence, (int, float)) or not math.isfinite(float(confidence)) or not 0.0 <= float(confidence) <= 1.0:
            output[role.value] = _abstention(role, "invalid_confidence")
            continue
        provenance = raw.get("provenance")
        if not isinstance(provenance, Mapping) or not all(str(provenance.get(key, "")).strip() for key in ("source", "evidence_reference", "evidence_timestamp")):
            output[role.value] = _abstention(role, "missing_or_invalid_provenance")
            continue
        try:
            provenance_time = _as_aware_datetime(provenance["evidence_timestamp"])
        except (TypeError, ValueError):
            output[role.value] = _abstention(role, "invalid_provenance_timestamp")
            continue
        if provenance_time >= cutoff or provenance_time != evidence_time:
            output[role.value] = _abstention(role, "provenance_timestamp_not_pit_consistent")
            continue
        if not any(str(raw.get(key, "")).strip() for key in ("model", "cache_reference", "fallback_reason")):
            output[role.value] = _abstention(role, "missing_model_cache_or_fallback_metadata")
            continue
        proposals = raw.get("proposed_parameter_changes", ())
        if not isinstance(proposals, (tuple, list)):
            output[role.value] = _abstention(role, "invalid_parameter_proposals")
            continue
        parsed_proposals = _validate_proposals(role, proposals)
        if parsed_proposals is None:
            output[role.value] = _abstention(role, "invalid_parameter_proposal")
            continue
        if str(raw.get("decision", "abstain")) not in {"approve_offline_shadow_cycle", "review", "hold", "reject", "abstain"}:
            output[role.value] = _abstention(role, "invalid_structured_decision")
            continue
        output[role.value] = {
            "role": role.value,
            "status": "abstained" if str(raw.get("decision")) == "abstain" else "accepted",
            "abstain": str(raw.get("decision")) == "abstain" or bool(raw.get("abstain", False)),
            "pit_timestamp": evidence_time.isoformat(),
            "summary": str(raw.get("summary", "cached structured evidence")),
            "decision": str(raw.get("decision", "abstain")),
            "confidence": float(confidence),
            "proposed_parameter_changes": parsed_proposals,
            "provenance": _json_ready(provenance),
            "evidence_digest": _digest_packet(raw),
            "specialist_evidence_digests": tuple(str(item) for item in raw.get("specialist_evidence_digests", ())),
        }
    return output


def build_shadow_committee_report(*, evidence: Mapping[str, Any] | None, execution_timestamp: str | datetime, production_final_recommendation: str) -> Mapping[str, Any]:
    """Assemble specialist evidence before the separate shadow committee decision."""
    desk_outputs = validate_cached_desk_evidence(evidence, execution_timestamp=execution_timestamp)
    specialist_outputs = tuple(desk_outputs[role.value] for role in CANONICAL_DEEPSEEK_DESKS if role is not DeepSeekAdvisoryRole.INVESTMENT_COMMITTEE)
    accepted = tuple(item for item in specialist_outputs if item["status"] == "accepted" and not item["abstain"])
    committee_input = desk_outputs[DeepSeekAdvisoryRole.INVESTMENT_COMMITTEE.value]
    proposal_changes = tuple(change for item in accepted for change in item["proposed_parameter_changes"])
    specialist_digests = tuple(item["evidence_digest"] for item in accepted)
    if not accepted:
        shadow_decision = "abstain"
        reason = "zero_valid_specialist_evidence"
    else:
        weighted = sum(float(item["confidence"]) * (1 if item["decision"] in {"approve_offline_shadow_cycle", "review"} else -1 if item["decision"] == "reject" else 0) for item in accepted)
        shadow_decision = "approve_offline_shadow_cycle" if weighted > 0 else "review" if weighted == 0 else "reject"
        reason = "deterministic_specialist_evidence_aggregation"
    committee_time = _as_aware_datetime(committee_input["pit_timestamp"]) if committee_input.get("status") == "accepted" else None
    specialist_times = tuple(_as_aware_datetime(item["pit_timestamp"]) for item in accepted)
    supplied_committee_bound = (
        committee_input.get("status") == "accepted"
        and tuple(committee_input.get("specialist_evidence_digests", ())) == specialist_digests
        and bool(specialist_times)
        and committee_time is not None and committee_time > max(specialist_times)
        and committee_time < _as_aware_datetime(execution_timestamp)
    )
    delta = {
        "production_final_recommendation": production_final_recommendation,
        "shadow_committee_decision": shadow_decision,
        "disagrees": shadow_decision not in {"abstain", production_final_recommendation},
    }
    return {
        "status": "shadow_bound",
        "ai_firm_mode": "shadow_bound",
        "ai_shadow_evidence_digest": _digest_packet(evidence or {}),
        "execution_timestamp": _as_aware_datetime(execution_timestamp).isoformat(),
        "specialist_desk_outputs": specialist_outputs,
        "committee_evidence": {**committee_input, "accepted_as_binding": supplied_committee_bound},
        "shadow_committee_decision": {"decision": shadow_decision, "reason": reason, "input_count": len(accepted), "specialist_evidence_digests": specialist_digests},
        "production_vs_shadow_decision_delta": delta,
        "proposed_parameter_changes": proposal_changes,
        "production_execution_mutation": False,
        "account_state_mutation": False,
        "order_mutation": False,
    }


def compact_dashboard_summary(*, production_manifest: Mapping[str, Any], effective_parameters: Mapping[str, Any], desk_shadow_report: Mapping[str, Any], production_decision: str) -> Mapping[str, Any]:
    """Small JSON-serializable future-exporter payload; no exporter is implemented here."""
    return {
        "production_candidate_id": production_manifest.get("production_candidate_id"),
        "production_candidate_version": production_manifest.get("production_candidate_version"),
        "production_candidate_digest": production_manifest.get("manifest_digest"),
        "execution_arm": production_manifest.get("production_execution_arm"),
        "ai_firm_mode": production_manifest.get("ai_firm_mode"),
        "desk_statuses": {
            **{item.get("role"): item.get("status") for item in desk_shadow_report.get("specialist_desk_outputs", ())},
            str(desk_shadow_report.get("committee_evidence", {}).get("role", "investment_committee")): desk_shadow_report.get("committee_evidence", {}).get("status", "not_configured"),
        },
        "production_decision": production_decision,
        "shadow_decision": desk_shadow_report.get("shadow_committee_decision"),
        "decision_delta": desk_shadow_report.get("production_vs_shadow_decision_delta"),
        "effective_parameters": _json_ready(effective_parameters),
        "source_artifact_digests": _json_ready(production_manifest.get("source_artifact_digests", {})),
        "runtime_limitations": ("offline_cached_evidence_only", "no_dashboard_exporter_in_pr123"),
    }


def _desk_contract(role: DeepSeekAdvisoryRole, registry: QuantFirmRoleSkillRegistry) -> DeskOperatingContract:
    skills = registry.list_by_role(role)
    return DeskOperatingContract(
        role=role,
        required_evidence_inputs=("role", "pit_timestamp", "summary", "decision", "provenance"),
        permitted_tools_and_skills=tuple({"skill_name": skill.skill_name, "tool_name": skill.tool_name, "enabled": skill.enabled_by_default} for skill in skills),
        mature_framework_references=tuple(sorted({skill.mature_framework or "disabled_placeholder" for skill in skills})),
        structured_output_contract={"decision": "string", "confidence": "0..1", "proposed_parameter_changes": "list", "abstain": "bool"},
        model_policy={"live_calls_allowed": False, "evidence_source": "supplied_or_cached", "fallback": "abstain"},
        allowed_parameter_proposals={"target_position_count": (1.0, 50.0), "reserve_cash_weight": (0.0, 0.5), "max_position_weight": (0.01, 1.0), "turnover_penalty": (0.0, 10.0)},
        may_influence_production_execution=False,
        provenance_requirements=("source", "artifact_or_cache_reference", "evidence_timestamp"),
        pit_evidence_timestamp_requirements=("pit_timestamp must be strictly before execution timestamp",),
        fallback_and_abstention="Missing, malformed, role-mismatched, or late evidence abstains without blocking production.",
    )


def _abstention(role: DeepSeekAdvisoryRole, reason: str) -> Mapping[str, Any]:
    return {"role": role.value, "status": "abstained", "abstain": True, "reason": reason, "decision": "abstain", "confidence": 0.0, "proposed_parameter_changes": (), "provenance": {}}


def _as_aware_datetime(value: str | datetime | None) -> datetime:
    if isinstance(value, datetime):
        parsed = value
    else:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    return parsed.replace(tzinfo=timezone.utc) if parsed.tzinfo is None else parsed.astimezone(timezone.utc)


def _bounded_confidence(value: Any) -> float:
    try:
        return max(0.0, min(1.0, float(value)))
    except (TypeError, ValueError):
        return 0.0


def _validate_proposals(role: DeepSeekAdvisoryRole, proposals: Any) -> tuple[Mapping[str, Any], ...] | None:
    allowed = {"target_position_count": (1.0, 50.0), "reserve_cash_weight": (0.0, 0.5), "max_position_weight": (0.01, 1.0), "turnover_penalty": (0.0, 10.0)}
    result = []
    for proposal in proposals:
        if not isinstance(proposal, Mapping): return None
        name = proposal.get("name")
        if name not in allowed or "current_value" not in proposal or "proposed_value" not in proposal: return None
        try: proposed = float(proposal["proposed_value"])
        except (TypeError, ValueError): return None
        low, high = allowed[str(name)]
        if not math.isfinite(proposed) or not low <= proposed <= high: return None
        result.append({"name": str(name), "current_value": _json_ready(proposal["current_value"]), "proposed_value": proposed, "role": role.value})
    return tuple(result)


def _digest_packet(value: Mapping[str, Any]) -> str:
    return hashlib.sha256(json.dumps(_json_ready(value), sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def _json_ready(value: Any) -> Any:
    if is_dataclass(value) and not isinstance(value, type): return _json_ready(asdict(value))
    if isinstance(value, Mapping): return {str(k): _json_ready(v) for k, v in value.items()}
    if isinstance(value, (tuple, list, set, frozenset)): return [_json_ready(v) for v in value]
    if hasattr(value, "value"): return value.value
    return value
