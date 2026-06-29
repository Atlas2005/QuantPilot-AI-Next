"""Controlled Provider Probe Execution Gate.

R4 exposes safety/decision contracts and local gate helpers only. It does not
fetch market data, call provider APIs, or create provider adapters.
"""

from quantpilot_core.provider_probe_gate.contracts import (
    ProviderProbeAllowedProvider,
    ProviderProbeAuditRecord,
    ProviderProbeEvidenceRequirement,
    ProviderProbeExecutionMode,
    ProviderProbeGateDecision,
    ProviderProbeGateRejectionReason,
    ProviderProbeGateRequest,
    ProviderProbeGateStatus,
    ProviderProbeSafetyPolicy,
    ProviderProbeScope,
)
from quantpilot_core.provider_probe_gate.gate import (
    decide_provider_probe_gate,
    default_provider_probe_safety_policy,
    load_provider_probe_gate_request,
    provider_probe_gate_request_from_mapping,
    validate_provider_probe_gate_request,
)

__all__ = [
    "ProviderProbeAllowedProvider",
    "ProviderProbeAuditRecord",
    "ProviderProbeEvidenceRequirement",
    "ProviderProbeExecutionMode",
    "ProviderProbeGateDecision",
    "ProviderProbeGateRejectionReason",
    "ProviderProbeGateRequest",
    "ProviderProbeGateStatus",
    "ProviderProbeSafetyPolicy",
    "ProviderProbeScope",
    "decide_provider_probe_gate",
    "default_provider_probe_safety_policy",
    "load_provider_probe_gate_request",
    "provider_probe_gate_request_from_mapping",
    "validate_provider_probe_gate_request",
]

