"""Bounded, advisory-only active shadow. It cannot affect production execution."""
from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, is_dataclass
from pathlib import Path
from typing import Any, Mapping

from quantpilot_core.quant_firm.deepseek_advisory import DeepSeekAdvisoryAgent, DeepSeekAdvisoryInput, DeepSeekAdvisoryRole, DeepSeekClientConfig
from .store import payload_digest


@dataclass(frozen=True)
class ActiveShadowConfig:
    enabled: bool = False
    enable_live_calls: bool = False
    max_physical_model_calls_per_cycle: int = 0
    max_estimated_cost_per_cycle: float = 0.0
    estimated_cost_per_call: float = 0.0
    cache_path: str | Path = ".cache/quantpilot/active_shadow"
    allow_roles: tuple[DeepSeekAdvisoryRole, ...] = tuple(DeepSeekAdvisoryRole)
    timeout: float = 30.0
    failure_policy: str = "abstain"

    def __post_init__(self) -> None:
        if self.failure_policy != "abstain":
            raise ValueError("active shadow supports only failure_policy='abstain'")
        if self.timeout <= 0:
            raise ValueError("timeout must be positive")
        if self.enable_live_calls and (self.max_physical_model_calls_per_cycle <= 0 or self.max_estimated_cost_per_cycle <= 0 or self.estimated_cost_per_call <= 0):
            raise ValueError("live active shadow requires positive call, cycle-cost, and per-call cost limits")


class ActiveShadowRunner:
    def __init__(self, config: ActiveShadowConfig, *, agent: Any | None = None) -> None:
        self.config = config
        self.agent = agent or DeepSeekAdvisoryAgent(DeepSeekClientConfig(timeout_seconds=config.timeout, enable_live_call=config.enable_live_calls))

    def run(self, evidence: Mapping[str, Any]) -> Mapping[str, Any]:
        evidence_digest = payload_digest(evidence)
        result: dict[str, Any] = {"mode": "disabled", "evidence_digest": evidence_digest, "physical_model_calls": 0, "cache_hits": 0, "estimated_api_cost": 0.0, "cost_is_estimated": True, "input_tokens": 0, "output_tokens": 0, "abstentions": 0, "roles": {}}
        if not self.config.enabled:
            return result
        result["mode"] = "active_shadow"
        root = Path(self.config.cache_path)
        root.mkdir(parents=True, exist_ok=True)
        roles = tuple(role for role in self.config.allow_roles if role is not DeepSeekAdvisoryRole.INVESTMENT_COMMITTEE)
        if DeepSeekAdvisoryRole.INVESTMENT_COMMITTEE in self.config.allow_roles:
            roles += (DeepSeekAdvisoryRole.INVESTMENT_COMMITTEE,)
        for role in roles:
            key = payload_digest({"role": role.value, "pit_evidence_digest": evidence_digest, "model": self._model_name(), "policy": "quant_firm_approved_v1"})
            cached = self._read_cache(root / f"{key}.json", key)
            if cached is not None:
                result["roles"][role.value] = cached
                result["cache_hits"] += 1
                continue
            if not self.config.enable_live_calls:
                self._abstain(result, role, "live_calls_disabled")
                continue
            if result["physical_model_calls"] >= self.config.max_physical_model_calls_per_cycle:
                self._abstain(result, role, "call_budget_exhausted")
                continue
            if result["estimated_api_cost"] + self.config.estimated_cost_per_call > self.config.max_estimated_cost_per_cycle:
                self._abstain(result, role, "cost_budget_exhausted")
                continue
            # This count occurs before the physical request, including provider failures.
            result["physical_model_calls"] += 1
            result["estimated_api_cost"] += self.config.estimated_cost_per_call
            try:
                role_evidence: Mapping[str, Any] = evidence
                if role is DeepSeekAdvisoryRole.INVESTMENT_COMMITTEE:
                    specialist_digests = tuple(
                        payload_digest(payload)
                        for specialist, payload in result["roles"].items()
                        if specialist != role.value and isinstance(payload, Mapping) and payload.get("status") != "abstain"
                    )
                    role_evidence = {**evidence, "specialist_evidence_digests": specialist_digests}
                output = self.agent.advise(DeepSeekAdvisoryInput(role=role, quant_firm_decision_report_summary=role_evidence, learning_desk_output=evidence.get("learning_desk"), run_label=str(evidence.get("session_id", ""))))
                payload = _json(output)
                if getattr(output, "is_fallback", False) or not isinstance(payload, Mapping):
                    raise ValueError("invalid advisory output")
                result["input_tokens"] += int(payload.get("input_tokens", 0) or 0)
                result["output_tokens"] += int(payload.get("output_tokens", 0) or 0)
                self._write_cache(root / f"{key}.json", {"cache_key": key, "payload_digest": payload_digest(payload), "payload": payload})
                result["roles"][role.value] = payload
            except Exception as exc:
                self._abstain(result, role, f"provider_or_validation_failure:{type(exc).__name__}")
        return result

    def _model_name(self) -> str:
        return str(getattr(getattr(self.agent, "config", None), "model", "approved-default"))

    @staticmethod
    def _abstain(result: dict[str, Any], role: DeepSeekAdvisoryRole, reason: str) -> None:
        result["roles"][role.value] = {"status": "abstain", "reason": reason}
        result["abstentions"] += 1

    @staticmethod
    def _read_cache(path: Path, expected_key: str) -> Mapping[str, Any] | None:
        try:
            item = json.loads(path.read_text(encoding="utf-8"))
            payload = item["payload"]
            if item.get("cache_key") != expected_key or item.get("payload_digest") != payload_digest(payload) or not isinstance(payload, Mapping):
                return None
            return payload
        except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError):
            return None

    @staticmethod
    def _write_cache(path: Path, value: Mapping[str, Any]) -> None:
        temporary = path.with_suffix(".tmp")
        with temporary.open("w", encoding="utf-8") as handle:
            json.dump(value, handle, sort_keys=True)
            handle.flush(); os.fsync(handle.fileno())
        os.replace(temporary, path)


def _json(value: Any) -> Any:
    if is_dataclass(value) and not isinstance(value, type): return _json(asdict(value))
    if isinstance(value, Mapping): return {str(k): _json(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)): return [_json(v) for v in value]
    return getattr(value, "value", value)
