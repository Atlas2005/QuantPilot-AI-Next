"""Local R5 mock provider probe orchestration helpers."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from quantpilot_core.mock_probe_run.contracts import (
    MockProbeRunArtifactManifest,
    MockProbeRunAuditRecord,
    MockProbeRunRejectionReason,
    MockProbeRunRequest,
    MockProbeRunResult,
    MockProbeRunStatus,
)
from quantpilot_core.provider_probe_gate import (
    ProviderProbeExecutionMode,
    ProviderProbeGateStatus,
    decide_provider_probe_gate,
    load_provider_probe_gate_request,
)
from quantpilot_core.provider_sandbox_bridge import (
    bridge_snapshot_to_fixture,
    load_provider_probe_snapshot,
)


ALLOWED_RUN_MODES = frozenset(
    {ProviderProbeExecutionMode.MOCK_ONLY, ProviderProbeExecutionMode.DRY_RUN}
)
MOCK_OUTPUT_CLASSIFICATION = "mock_fixture_only"


def load_mock_probe_run_request(path: str | Path) -> MockProbeRunRequest:
    """Load a local static R5 mock run request."""

    with Path(path).open("r", encoding="utf-8") as handle:
        raw = json.load(handle)
    if not isinstance(raw, dict):
        raise ValueError("Mock probe run request must be a JSON object.")
    return mock_probe_run_request_from_mapping(raw)


def mock_probe_run_request_from_mapping(value: dict[str, Any]) -> MockProbeRunRequest:
    """Convert a mapping into a typed mock run request."""

    manifest = value.get("artifact_manifest", {})
    if not isinstance(manifest, dict):
        manifest = {}
    artifact_manifest = MockProbeRunArtifactManifest(
        gate_request_fixture_path=str(
            manifest.get(
                "gate_request_fixture_path",
                value.get("gate_request_fixture_path", ""),
            )
        ),
        provider_probe_snapshot_fixture_path=str(
            manifest.get(
                "provider_probe_snapshot_fixture_path",
                value.get("provider_probe_snapshot_fixture_path", ""),
            )
        ),
        output_classification=str(
            manifest.get(
                "output_classification",
                value.get("output_classification", ""),
            )
        ),
        writes_production_data_assets=bool(
            manifest.get("writes_production_data_assets", False)
        ),
    )
    return MockProbeRunRequest(
        run_id=str(value.get("run_id", "")),
        provider_candidate_name=str(value.get("provider_candidate_name", "")),
        execution_mode=ProviderProbeExecutionMode(
            value.get("execution_mode", ProviderProbeExecutionMode.MOCK_ONLY.value)
        ),
        gate_request_fixture_path=str(value.get("gate_request_fixture_path", "")),
        provider_probe_snapshot_fixture_path=str(
            value.get("provider_probe_snapshot_fixture_path", "")
        ),
        expected_sandbox_bridge_compatibility=bool(
            value.get("expected_sandbox_bridge_compatibility", False)
        ),
        no_real_data=bool(value.get("no_real_data", False)),
        no_provider_api=bool(value.get("no_provider_api", False)),
        no_broker=bool(value.get("no_broker", False)),
        no_live_trading=bool(value.get("no_live_trading", False)),
        no_order_execution=bool(value.get("no_order_execution", False)),
        output_classification=str(value.get("output_classification", "")),
        artifact_manifest=artifact_manifest,
        audit_notes=str(value.get("audit_notes", "")),
    )


def run_mock_provider_probe(
    request: MockProbeRunRequest,
    repo_root: str | Path | None = None,
) -> MockProbeRunResult:
    """Run the local R4 gate -> R3 bridge mock path."""

    root = Path(repo_root) if repo_root is not None else Path.cwd()
    reasons, messages = validate_mock_probe_run_request(request)
    if reasons:
        return _result(
            request=request,
            status=MockProbeRunStatus.REJECTED,
            gate_decision_status="not_evaluated",
            bridge_result_status="not_evaluated",
            fixture_input=None,
            rejection_reasons=tuple(reasons),
            messages=tuple(messages),
            gate_allowed=False,
            bridge_accepted=False,
        )

    gate_request = load_provider_probe_gate_request(
        _resolve_local_data_path(root, request.gate_request_fixture_path)
    )
    gate_decision = decide_provider_probe_gate(gate_request)
    if gate_decision.status is not ProviderProbeGateStatus.ALLOWED:
        return _result(
            request=request,
            status=MockProbeRunStatus.REJECTED,
            gate_decision_status=gate_decision.status.value,
            bridge_result_status="not_evaluated",
            fixture_input=None,
            rejection_reasons=(MockProbeRunRejectionReason.GATE_REJECTED,),
            messages=gate_decision.messages,
            gate_allowed=False,
            bridge_accepted=False,
        )

    snapshot = load_provider_probe_snapshot(
        _resolve_local_data_path(root, request.provider_probe_snapshot_fixture_path)
    )
    bridge_result = bridge_snapshot_to_fixture(snapshot)
    if not bridge_result.accepted:
        return _result(
            request=request,
            status=MockProbeRunStatus.REJECTED,
            gate_decision_status=gate_decision.status.value,
            bridge_result_status="rejected",
            fixture_input=None,
            rejection_reasons=(MockProbeRunRejectionReason.BRIDGE_REJECTED,),
            messages=bridge_result.messages,
            gate_allowed=True,
            bridge_accepted=False,
        )

    return _result(
        request=request,
        status=MockProbeRunStatus.SUCCEEDED,
        gate_decision_status=gate_decision.status.value,
        bridge_result_status="accepted",
        fixture_input=bridge_result.fixture_input,
        rejection_reasons=(),
        messages=("Mock provider probe path completed locally.",),
        gate_allowed=True,
        bridge_accepted=True,
    )


def validate_mock_probe_run_request(
    request: MockProbeRunRequest,
) -> tuple[list[MockProbeRunRejectionReason], list[str]]:
    """Validate local R5 request constraints before loading fixtures."""

    reasons: list[MockProbeRunRejectionReason] = []
    messages: list[str] = []
    if request.execution_mode not in ALLOWED_RUN_MODES:
        _append(
            reasons,
            messages,
            MockProbeRunRejectionReason.EXECUTION_MODE_NOT_ALLOWED,
            "Execution mode must be mock_only or dry_run.",
        )
    for path_value in (
        request.gate_request_fixture_path,
        request.provider_probe_snapshot_fixture_path,
        request.artifact_manifest.gate_request_fixture_path,
        request.artifact_manifest.provider_probe_snapshot_fixture_path,
    ):
        if not _is_local_data_path(path_value):
            _append(
                reasons,
                messages,
                MockProbeRunRejectionReason.FIXTURE_PATH_NOT_LOCAL_DATA,
                "Fixture paths must be local relative paths under data/.",
            )
    if not request.expected_sandbox_bridge_compatibility:
        _append(
            reasons,
            messages,
            MockProbeRunRejectionReason.SANDBOX_BRIDGE_COMPATIBILITY_MISSING,
            "Expected sandbox bridge compatibility must be true.",
        )
    if (
        not request.no_real_data
        or not request.no_provider_api
        or not request.no_broker
        or not request.no_live_trading
        or not request.no_order_execution
    ):
        _append(
            reasons,
            messages,
            MockProbeRunRejectionReason.SAFETY_FLAG_VIOLATION,
            "All no-real-data/provider/broker/live/order flags must be true.",
        )
    if (
        request.output_classification != MOCK_OUTPUT_CLASSIFICATION
        or request.artifact_manifest.output_classification != MOCK_OUTPUT_CLASSIFICATION
        or request.artifact_manifest.writes_production_data_assets
    ):
        _append(
            reasons,
            messages,
            MockProbeRunRejectionReason.OUTPUT_CLASSIFICATION_INVALID,
            "Output classification must be mock_fixture_only and must not write production assets.",
        )
    return reasons, messages


def _result(
    request: MockProbeRunRequest,
    status: MockProbeRunStatus,
    gate_decision_status: str,
    bridge_result_status: str,
    fixture_input,
    rejection_reasons: tuple[MockProbeRunRejectionReason, ...],
    messages: tuple[str, ...],
    gate_allowed: bool,
    bridge_accepted: bool,
) -> MockProbeRunResult:
    audit = MockProbeRunAuditRecord(
        run_id=request.run_id,
        status=status,
        rejection_reasons=rejection_reasons,
        gate_allowed=gate_allowed,
        bridge_accepted=bridge_accepted,
        no_real_data=request.no_real_data,
        no_provider_api=request.no_provider_api,
        no_broker=request.no_broker,
        no_live_trading=request.no_live_trading,
        no_order_execution=request.no_order_execution,
        writes_production_data_assets=request.artifact_manifest.writes_production_data_assets,
        notes=request.audit_notes,
    )
    return MockProbeRunResult(
        run_id=request.run_id,
        status=status,
        gate_decision_status=gate_decision_status,
        sandbox_bridge_result_status=bridge_result_status,
        sandbox_fixture_input=fixture_input,
        rejection_reasons=rejection_reasons,
        messages=messages,
        audit_record=audit,
        artifact_manifest=request.artifact_manifest,
    )


def _resolve_local_data_path(root: Path, path_value: str) -> Path:
    if not _is_local_data_path(path_value):
        raise ValueError("Fixture path must be a local relative path under data/.")
    return root / path_value


def _is_local_data_path(path_value: str) -> bool:
    path = Path(path_value)
    return (
        bool(path_value)
        and not path.is_absolute()
        and ".." not in path.parts
        and len(path.parts) > 1
        and path.parts[0] == "data"
    )


def _append(
    reasons: list[MockProbeRunRejectionReason],
    messages: list[str],
    reason: MockProbeRunRejectionReason,
    message: str,
) -> None:
    if reason not in reasons:
        reasons.append(reason)
    messages.append(message)

