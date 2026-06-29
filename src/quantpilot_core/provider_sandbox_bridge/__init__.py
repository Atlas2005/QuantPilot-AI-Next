"""Provider-Sandbox Fixture Bridge.

R3 exposes fixture/probe bridge contracts and local transformation helpers only.
External data provider projects remain adapter candidates.
"""

from quantpilot_core.provider_sandbox_bridge.bridge import (
    bridge_snapshot_to_fixture,
    load_provider_probe_snapshot,
    provider_probe_snapshot_from_mapping,
    validate_provider_probe_snapshot,
)
from quantpilot_core.provider_sandbox_bridge.contracts import (
    ProviderDataQualitySignal,
    ProviderFailureSignal,
    ProviderLatencySignal,
    ProviderProbeSnapshot,
    ProviderProbeStatus,
    ProviderSandboxAdapterBoundary,
    ProviderSandboxBridgeRejectionReason,
    ProviderSandboxBridgeResult,
    SandboxFixtureInput,
)

__all__ = [
    "ProviderDataQualitySignal",
    "ProviderFailureSignal",
    "ProviderLatencySignal",
    "ProviderProbeSnapshot",
    "ProviderProbeStatus",
    "ProviderSandboxAdapterBoundary",
    "ProviderSandboxBridgeRejectionReason",
    "ProviderSandboxBridgeResult",
    "SandboxFixtureInput",
    "bridge_snapshot_to_fixture",
    "load_provider_probe_snapshot",
    "provider_probe_snapshot_from_mapping",
    "validate_provider_probe_snapshot",
]
