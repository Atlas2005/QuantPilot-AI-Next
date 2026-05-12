"""Portfolio engine contract boundary."""

from dataclasses import dataclass, field

from quantpilot_core.contracts.base import BaseContract


@dataclass(frozen=True)
class PortfolioEngineContract(BaseContract):
    """Interface shape for future portfolio engines."""

    risk_constraints: tuple[str, ...] = field(default_factory=tuple)
    allocation_assumptions: tuple[str, ...] = field(default_factory=tuple)

    def list_risk_constraints(self) -> list[str]:
        return list(self.risk_constraints)

    def explain_allocation_assumptions(self) -> list[str]:
        return list(self.allocation_assumptions)

