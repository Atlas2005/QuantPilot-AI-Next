"""Bridge real provider daily bars into the small-sample data gate."""

from quantpilot_core.real_provider_gate_bridge.bridge import (
    RealProviderGateBridgeError,
    RealProviderSmallSampleGateResult,
    SmallSampleGateBridgeMetadata,
    validate_provider_bars_with_small_sample_gate,
)

__all__ = [
    "RealProviderGateBridgeError",
    "RealProviderSmallSampleGateResult",
    "SmallSampleGateBridgeMetadata",
    "validate_provider_bars_with_small_sample_gate",
]
