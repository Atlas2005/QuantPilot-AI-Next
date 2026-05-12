from pathlib import Path

from quantpilot_core.factors.candidate_library import (
    load_factor_candidates,
    summarize_factor_candidates,
    validate_factor_candidates,
)


ROOT = Path(__file__).resolve().parents[2]
CANDIDATES_PATH = ROOT / "data" / "factor_definitions" / "factor_candidates.json"


def test_factor_candidates_load_and_validate() -> None:
    candidates = load_factor_candidates(CANDIDATES_PATH)

    assert candidates
    assert validate_factor_candidates(candidates) == []


def test_factor_candidate_required_fields_and_unique_names() -> None:
    candidates = load_factor_candidates(CANDIDATES_PATH)
    required_fields = {
        "name",
        "category",
        "direction",
        "status",
        "required_fields",
        "lookback_window",
        "computation_scope",
        "evidence_status",
        "alpha_claim_allowed",
        "trading_ready",
        "known_limitations",
        "notes",
    }
    names = [candidate["name"] for candidate in candidates]

    assert len(names) == len(set(names))
    for candidate in candidates:
        assert required_fields.issubset(candidate)


def test_factor_candidates_do_not_claim_alpha_or_readiness() -> None:
    candidates = load_factor_candidates(CANDIDATES_PATH)

    for candidate in candidates:
        assert candidate["alpha_claim_allowed"] is False
        assert candidate["trading_ready"] is False
        assert candidate["status"] != "validated"


def test_summarize_factor_candidates_works() -> None:
    candidates = load_factor_candidates(CANDIDATES_PATH)
    summary = summarize_factor_candidates(candidates)

    assert summary["candidate_count"] >= 4
    assert summary["alpha_claim_allowed_count"] == 0
    assert summary["trading_ready_count"] == 0
