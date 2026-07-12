"""Compact, versioned binding for an evaluated production candidate.

The contract deliberately stores artifact references and digests, never the
artifacts themselves.  It is a binding/audit record, not a promotion claim.
"""

from __future__ import annotations

import hashlib
import json
import os
from dataclasses import asdict, dataclass, field, is_dataclass, replace
from pathlib import Path
from typing import Any, Mapping


PRODUCTION_CANDIDATE_SCHEMA_VERSION = "production_candidate_v1"
DEFAULT_PRODUCTION_CANDIDATE_ID = "equal_weight_baseline_production_candidate"
DEFAULT_PRODUCTION_CANDIDATE_VERSION = "1.0.0"
RUNTIME_REQUIRED_FIELDS = frozenset({
    "schema_version", "production_candidate_id", "production_candidate_version",
    "strategy_candidate_id", "execution_ranking_mode", "production_execution_arm",
    "ai_firm_mode", "multi_agent_mode", "capital_profile_id", "frozen_strategy_parameters",
    "frozen_portfolio_parameters", "frozen_execution_parameters", "fee_profile_policy",
    "account_capability_policy", "benchmark", "source_artifacts", "source_artifact_digests",
    "evidence_scope", "information_capability_status", "promotion_reason", "limitations",
    "created_at", "snapshot_digest", "code_revision", "manifest_digest",
})
CONSUMED_FROZEN_PARAMETERS = frozenset({
    "target_symbol_count", "target_position_count", "max_execution_symbols", "max_position_weight",
    "reserve_cash_weight", "min_order_lot", "initial_capital", "strategy_id",
})
REQUIRED_FROZEN_PARAMETERS = frozenset({"initial_capital", "target_symbol_count", "target_position_count", "max_execution_symbols", "max_position_weight", "reserve_cash_weight", "min_order_lot", "strategy_id"})


class ProductionCandidateContractError(ValueError):
    """Raised for an invalid manifest or a concrete production binding mismatch."""


@dataclass(frozen=True)
class ProductionCandidateManifest:
    schema_version: str = PRODUCTION_CANDIDATE_SCHEMA_VERSION
    production_candidate_id: str = DEFAULT_PRODUCTION_CANDIDATE_ID
    production_candidate_version: str = DEFAULT_PRODUCTION_CANDIDATE_VERSION
    strategy_candidate_id: str = "equal_weight_baseline"
    execution_ranking_mode: str = "equal_weight_baseline"
    production_execution_arm: str = "non_llm_baseline"
    ai_firm_mode: str = "shadow_bound"
    multi_agent_mode: str = "seven_desk_committee_shadow"
    capital_profile_id: str = "default_paper_capital"
    frozen_strategy_parameters: Mapping[str, Any] = field(default_factory=dict)
    frozen_portfolio_parameters: Mapping[str, Any] = field(default_factory=dict)
    frozen_execution_parameters: Mapping[str, Any] = field(default_factory=dict)
    fee_profile_policy: Mapping[str, Any] = field(default_factory=dict)
    account_capability_policy: Mapping[str, Any] = field(default_factory=dict)
    benchmark: Mapping[str, Any] | str = field(default_factory=dict)
    source_artifacts: Mapping[str, str] = field(default_factory=dict)
    source_artifact_digests: Mapping[str, str] = field(default_factory=dict)
    snapshot_digest: str | None = None
    code_revision: str | None = None
    evidence_scope: Mapping[str, Any] = field(default_factory=dict)
    information_capability_status: Mapping[str, Any] = field(default_factory=dict)
    promotion_reason: str = "evidence_backed_non_llm_baseline; AI profitability not proven"
    limitations: tuple[str, ...] = (
        "AI incremental profitability is not proven.",
        "Production execution remains the validated non-LLM arm.",
    )
    created_at: str | None = None
    manifest_digest: str = ""


def manifest_payload(manifest: ProductionCandidateManifest | Mapping[str, Any], *, include_digest: bool = True) -> Mapping[str, Any]:
    value = coerce_manifest(manifest, verify=False)
    return _manifest_payload_value(value, include_digest=include_digest)


def _manifest_payload_value(value: ProductionCandidateManifest, *, include_digest: bool) -> Mapping[str, Any]:
    payload = _json_ready(asdict(value))
    if not include_digest:
        payload.pop("manifest_digest", None)
    return payload


def manifest_digest(manifest: ProductionCandidateManifest | Mapping[str, Any]) -> str:
    if isinstance(manifest, ProductionCandidateManifest):
        value = manifest
    elif isinstance(manifest, Mapping):
        fields = {name: manifest.get(name) for name in ProductionCandidateManifest.__dataclass_fields__}
        value = ProductionCandidateManifest(**{key: item for key, item in fields.items() if item is not None})
    else:
        raise TypeError("production manifest must be a ProductionCandidateManifest or mapping")
    _validate_manifest_shape(value)
    return _digest(_manifest_payload_value(value, include_digest=False))


def coerce_manifest(manifest: ProductionCandidateManifest | Mapping[str, Any], *, verify: bool = True) -> ProductionCandidateManifest:
    if isinstance(manifest, ProductionCandidateManifest):
        value = manifest
    elif isinstance(manifest, Mapping):
        fields = {name: manifest.get(name) for name in ProductionCandidateManifest.__dataclass_fields__}
        value = ProductionCandidateManifest(**{key: item for key, item in fields.items() if item is not None})
    else:
        raise TypeError("production manifest must be a ProductionCandidateManifest or mapping")
    _validate_manifest_shape(value)
    expected = _digest(_manifest_payload_value(value, include_digest=False))
    if verify and value.manifest_digest and value.manifest_digest != expected:
        raise ProductionCandidateContractError("production manifest digest mismatch")
    return replace(value, manifest_digest=expected) if not value.manifest_digest else value


def load_runtime_manifest(manifest: ProductionCandidateManifest | Mapping[str, Any]) -> ProductionCandidateManifest:
    """Strict production loader; unlike the builder it never fills external gaps."""
    if isinstance(manifest, Mapping):
        unknown = set(manifest) - set(ProductionCandidateManifest.__dataclass_fields__)
        missing = RUNTIME_REQUIRED_FIELDS - set(manifest)
        if unknown:
            raise ProductionCandidateContractError(f"unknown production manifest fields: {', '.join(sorted(unknown))}")
        if missing:
            raise ProductionCandidateContractError(f"missing required production manifest fields: {', '.join(sorted(missing))}")
        value = ProductionCandidateManifest(**dict(manifest))
    elif isinstance(manifest, ProductionCandidateManifest):
        value = manifest
    else:
        raise TypeError("production manifest must be a ProductionCandidateManifest or mapping")
    if not value.manifest_digest:
        raise ProductionCandidateContractError("runtime production manifest requires manifest_digest")
    value = coerce_manifest(value, verify=True)
    _validate_frozen_parameter_groups(value)
    return value


def build_production_candidate_manifest(*, created_at: str | None = None, code_revision: str | None = None, source_artifacts: Mapping[str, Any] | None = None, source_artifact_digests: Mapping[str, str] | None = None, snapshot_digest: str | None = None, **overrides: Any) -> ProductionCandidateManifest:
    """Build a deterministic manifest except for explicitly supplied values."""
    artifacts, digests = _artifact_refs_and_digests(source_artifacts or {}, source_artifact_digests or {})
    value = ProductionCandidateManifest(
        created_at=created_at,
        code_revision=code_revision,
        source_artifacts=artifacts,
        source_artifact_digests=digests,
        snapshot_digest=snapshot_digest,
        **overrides,
    )
    value = coerce_manifest(value, verify=False)
    return replace(value, manifest_digest=manifest_digest(value))


def verify_manifest_digest(manifest: ProductionCandidateManifest | Mapping[str, Any]) -> bool:
    value = coerce_manifest(manifest, verify=False)
    return bool(value.manifest_digest) and value.manifest_digest == manifest_digest(value)


def write_manifest_atomic(manifest: ProductionCandidateManifest | Mapping[str, Any], path: str | Path) -> str:
    value = coerce_manifest(manifest)
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_name(f".{target.name}.tmp")
    with temporary.open("w", encoding="utf-8") as handle:
        handle.write(json.dumps(manifest_payload(value), sort_keys=True, indent=2, ensure_ascii=True))
        handle.write("\n")
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temporary, target)
    return str(target)


def effective_parameter_payload(manifest: ProductionCandidateManifest | Mapping[str, Any], *, runtime_parameters: Mapping[str, Any]) -> Mapping[str, Any]:
    value = load_runtime_manifest(manifest)
    frozen = {
        **dict(value.frozen_strategy_parameters),
        **dict(value.frozen_portfolio_parameters),
        **dict(value.frozen_execution_parameters),
    }
    effective = dict(runtime_parameters)
    for name, frozen_value in frozen.items():
        if name in effective and _json_ready(effective[name]) != _json_ready(frozen_value):
            raise ProductionCandidateContractError(f"frozen parameter mismatch: {name}")
        effective[name] = frozen_value
    effective.update({
        "strategy_candidate_id": value.strategy_candidate_id,
        "execution_ranking_mode": value.execution_ranking_mode,
        "production_execution_arm": value.production_execution_arm,
    })
    return {key: _json_ready(item) for key, item in sorted(effective.items())}


def effective_parameter_digest(manifest: ProductionCandidateManifest | Mapping[str, Any], *, runtime_parameters: Mapping[str, Any]) -> str:
    return _digest(effective_parameter_payload(manifest, runtime_parameters=runtime_parameters))


def _artifact_refs_and_digests(artifacts: Mapping[str, Any], supplied_digests: Mapping[str, str]) -> tuple[Mapping[str, str], Mapping[str, str]]:
    refs: dict[str, str] = {}
    digests = {str(key): str(value) for key, value in supplied_digests.items()}
    for name, artifact in artifacts.items():
        key = str(name)
        if isinstance(artifact, (str, Path)):
            path = Path(artifact)
            refs[key] = str(path)
            if key not in digests and path.exists() and path.is_file():
                digest = hashlib.sha256()
                with path.open("rb") as handle:
                    for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                        digest.update(chunk)
                digests[key] = digest.hexdigest()
        else:
            raise ProductionCandidateContractError("source artifact references must be compact strings or explicit local paths")
    return refs, digests


def _validate_manifest_shape(value: ProductionCandidateManifest) -> None:
    if value.schema_version != PRODUCTION_CANDIDATE_SCHEMA_VERSION:
        raise ProductionCandidateContractError(f"unsupported production manifest schema_version: {value.schema_version}")
    required = ("production_candidate_id", "production_candidate_version", "strategy_candidate_id", "execution_ranking_mode", "production_execution_arm", "ai_firm_mode", "multi_agent_mode")
    if any(not str(getattr(value, key, "")).strip() for key in required):
        raise ProductionCandidateContractError("production manifest contains an empty required binding")
    if value.production_execution_arm != "non_llm_baseline":
        raise ProductionCandidateContractError("production execution arm must remain non_llm_baseline")
    if value.ai_firm_mode != "shadow_bound":
        raise ProductionCandidateContractError("AI firm mode must remain shadow_bound")
    if value.strategy_candidate_id != "equal_weight_baseline" or value.execution_ranking_mode != "equal_weight_baseline":
        raise ProductionCandidateContractError("production candidate and ranking mode must both be equal_weight_baseline")
    if value.multi_agent_mode != "seven_desk_committee_shadow":
        raise ProductionCandidateContractError("unsupported multi_agent_mode")
    if not str(value.capital_profile_id).strip() or not value.benchmark:
        raise ProductionCandidateContractError("capital_profile_id and benchmark must be non-empty")


def _validate_frozen_parameter_groups(value: ProductionCandidateManifest) -> None:
    if not {"pr121", "pr122"}.issubset(value.source_artifacts) or not {"pr121", "pr122"}.issubset(value.source_artifact_digests):
        raise ProductionCandidateContractError("runtime manifest requires separate PR #121 and PR #122 artifact references and digests")
    groups = (dict(value.frozen_strategy_parameters), dict(value.frozen_portfolio_parameters), dict(value.frozen_execution_parameters))
    seen: set[str] = set()
    for group in groups:
        duplicate = seen.intersection(group)
        if duplicate:
            raise ProductionCandidateContractError(f"conflicting duplicate frozen parameters: {', '.join(sorted(duplicate))}")
        seen.update(group)
    unsupported = seen - CONSUMED_FROZEN_PARAMETERS
    if unsupported:
        raise ProductionCandidateContractError(f"frozen parameters not consumed by runtime: {', '.join(sorted(unsupported))}")
    missing = REQUIRED_FROZEN_PARAMETERS - seen
    if missing:
        raise ProductionCandidateContractError(f"missing required frozen production parameters: {', '.join(sorted(missing))}")
    frozen = {key: next(group[key] for group in groups if key in group) for key in seen}
    if float(frozen["initial_capital"]) <= 0 or int(frozen["target_symbol_count"]) <= 0 or int(frozen["target_position_count"]) <= 0 or int(frozen["max_execution_symbols"]) <= 0 or int(frozen["min_order_lot"]) <= 0:
        raise ProductionCandidateContractError("frozen capital/count/lot values must be positive")
    if int(frozen["target_position_count"]) > int(frozen["max_execution_symbols"]) or not 0 < float(frozen["max_position_weight"]) <= 1 or not 0 <= float(frozen["reserve_cash_weight"]) < 1:
        raise ProductionCandidateContractError("frozen portfolio numeric ranges are invalid")
    if not value.fee_profile_policy or not str(value.fee_profile_policy.get("profile_id", "")).strip() or not str(value.fee_profile_policy.get("required_provenance", "")).strip():
        raise ProductionCandidateContractError("runtime manifest requires non-empty fee profile identity and provenance policy")
    if not value.account_capability_policy or not str(value.account_capability_policy.get("capability_digest", "")).strip():
        raise ProductionCandidateContractError("runtime manifest requires non-empty account capability digest policy")
    if not value.code_revision:
        raise ProductionCandidateContractError("runtime manifest requires non-empty code_revision")
    if any(len(str(value.source_artifact_digests[key])) != 64 or any(ch not in "0123456789abcdef" for ch in str(value.source_artifact_digests[key]).lower()) for key in ("pr121", "pr122")):
        raise ProductionCandidateContractError("PR artifact digests must be SHA-256 hex")
    if value.snapshot_digest is None and not any("no snapshot digest" in str(item).lower() for item in value.limitations):
        raise ProductionCandidateContractError("null snapshot_digest requires an explicit limitation")


def _digest(value: Any) -> str:
    return hashlib.sha256(json.dumps(_json_ready(value), sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")).hexdigest()


def _json_ready(value: Any) -> Any:
    if is_dataclass(value) and not isinstance(value, type):
        return _json_ready(asdict(value))
    if isinstance(value, Mapping):
        return {str(key): _json_ready(item) for key, item in sorted(value.items(), key=lambda pair: str(pair[0]))}
    if isinstance(value, (tuple, list, set, frozenset)):
        return [_json_ready(item) for item in value]
    if hasattr(value, "value"):
        return value.value
    return value
