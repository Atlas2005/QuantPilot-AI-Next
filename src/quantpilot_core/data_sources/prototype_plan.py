"""Manual-only prototype planning structures for future data-source reviews."""

from dataclasses import dataclass
from enum import Enum


class DataSourceCandidateType(str, Enum):
    PUBLIC_PYTHON_LIBRARY = "public_python_library"
    COMMERCIAL_VENDOR = "commercial_vendor"
    PROFESSIONAL_TERMINAL = "professional_terminal"
    OPEN_SOURCE_DATA_PIPELINE = "open_source_data_pipeline"
    INTERNAL_FIXTURE = "internal_fixture"
    UNKNOWN = "unknown"


class PrototypeRunMode(str, Enum):
    REGISTRY_ONLY = "registry_only"
    MANUAL_ONLY = "manual_only"
    DISABLED_IN_CI = "disabled_in_ci"
    FUTURE_ADAPTER = "future_adapter"
    AVOID_FOR_NOW = "avoid_for_now"


@dataclass(frozen=True)
class DataSourcePrototypePlan:
    """Plan metadata for a future manual data-source prototype.

    This is not a data-source adapter and cannot fetch data.
    """

    name: str
    candidate_type: DataSourceCandidateType
    run_mode: PrototypeRunMode
    requires_network: bool
    requires_token: bool
    requires_license_review: bool
    allowed_in_ci: bool
    target_asset_scope: str
    expected_output_contract: str
    notes: str

    def __post_init__(self) -> None:
        if self.allowed_in_ci and self.candidate_type is not DataSourceCandidateType.INTERNAL_FIXTURE:
            raise ValueError("External data-source prototype plans must not be allowed in CI.")

