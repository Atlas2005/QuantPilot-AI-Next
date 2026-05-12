"""Backtest engine contract boundary."""

from dataclasses import dataclass, field

from quantpilot_core.contracts.base import BaseContract


@dataclass(frozen=True)
class BacktestEngineContract(BaseContract):
    """Interface shape for future backtest engine adapters."""

    engine_assumptions: tuple[str, ...] = field(default_factory=tuple)
    execution_model_notes: tuple[str, ...] = field(default_factory=tuple)

    def list_engine_assumptions(self) -> list[str]:
        return list(self.engine_assumptions)

    def explain_execution_model(self) -> list[str]:
        return list(self.execution_model_notes)

