import importlib
from pathlib import Path

from quantpilot_core.registry import load_candidate_registry
from quantpilot_core.registry.candidate import (
    BENCHMARK_ROLES,
    CANDIDATE_TYPES,
    EVALUATION_STATUSES,
    INTEGRATION_POLICIES,
    PHASE_ALLOWED_VALUES,
    RECOMMENDED_ACTIONS,
    REQUIRED_FIELDS,
)


REPO_ROOT = Path(__file__).resolve().parents[2]
CANDIDATE_REGISTRY = REPO_ROOT / "data" / "open_source_candidates" / "candidates.json"
CONSERVATIVE_PHASE_ALLOWED = {"registry_only", "prototype_later", "deferred"}


def test_candidate_json_loads() -> None:
    candidates = load_candidate_registry(CANDIDATE_REGISTRY)

    assert candidates


def test_all_required_fields_exist() -> None:
    candidates = load_candidate_registry(CANDIDATE_REGISTRY)

    for candidate in candidates:
        for field in REQUIRED_FIELDS:
            assert getattr(candidate, field)


def test_enum_values_are_valid() -> None:
    candidates = load_candidate_registry(CANDIDATE_REGISTRY)

    for candidate in candidates:
        assert candidate.recommended_action in RECOMMENDED_ACTIONS
        assert candidate.evaluation_status in EVALUATION_STATUSES
        assert candidate.phase_allowed in PHASE_ALLOWED_VALUES
        assert candidate.candidate_type in CANDIDATE_TYPES
        assert candidate.benchmark_role in BENCHMARK_ROLES
        assert candidate.integration_policy in INTEGRATION_POLICIES


def test_candidate_names_are_unique() -> None:
    candidates = load_candidate_registry(CANDIDATE_REGISTRY)
    names = [candidate.name for candidate in candidates]

    assert len(names) == len(set(names))


def test_no_candidates_are_approved_for_adapter_in_phase_1() -> None:
    candidates = load_candidate_registry(CANDIDATE_REGISTRY)

    assert all(candidate.evaluation_status != "approved_for_adapter" for candidate in candidates)


def test_all_phase_allowed_values_are_conservative() -> None:
    candidates = load_candidate_registry(CANDIDATE_REGISTRY)

    assert all(
        candidate.phase_allowed in CONSERVATIVE_PHASE_ALLOWED
        for candidate in candidates
    )


def test_no_external_candidate_framework_imports_are_required() -> None:
    importlib.import_module("quantpilot_core.registry.candidate")
    importlib.import_module("quantpilot_core.registry.candidate_loader")
