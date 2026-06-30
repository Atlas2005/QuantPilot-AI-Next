from __future__ import annotations

from dataclasses import replace

from quantpilot_core.final_readiness_release_hardening import (
    FinalReadinessDecision,
    FinalReadinessInput,
    ForbiddenScopeCheck,
    ReleaseArea,
    ReleaseCheckStatus,
    RequiredDocumentRecord,
    RequiredModuleRecord,
    build_release_checks,
    default_forbidden_scope_checks,
    default_required_documents,
    default_required_modules,
    run_final_readiness_release_hardening,
    validate_final_readiness_input,
)


def module(
    name: str = "quantpilot_core.paper_ledger",
    *,
    required: bool = True,
    import_path: str | None = None,
    evidence_refs: tuple[str, ...] = ("evidence://module",),
) -> RequiredModuleRecord:
    return RequiredModuleRecord(
        module_name=name,
        area=ReleaseArea.PAPER_LEDGER.value,
        required=required,
        import_path=import_path or name,
        evidence_refs=evidence_refs,
    )


def document(
    path: str = "docs/PAPER_LEDGER_DRY_RUN_INTEGRATION.md",
    *,
    required: bool = True,
    evidence_refs: tuple[str, ...] = ("evidence://document",),
) -> RequiredDocumentRecord:
    return RequiredDocumentRecord(
        document_path=path,
        area=ReleaseArea.DOCS.value,
        required=required,
        evidence_refs=evidence_refs,
    )


def forbidden_check(
    name: str = "scope",
    *,
    evidence_refs: tuple[str, ...] = ("evidence://safe-preflight-only",),
    forbidden_terms: tuple[str, ...] = ("place_order",),
    allowed_exceptions: tuple[str, ...] = (),
) -> ForbiddenScopeCheck:
    return ForbiddenScopeCheck(
        name=name,
        forbidden_terms=forbidden_terms,
        allowed_exceptions=allowed_exceptions,
        evidence_refs=evidence_refs,
    )


def final_input(**overrides) -> FinalReadinessInput:
    values = {
        "release_id": "r30",
        "modules": (module(),),
        "documents": (document(),),
        "forbidden_scope_checks": (forbidden_check(),),
        "evidence_refs": ("evidence://release",),
    }
    values.update(overrides)
    return FinalReadinessInput(**values)


def codes(report) -> set[str]:
    return {flag.code for flag in report.risk_flags}


def test_default_final_readiness_returns_ready_when_inventory_exists() -> None:
    report = run_final_readiness_release_hardening(project_root=".")

    assert report.ok is True
    assert report.decision == FinalReadinessDecision.READY.value
    assert report.failed_checks == ()
    assert report.warning_checks == ()


def test_missing_release_id_is_rejected() -> None:
    report = run_final_readiness_release_hardening(final_input(release_id=""), project_root=".")

    assert report.decision == FinalReadinessDecision.BLOCKED.value
    assert "release_id_missing" in codes(report)
    assert "input_shape" in report.failed_checks


def test_missing_input_evidence_refs_is_rejected() -> None:
    flags = validate_final_readiness_input(final_input(evidence_refs=()))

    assert any(flag.code == "release_evidence_missing" for flag in flags)


def test_duplicate_module_name_rejected() -> None:
    duplicate = module()

    report = run_final_readiness_release_hardening(
        final_input(modules=(duplicate, duplicate)),
        project_root=".",
    )

    assert report.decision == FinalReadinessDecision.BLOCKED.value
    assert "duplicate_module_name" in codes(report)


def test_duplicate_document_path_rejected() -> None:
    duplicate = document()

    report = run_final_readiness_release_hardening(
        final_input(documents=(duplicate, duplicate)),
        project_root=".",
    )

    assert report.decision == FinalReadinessDecision.BLOCKED.value
    assert "duplicate_document_path" in codes(report)


def test_duplicate_forbidden_check_name_rejected() -> None:
    duplicate = forbidden_check()

    report = run_final_readiness_release_hardening(
        final_input(forbidden_scope_checks=(duplicate, duplicate)),
        project_root=".",
    )

    assert report.decision == FinalReadinessDecision.BLOCKED.value
    assert "duplicate_forbidden_scope_check_name" in codes(report)


def test_missing_required_module_creates_fail() -> None:
    missing = module(
        "quantpilot_core.missing_release_module",
        import_path="quantpilot_core.missing_release_module",
    )

    report = run_final_readiness_release_hardening(
        final_input(modules=(missing,)),
        project_root=".",
    )

    assert report.decision == FinalReadinessDecision.BLOCKED.value
    assert report.failed_checks == ("module:quantpilot_core.missing_release_module",)


def test_missing_required_document_creates_fail(tmp_path) -> None:
    missing = document("docs/DOES_NOT_EXIST.md")

    report = run_final_readiness_release_hardening(
        final_input(documents=(missing,)),
        project_root=str(tmp_path),
    )

    assert report.decision == FinalReadinessDecision.BLOCKED.value
    assert report.failed_checks == ("document:docs/DOES_NOT_EXIST.md",)


def test_forbidden_scope_evidence_creates_fail() -> None:
    scope = forbidden_check(evidence_refs=("release evidence mentions place_order",))

    report = run_final_readiness_release_hardening(
        final_input(forbidden_scope_checks=(scope,)),
        project_root=".",
    )

    assert report.decision == FinalReadinessDecision.BLOCKED.value
    assert report.failed_checks == ("forbidden_scope:scope",)


def test_warning_without_fail_returns_manual_review() -> None:
    optional_missing = module(
        "quantpilot_core.optional_missing_release_module",
        required=False,
        import_path="quantpilot_core.optional_missing_release_module",
    )

    report = run_final_readiness_release_hardening(
        final_input(modules=(optional_missing,)),
        project_root=".",
    )

    assert report.decision == FinalReadinessDecision.MANUAL_REVIEW.value
    assert report.warning_checks == ("module:quantpilot_core.optional_missing_release_module",)
    assert report.failed_checks == ()


def test_fail_check_returns_blocked() -> None:
    missing = document("docs/MISSING_R30_DOC.md")

    report = run_final_readiness_release_hardening(
        final_input(documents=(missing,)),
        project_root=".",
    )

    assert report.ok is False
    assert report.decision == FinalReadinessDecision.BLOCKED.value


def test_ok_true_only_when_ready() -> None:
    ready = run_final_readiness_release_hardening(final_input(), project_root=".")
    blocked = run_final_readiness_release_hardening(
        final_input(modules=(module("quantpilot_core.missing", import_path="quantpilot_core.missing"),)),
        project_root=".",
    )

    assert ready.ok is True
    assert ready.decision == FinalReadinessDecision.READY.value
    assert blocked.ok is False
    assert blocked.decision != FinalReadinessDecision.READY.value


def test_deterministic_passed_warning_failed_check_lists() -> None:
    optional_missing = module(
        "quantpilot_core.optional_missing_release_module",
        required=False,
        import_path="quantpilot_core.optional_missing_release_module",
    )
    missing_doc = document("docs/MISSING_R30_DOC.md")
    input_data = final_input(
        modules=(module(), optional_missing),
        documents=(document(), missing_doc),
    )

    report = run_final_readiness_release_hardening(input_data, project_root=".")

    assert report.passed_checks[:3] == (
        "input_shape",
        "module:quantpilot_core.paper_ledger",
        "document:docs/PAPER_LEDGER_DRY_RUN_INTEGRATION.md",
    )
    assert report.warning_checks == ("module:quantpilot_core.optional_missing_release_module",)
    assert report.failed_checks == ("document:docs/MISSING_R30_DOC.md",)


def test_no_mutation_of_input_data() -> None:
    input_data = final_input()
    before = replace(input_data)

    run_final_readiness_release_hardening(input_data, project_root=".")
    build_release_checks(input_data, project_root=".")

    assert input_data == before


def test_default_inventories_cover_required_r30_surface() -> None:
    modules = {record.import_path for record in default_required_modules()}
    documents = {record.document_path for record in default_required_documents()}
    forbidden = default_forbidden_scope_checks()

    assert "quantpilot_core.qlib_evaluation_preflight" in modules
    assert "quantpilot_core.stats_agent_factor_metrics_preflight" in modules
    assert "docs/QLIB_EVALUATION_PREFLIGHT.md" in documents
    assert forbidden and forbidden[0].forbidden_terms
