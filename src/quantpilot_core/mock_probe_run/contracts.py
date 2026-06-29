"""Contracts for the R5 controlled mock provider probe run."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from quantpilot_core.provider_probe_gate.contracts import ProviderProbeExecutionMode
from quantpilot_core.provider_sandbox_bridge.contracts import SandboxFixtureInput


class MockProbeRunStatus(str, Enum):
    SUCCEEDED = "succeeded"
    REJECTED = "rejected"


class MockProbeRunRejectionReason(str, Enum):
    NONE = "none"
    EXECUTION_MODE_NOT_ALLOWED = "execution_mode_not_allowed"
    FIXTURE_PATH_NOT_LOCAL_DATA = "fixture_path_not_local_data"
    SAFETY_FLAG_VIOLATION = "safety_flag_violation"
    OUTPUT_CLASSIFICATION_INVALID = "output_classification_invalid"
    SANDBOX_BRIDGE_COMPATIBILITY_MISSING = "sandbox_bridge_compatibility_missing"
    GATE_REJECTED = "gate_rejected"
    BRIDGE_REJECTED = "bridge_rejected"


@dataclass(frozen=True)
class MockProbeRunArtifactManifest:
    """Local artifact references for a mock-only run."""

    gate_request_fixture_path: str
    provider_probe_snapshot_fixture_path: str
    output_classification: str
    writes_production_data_assets: bool


@dataclass(frozen=True)
class MockProbeRunRequest:
    """Request for a local mock-only provider probe path."""

    run_id: str
    provider_candidate_name: str
    execution_mode: ProviderProbeExecutionMode
    gate_request_fixture_path: str
    provider_probe_snapshot_fixture_path: str
    expected_sandbox_bridge_compatibility: bool
    no_real_data: bool
    no_provider_api: bool
    no_broker: bool
    no_live_trading: bool
    no_order_execution: bool
    output_classification: str
    artifact_manifest: MockProbeRunArtifactManifest
    audit_notes: str


@dataclass(frozen=True)
class MockProbeRunAuditRecord:
    """Audit record for the local R5 mock run."""

    run_id: str
    status: MockProbeRunStatus
    rejection_reasons: tuple[MockProbeRunRejectionReason, ...]
    gate_allowed: bool
    bridge_accepted: bool
    no_real_data: bool
    no_provider_api: bool
    no_broker: bool
    no_live_trading: bool
    no_order_execution: bool
    writes_production_data_assets: bool
    notes: str


@dataclass(frozen=True)
class MockProbeRunResult:
    """Result for a local mock gate-to-bridge run."""

    run_id: str
    status: MockProbeRunStatus
    gate_decision_status: str
    sandbox_bridge_result_status: str
    sandbox_fixture_input: SandboxFixtureInput | None
    rejection_reasons: tuple[MockProbeRunRejectionReason, ...]
    messages: tuple[str, ...]
    audit_record: MockProbeRunAuditRecord
    artifact_manifest: MockProbeRunArtifactManifest

