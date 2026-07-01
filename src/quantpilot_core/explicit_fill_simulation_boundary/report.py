"""Report helper for explicit fill simulation boundary."""

from __future__ import annotations

from quantpilot_core.explicit_fill_simulation_boundary.contracts import (
    FillSimulationRequest,
    FillSimulationResult,
)
from quantpilot_core.explicit_fill_simulation_boundary.simulation import (
    simulate_fill_boundary,
)


def build_fill_simulation_report(request: FillSimulationRequest) -> FillSimulationResult:
    """Build a deterministic fill simulation report."""

    return simulate_fill_boundary(request)
