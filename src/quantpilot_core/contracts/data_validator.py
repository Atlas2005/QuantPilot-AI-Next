"""Data validator contract boundary."""

from dataclasses import dataclass, field

from quantpilot_core.contracts.base import BaseContract


@dataclass(frozen=True)
class DataValidatorContract(BaseContract):
    """Interface shape for future dataset validation."""

    validation_rules: tuple[str, ...] = field(default_factory=tuple)
    failure_policy: tuple[str, ...] = field(default_factory=tuple)

    def list_validation_rules(self) -> list[str]:
        return list(self.validation_rules)

    def explain_failure_policy(self) -> list[str]:
        return list(self.failure_policy)

