from pathlib import Path

from quantpilot_core.factors.external_analytics_preflight import (
    load_external_analytics_preflight,
    summarize_external_analytics_preflight,
    validate_external_analytics_preflight,
)


ROOT = Path(__file__).resolve().parents[2]
PREFLIGHT_PATH = ROOT / "data" / "factor_validation" / "external_analytics_preflight.json"


def test_external_analytics_preflight_loads_and_validates() -> None:
    candidates = load_external_analytics_preflight(PREFLIGHT_PATH)

    assert candidates
    assert validate_external_analytics_preflight(candidates) == []


def test_required_external_analytics_candidates_exist() -> None:
    candidates = load_external_analytics_preflight(PREFLIGHT_PATH)
    names = {candidate["name"] for candidate in candidates}

    assert "Alphalens" in names
    assert "Alphalens Reloaded" in names
    assert "quantstats" in names
    assert "quantstats-reloaded" in names
    assert "empyrical" in names
    assert "empyrical-reloaded" in names
    assert "Qlib" in names


def test_external_analytics_candidates_remain_unapproved() -> None:
    candidates = load_external_analytics_preflight(PREFLIGHT_PATH)
    required_fields = {
        "name",
        "candidate_type",
        "integration_policy",
        "license_risk",
        "dependency_risk",
        "data_shape_risk",
        "a_share_fit_risk",
        "runtime_risk",
        "requires_real_data",
        "requires_pandas_like_input",
        "approved_for_install",
        "approved_for_adapter",
        "alpha_claim_allowed",
        "trading_ready",
        "notes",
    }

    for candidate in candidates:
        assert required_fields.issubset(candidate)
        assert candidate["approved_for_install"] is False
        assert candidate["approved_for_adapter"] is False
        assert candidate["alpha_claim_allowed"] is False
        assert candidate["trading_ready"] is False


def test_qlib_is_not_ready_for_adapter_or_install() -> None:
    candidates = load_external_analytics_preflight(PREFLIGHT_PATH)
    qlib = next(candidate for candidate in candidates if candidate["name"] == "Qlib")

    assert qlib["integration_policy"] != "adapter_later"
    assert qlib["approved_for_install"] is False
    assert qlib["approved_for_adapter"] is False


def test_summarize_external_analytics_preflight_works() -> None:
    candidates = load_external_analytics_preflight(PREFLIGHT_PATH)
    summary = summarize_external_analytics_preflight(candidates)

    assert summary["candidate_count"] == 7
    assert summary["approved_for_install_count"] == 0
    assert summary["approved_for_adapter_count"] == 0
    assert summary["alpha_claim_allowed_count"] == 0
    assert summary["trading_ready_count"] == 0
