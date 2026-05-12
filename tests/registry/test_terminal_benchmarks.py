from pathlib import Path

from quantpilot_core.registry import load_candidate_registry


REPO_ROOT = Path(__file__).resolve().parents[2]
CANDIDATE_REGISTRY = REPO_ROOT / "data" / "open_source_candidates" / "candidates.json"
CONSERVATIVE_PHASE_ALLOWED = {"registry_only", "prototype_later", "deferred"}


def candidates_by_name() -> dict[str, object]:
    return {
        candidate.name: candidate
        for candidate in load_candidate_registry(CANDIDATE_REGISTRY)
    }


def test_new_terminal_candidate_types_are_valid() -> None:
    candidates = load_candidate_registry(CANDIDATE_REGISTRY)
    candidate_types = {candidate.candidate_type for candidate in candidates}

    assert "professional_terminal_benchmark" in candidate_types
    assert "open_source_terminal_candidate" in candidate_types


def test_bloomberg_terminal_is_reference_only() -> None:
    bloomberg = candidates_by_name()["Bloomberg Terminal"]

    assert bloomberg.candidate_type == "professional_terminal_benchmark"
    assert bloomberg.recommended_action == "borrow_architecture_only"
    assert bloomberg.phase_allowed == "registry_only"
    assert bloomberg.integration_policy == "no_integration_reference_only"
    assert bloomberg.evaluation_status != "approved_for_adapter"
    assert "Proprietary commercial benchmark only" in bloomberg.notes


def test_fincept_terminal_requires_license_review() -> None:
    fincept = candidates_by_name()["FinceptTerminal"]

    assert fincept.candidate_type == "open_source_terminal_candidate"
    assert fincept.phase_allowed == "registry_only"
    assert fincept.integration_policy == "license_review_required"
    assert fincept.commercial_risk == "high"
    assert fincept.license_review_status == "required_before_any_use"
    assert "Do not clone, copy, integrate, or commercialize" in fincept.notes


def test_no_professional_terminal_benchmark_is_approved_for_adapter() -> None:
    candidates = load_candidate_registry(CANDIDATE_REGISTRY)
    professional_terminals = [
        candidate
        for candidate in candidates
        if candidate.candidate_type == "professional_terminal_benchmark"
    ]

    assert professional_terminals
    assert all(
        candidate.evaluation_status != "approved_for_adapter"
        for candidate in professional_terminals
    )


def test_phase_allowed_values_remain_conservative_for_phase_1_1() -> None:
    candidates = load_candidate_registry(CANDIDATE_REGISTRY)

    assert all(
        candidate.phase_allowed in CONSERVATIVE_PHASE_ALLOWED
        for candidate in candidates
    )


def test_candidates_load_with_standard_library_loader_only() -> None:
    candidates = load_candidate_registry(CANDIDATE_REGISTRY)

    assert "OpenBB Platform / OpenBB Terminal" in {
        candidate.name for candidate in candidates
    }
