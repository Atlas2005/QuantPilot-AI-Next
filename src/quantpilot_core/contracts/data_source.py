"""Data source contract boundary."""

from dataclasses import dataclass, field

from quantpilot_core.contracts.base import BaseContract


@dataclass(frozen=True)
class DataSourceContract(BaseContract):
    """Interface shape for future data-source adapters.

    This contract does not fetch market data or define provider adapters.
    """

    supported_assets: tuple[str, ...] = field(default_factory=tuple)
    required_fields: tuple[str, ...] = field(default_factory=tuple)
    data_limitations: tuple[str, ...] = field(default_factory=tuple)

    def list_supported_assets(self) -> list[str]:
        return list(self.supported_assets)

    def list_required_fields(self) -> list[str]:
        return list(self.required_fields)

    def explain_data_limitations(self) -> list[str]:
        return list(self.data_limitations)

