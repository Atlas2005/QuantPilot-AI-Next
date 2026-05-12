"""Base contract boundary for Phase 2."""

from abc import ABC
from dataclasses import dataclass, field

from quantpilot_core.contracts.types import ContractMetadata


@dataclass(frozen=True)
class BaseContract(ABC):
    """Minimal non-operational base for contract definitions."""

    metadata: ContractMetadata
    scope_warnings: tuple[str, ...] = field(default_factory=tuple)

    def describe(self) -> dict[str, object]:
        """Return a serializable description of this contract boundary."""

        return {
            "metadata": self.metadata.as_dict(),
            "scope_warnings": list(self.scope_warnings),
            "trading_ready": False,
        }

    def validate_scope(self) -> list[str]:
        """Return scope warnings without performing business logic."""

        return list(self.scope_warnings)

