"""Default inventories and deterministic R30 release checks."""

from __future__ import annotations

import importlib
from pathlib import Path

from quantpilot_core.final_readiness_release_hardening.contracts import (
    FinalReadinessInput,
    FinalReadinessRiskFlag,
    ForbiddenScopeCheck,
    ReleaseArea,
    ReleaseCheckRecord,
    ReleaseCheckStatus,
    ReleaseSeverity,
    RequiredDocumentRecord,
    RequiredModuleRecord,
)


def default_required_modules() -> tuple[RequiredModuleRecord, ...]:
    """Return the required executable-trading MVP module inventory."""

    return (
        _module("real_data_provider", ReleaseArea.DATA),
        _module("provider_fallback_selector", ReleaseArea.DATA),
        _module("paper_ledger", ReleaseArea.PAPER_LEDGER),
        _module("deepseek_multi_agent", ReleaseArea.AI_AGENT),
        _module("ai_action_paper_bridge", ReleaseArea.PAPER_LEDGER),
        _module("paper_ledger_dry_run", ReleaseArea.PAPER_LEDGER),
        _module("multi_day_paper_replay", ReleaseArea.REPLAY),
    )


def default_required_documents() -> tuple[RequiredDocumentRecord, ...]:
    """Return the required executable-trading MVP documentation inventory."""

    return (
        _document("docs/AI_ACTION_PROPOSAL_PAPER_LEDGER_BRIDGE.md", ReleaseArea.PAPER_LEDGER),
        _document("docs/PAPER_LEDGER_DRY_RUN_INTEGRATION.md", ReleaseArea.PAPER_LEDGER),
        _document("docs/MULTI_DAY_PAPER_REPLAY.md", ReleaseArea.REPLAY),
    )


def default_forbidden_scope_checks() -> tuple[ForbiddenScopeCheck, ...]:
    """Return deterministic forbidden-scope evidence checks.

    These checks evaluate caller-provided evidence strings. R30 does not perform
    repository-wide text scanning; that belongs in a future CI hardening step.
    """

    return (
        ForbiddenScopeCheck(
            name="runtime_boundary_evidence",
            forbidden_terms=(
                "place_order",
                "send_order",
                "live_trade",
                "real_broker",
                "broker_sdk",
                "qrun",
                "qlib" + ".init",
                "deepseek api call",
                "requests" + ".post",
                "requests" + ".get",
                "websocket",
                "train_live_model",
                "mutate_real_account",
            ),
            allowed_exceptions=("preflight-only", "not executed", "runtime disabled"),
            evidence_refs=("evidence://r30/no-forbidden-runtime-scope",),
        ),
    )


def validate_final_readiness_input(
    input_data: FinalReadinessInput,
) -> tuple[FinalReadinessRiskFlag, ...]:
    """Validate R30 input shape before release checks are derived."""

    flags: list[FinalReadinessRiskFlag] = []
    if not input_data.release_id.strip():
        flags.append(_critical("release_id_missing", "Release id must be non-empty."))
    if not _has_evidence(input_data.evidence_refs):
        flags.append(_critical("release_evidence_missing", "Release evidence_refs must be non-empty."))

    module_names: set[str] = set()
    for index, module in enumerate(input_data.modules):
        prefix = f"module[{index}]"
        if not module.module_name.strip():
            flags.append(_critical(f"{prefix}:module_name_missing", "Module name must be non-empty."))
        if not module.import_path.strip():
            flags.append(_critical(f"{prefix}:import_path_missing", "Module import_path must be non-empty."))
        if module.required and not _has_evidence(module.evidence_refs):
            flags.append(_critical(f"{prefix}:evidence_missing", "Required module evidence_refs must be non-empty."))
        if module.module_name in module_names:
            flags.append(_critical("duplicate_module_name", f"Duplicate module name: {module.module_name}."))
        module_names.add(module.module_name)

    document_paths: set[str] = set()
    for index, document in enumerate(input_data.documents):
        prefix = f"document[{index}]"
        if not document.document_path.strip():
            flags.append(_critical(f"{prefix}:document_path_missing", "Document path must be non-empty."))
        if document.required and not _has_evidence(document.evidence_refs):
            flags.append(_critical(f"{prefix}:evidence_missing", "Required document evidence_refs must be non-empty."))
        if document.document_path in document_paths:
            flags.append(_critical("duplicate_document_path", f"Duplicate document path: {document.document_path}."))
        document_paths.add(document.document_path)

    forbidden_names: set[str] = set()
    for index, scope_check in enumerate(input_data.forbidden_scope_checks):
        prefix = f"forbidden_scope[{index}]"
        if not scope_check.name.strip():
            flags.append(_critical(f"{prefix}:name_missing", "Forbidden scope check name must be non-empty."))
        if not _has_evidence(scope_check.evidence_refs):
            flags.append(_critical(f"{prefix}:evidence_missing", "Forbidden scope evidence_refs must be non-empty."))
        if scope_check.name in forbidden_names:
            flags.append(_critical("duplicate_forbidden_scope_check_name", f"Duplicate forbidden scope check name: {scope_check.name}."))
        forbidden_names.add(scope_check.name)
    return tuple(flags)


def build_release_checks(
    input_data: FinalReadinessInput,
    *,
    project_root: str | None = None,
) -> tuple[ReleaseCheckRecord, ...]:
    """Build module, document, and forbidden-scope release checks."""

    root = Path(project_root) if project_root is not None else Path.cwd()
    checks: list[ReleaseCheckRecord] = [
        _input_shape_check(validate_final_readiness_input(input_data), input_data.evidence_refs)
    ]
    checks.extend(_module_check(module) for module in input_data.modules)
    checks.extend(_document_check(document, root) for document in input_data.documents)
    checks.extend(_forbidden_scope_check(scope_check) for scope_check in input_data.forbidden_scope_checks)
    return tuple(checks)


def _module_check(module: RequiredModuleRecord) -> ReleaseCheckRecord:
    try:
        importlib.import_module(module.import_path)
    except ImportError:
        status = ReleaseCheckStatus.FAIL.value if module.required else ReleaseCheckStatus.WARNING.value
        reason = "required_module_missing" if module.required else "optional_module_missing"
    else:
        status = ReleaseCheckStatus.PASS.value
        reason = "passed"
    return ReleaseCheckRecord(
        name=f"module:{module.module_name}",
        area=module.area,
        status=status,
        reason=reason,
        evidence_refs=module.evidence_refs,
    )


def _document_check(
    document: RequiredDocumentRecord,
    project_root: Path,
) -> ReleaseCheckRecord:
    exists = (project_root / document.document_path).exists()
    if exists:
        status = ReleaseCheckStatus.PASS.value
        reason = "passed"
    else:
        status = ReleaseCheckStatus.FAIL.value if document.required else ReleaseCheckStatus.WARNING.value
        reason = "required_document_missing" if document.required else "optional_document_missing"
    return ReleaseCheckRecord(
        name=f"document:{document.document_path}",
        area=document.area,
        status=status,
        reason=reason,
        evidence_refs=document.evidence_refs,
    )


def _forbidden_scope_check(scope_check: ForbiddenScopeCheck) -> ReleaseCheckRecord:
    evidence_text = "\n".join(scope_check.evidence_refs).lower()
    exceptions = tuple(exception.lower() for exception in scope_check.allowed_exceptions)
    violations = tuple(
        term
        for term in scope_check.forbidden_terms
        if term.lower() in evidence_text
        and not any(exception in evidence_text for exception in exceptions)
    )
    status = ReleaseCheckStatus.FAIL.value if violations else ReleaseCheckStatus.PASS.value
    reason = "forbidden_scope_detected:" + ",".join(violations) if violations else "passed"
    return ReleaseCheckRecord(
        name=f"forbidden_scope:{scope_check.name}",
        area=ReleaseArea.SAFETY.value,
        status=status,
        reason=reason,
        evidence_refs=scope_check.evidence_refs,
    )


def _input_shape_check(
    risk_flags: tuple[FinalReadinessRiskFlag, ...],
    evidence_refs: tuple[str, ...],
) -> ReleaseCheckRecord:
    status = ReleaseCheckStatus.FAIL.value if risk_flags else ReleaseCheckStatus.PASS.value
    reason = ";".join(flag.code for flag in risk_flags) if risk_flags else "passed"
    return ReleaseCheckRecord(
        name="input_shape",
        area=ReleaseArea.SAFETY.value,
        status=status,
        reason=reason,
        evidence_refs=evidence_refs,
    )


def _module(module_name: str, area: ReleaseArea) -> RequiredModuleRecord:
    return RequiredModuleRecord(
        module_name=f"quantpilot_core.{module_name}",
        area=area.value,
        required=True,
        import_path=f"quantpilot_core.{module_name}",
        evidence_refs=(f"evidence://module/{module_name}",),
    )


def _document(document_path: str, area: ReleaseArea) -> RequiredDocumentRecord:
    return RequiredDocumentRecord(
        document_path=document_path,
        area=area.value,
        required=True,
        evidence_refs=(f"evidence://document/{document_path}",),
    )


def _has_evidence(evidence_refs: tuple[str, ...]) -> bool:
    return any(ref.strip() for ref in evidence_refs)


def _critical(code: str, message: str) -> FinalReadinessRiskFlag:
    return FinalReadinessRiskFlag(
        code=code,
        severity=ReleaseSeverity.CRITICAL.value,
        message=message,
    )
