"""Factor engine contract boundary."""

from dataclasses import dataclass, field

from quantpilot_core.contracts.base import BaseContract


@dataclass(frozen=True)
class FactorEngineContract(BaseContract):
    """Interface shape for future factor engines."""

    factor_inputs: tuple[str, ...] = field(default_factory=tuple)
    factor_limitations: tuple[str, ...] = field(default_factory=tuple)

    def list_factor_inputs(self) -> list[str]:
        return list(self.factor_inputs)

    def explain_factor_limitations(self) -> list[str]:
        return list(self.factor_limitations)

