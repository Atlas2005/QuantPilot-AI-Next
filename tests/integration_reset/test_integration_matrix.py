from pathlib import Path

from quantpilot_core.integration_reset import (
    load_integration_matrix,
    summarize_by_category,
    summarize_by_proposed_action,
)


ROOT = Path(__file__).resolve().parents[2]
MATRIX_PATH = ROOT / "data" / "integration_reset" / "r1_integration_replacement_matrix.json"
R1_DOCS = [
    ROOT / "docs" / "PROFIT_FIRST_INTEGRATION_ARCHITECTURE.md",
    ROOT / "docs" / "MULTI_AGENT_TARGET_ARCHITECTURE.md",
    ROOT / "docs" / "MARKET_REALITY_SANDBOX_ARCHITECTURE.md",
    ROOT / "docs" / "CAPITAL_AWARE_FAST_COMPOUNDING_MODE.md",
    ROOT / "docs" / "OPEN_SOURCE_REPLACEMENT_STRATEGY.md",
    ROOT / "docs" / "UPSTREAM_DEPENDENCY_INTELLIGENCE_LAYER.md",
    ROOT / "docs" / "THIRTY_DAY_CAPITAL_TEST_MVP_PLAN.md",
]


def test_matrix_loads() -> None:
    candidates = load_integration_matrix(MATRIX_PATH)

    assert candidates
    assert summarize_by_proposed_action(candidates)
    assert summarize_by_category(candidates)


def test_required_candidates_exist() -> None:
    candidates = load_integration_matrix(MATRIX_PATH)
    names = {candidate.name for candidate in candidates}
    required = {
        "AkShare",
        "Baostock",
        "Tushare",
        "SimTradeData",
        "Hikyuu",
        "RQAlpha",
        "vectorbt",
        "Backtrader",
        "Pandera",
        "Great Expectations",
        "Alphalens Reloaded",
        "empyrical / empyrical-reloaded",
        "quantstats / quantstats-reloaded",
        "Qlib",
        "LangGraph",
        "OpenAI Agents SDK",
        "CrewAI",
        "AutoGen",
        "vn.py / VeighNa",
    }

    assert required.issubset(names)


def test_r1_safety_fields_are_false() -> None:
    candidates = load_integration_matrix(MATRIX_PATH)

    assert all(candidate.install_allowed_in_r1 is False for candidate in candidates)
    assert all(candidate.live_trading_allowed_in_r1 is False for candidate in candidates)
    assert all(candidate.broker_connection_allowed_in_r1 is False for candidate in candidates)
    assert all(candidate.raw_data_fetch_allowed_in_r1 is False for candidate in candidates)


def test_every_candidate_requires_update_policy() -> None:
    candidates = load_integration_matrix(MATRIX_PATH)

    assert all(candidate.update_policy_required is True for candidate in candidates)


def test_capital_test_mvp_has_high_relevance_candidate() -> None:
    candidates = load_integration_matrix(MATRIX_PATH)

    assert any(
        candidate.capital_test_mvp_relevance == "high" for candidate in candidates
    )


def test_market_reality_sandbox_is_represented() -> None:
    combined_text = _r1_text()

    assert "Market Reality Sandbox" in combined_text
    assert "T+1" in combined_text
    assert "partial fills" in combined_text


def test_capital_aware_fast_compounding_mode_is_represented() -> None:
    combined_text = _r1_text()

    assert "Capital-Aware Fast Compounding Mode" in combined_text
    assert "current funds" in combined_text
    assert "minimum lot size" in combined_text


def test_no_trading_ready_or_profitability_claim_is_made() -> None:
    combined_text = _r1_text().lower()
    forbidden_positive_claims = [
        "is trading-ready",
        "are trading-ready",
        "trading ready",
        "profitability is proven",
        "profit is proven",
        "profitable strategy",
        "guaranteed profit",
        "guaranteed return",
    ]

    assert "not trading-ready" in combined_text
    assert "no profitability claim" in combined_text
    for phrase in forbidden_positive_claims:
        assert phrase not in combined_text


def _r1_text() -> str:
    docs_text = "\n".join(path.read_text(encoding="utf-8") for path in R1_DOCS)
    matrix_text = MATRIX_PATH.read_text(encoding="utf-8")
    return f"{docs_text}\n{matrix_text}"
