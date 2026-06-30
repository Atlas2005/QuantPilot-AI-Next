"""Combined P34 gate pruning and fill-loop report helpers."""

from __future__ import annotations

from quantpilot_core.gate_pruning_tradability_fill_loop.contracts import (
    FillSimulationReport,
    GatePruningReport,
)
from quantpilot_core.gate_pruning_tradability_fill_loop.gate_audit import (
    audit_gate_pruning,
)
from quantpilot_core.gate_pruning_tradability_fill_loop.simulation import (
    simulate_tradability_and_fills,
)


def run_p34_gate_pruning_and_fill_loop(
    signals,
    *,
    available_cash: float,
    positions: dict[str, int],
    sellable_positions: dict[str, int],
    suspended_symbols: tuple[str, ...] = (),
    price_limits: dict[str, tuple[float, float]] | None = None,
) -> tuple[GatePruningReport, FillSimulationReport]:
    """Run the P34 pruning audit and deterministic fill simulation."""

    gate_report = audit_gate_pruning()
    fill_report = simulate_tradability_and_fills(
        signals,
        available_cash=available_cash,
        positions=positions,
        sellable_positions=sellable_positions,
        suspended_symbols=suspended_symbols,
        price_limits=price_limits,
        gate_report=gate_report,
    )
    return gate_report, fill_report
