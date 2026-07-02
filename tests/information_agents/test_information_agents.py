from __future__ import annotations

from pathlib import Path

import pandas as pd

from quantpilot_core.information_agents import (
    InformationAgentRole,
    InformationAgentSignal,
    InformationDecisionReport,
    InformationDirection,
    InformationHorizon,
    build_information_decision_report,
    run_concept_rotation_agent,
    run_fund_positioning_agent,
    run_liquidity_regime_agent,
    run_moneyflow_structure_agent,
    run_news_impact_agent,
    run_northbound_flow_agent,
    run_shareholder_dividend_agent,
    run_valuation_agent,
)
from quantpilot_core.tool_registry import ToolSideEffectLevel, build_default_tool_registry


def news_fixture() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "datetime": ["2026-01-02T09:30:00"],
            "symbol": ["000001.SZ"],
            "source": ["news-fixture"],
            "provider": ["fixture-provider"],
            "headline": ["Profit growth"],
            "summary": ["Short note"],
            "url": ["local-fixture"],
            "evidence_text": ["Profit growth beat expectations."],
            "sentiment_score": [0.7],
            "importance_score": [0.8],
        }
    )


def announcement_fixture() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "datetime": ["2026-01-02T15:01:00"],
            "symbol": ["000001.SZ"],
            "source": ["announcement-fixture"],
            "provider": ["fixture-provider"],
            "announcement_type": ["earnings"],
            "title": ["Earnings increase"],
            "url": ["local-fixture"],
            "evidence_text": ["Announcement reports earnings increase."],
            "importance_score": [0.9],
        }
    )


def northbound_fixture() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "date": ["2026-01-02", "2026-01-09"],
            "symbol": ["000001.SZ", "000001.SZ"],
            "source": ["northbound-fixture", "northbound-fixture"],
            "provider": ["fixture-provider", "fixture-provider"],
            "holding_shares": [1000.0, 1300.0],
            "holding_value": [10000.0, 14000.0],
            "holding_ratio": [0.03, 0.05],
            "net_buy_value": [500.0, 1200.0],
            "evidence_text": ["Initial holding row.", "Later holding row."],
        }
    )


def liquidity_fixtures() -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    macro = pd.DataFrame(
        {
            "date": ["2026-01-02"],
            "source": ["policy-fixture"],
            "provider": ["fixture-provider"],
            "policy_area": ["liquidity"],
            "event_type": ["guidance"],
            "title": ["Supportive liquidity guidance"],
            "evidence_text": ["Policy note is supportive."],
            "impact_direction": ["supportive"],
            "importance_score": [0.8],
        }
    )
    margin = pd.DataFrame(
        {
            "date": ["2026-01-02", "2026-01-03"],
            "symbol": ["000001.SZ", "000001.SZ"],
            "source": ["margin-fixture", "margin-fixture"],
            "provider": ["fixture-provider", "fixture-provider"],
            "financing_balance": [10000.0, 11200.0],
            "securities_lending_balance": [200.0, 180.0],
            "financing_buy_value": [500.0, 800.0],
            "repayment_value": [100.0, 200.0],
            "evidence_text": ["Initial margin row.", "Later margin row."],
        }
    )
    moneyflow = pd.DataFrame(
        {
            "date": ["2026-01-03"],
            "symbol": ["000001.SZ"],
            "source": ["moneyflow-fixture"],
            "provider": ["fixture-provider"],
            "main_net_inflow": [1200.0],
            "large_net_inflow": [700.0],
            "retail_net_inflow": [-100.0],
            "turnover_rate": [0.05],
            "evidence_text": ["Main and large money entered."],
        }
    )
    stabilization = pd.DataFrame(
        {
            "date": ["2026-01-03"],
            "symbol": ["000001.SZ"],
            "source": ["stabilization-fixture"],
            "provider": ["fixture-provider"],
            "vehicle_type": ["broad-etf"],
            "flow_value": [1000.0],
            "flow_direction": ["inflow"],
            "evidence_text": ["ETF stabilization clue was inflow."],
            "confidence_score": [0.7],
        }
    )
    return macro, margin, moneyflow, stabilization


def fund_holdings_fixture() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "date": ["2026-01-02", "2026-03-31"],
            "symbol": ["000001.SZ", "000001.SZ"],
            "source": ["fund-fixture", "fund-fixture"],
            "provider": ["fixture-provider", "fixture-provider"],
            "fund_code": ["F001", "F001"],
            "fund_name": ["Fixture Fund", "Fixture Fund"],
            "holding_shares": [1000.0, 1300.0],
            "holding_value": [10000.0, 12800.0],
            "portfolio_weight": [0.04, 0.07],
            "evidence_text": ["Initial fund position.", "Fund position increased."],
        }
    )


def valuation_fixture() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "date": ["2026-01-02"],
            "symbol": ["000001.SZ"],
            "source": ["valuation-fixture"],
            "provider": ["fixture-provider"],
            "pe_ttm": [9.0],
            "pb": [0.9],
            "ps_ttm": [1.1],
            "market_cap": [100000.0],
            "pe_percentile": [0.2],
            "evidence_text": ["Valuation is low versus recent range."],
        }
    )


def dividend_fixture() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "date": ["2026-01-02"],
            "symbol": ["000001.SZ"],
            "source": ["dividend-fixture"],
            "provider": ["fixture-provider"],
            "cash_dividend_per_share": [0.2],
            "stock_dividend_ratio": [0.0],
            "record_date": ["2026-01-05"],
            "ex_dividend_date": ["2026-01-06"],
            "dividend_yield": [0.03],
            "evidence_text": ["Cash dividend continuity."],
        }
    )


def concept_fixture() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "date": ["2026-01-02"],
            "symbol": ["000001.SZ"],
            "source": ["concept-fixture"],
            "provider": ["fixture-provider"],
            "concept_name": ["bank reform"],
            "membership_weight": [0.7],
            "is_active": [True],
            "evidence_text": ["Active concept membership."],
        }
    )


def social_fixture() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "datetime": ["2026-01-02T10:00:00"],
            "symbol": ["000001.SZ"],
            "source": ["social-fixture"],
            "provider": ["fixture-provider"],
            "platform": ["forum"],
            "topic": ["bank reform"],
            "evidence_text": ["Positive discussion volume."],
            "sentiment_score": [0.5],
            "mention_count": [80],
        }
    )


def shareholder_fixture() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "date": ["2026-01-02", "2026-03-31"],
            "symbol": ["000001.SZ", "000001.SZ"],
            "source": ["holder-fixture", "holder-fixture"],
            "provider": ["fixture-provider", "fixture-provider"],
            "shareholder_name": ["Fixture Holder", "Fixture Holder"],
            "holding_shares": [1000.0, 1150.0],
            "holding_ratio": [0.02, 0.025],
            "shareholder_rank": [1.0, 1.0],
            "evidence_text": ["Stable holder.", "Holder increased position."],
        }
    )


def test_news_impact_agent_emits_evidence_backed_signal() -> None:
    signal = run_news_impact_agent(news_fixture(), announcement_fixture())

    assert signal.agent_role is InformationAgentRole.NEWS_IMPACT
    assert signal.agent_role.value == "news_impact_agent"
    assert signal.target == "000001.SZ"
    assert signal.direction is InformationDirection.POSITIVE
    assert signal.score > 0
    assert signal.confidence > 0
    assert signal.horizon is InformationHorizon.SHORT_TERM
    assert signal.regime == "event_supportive"
    assert signal.evidence
    assert signal.limitations


def test_northbound_flow_agent_detects_accumulation_and_frequency_limitation() -> None:
    signal = run_northbound_flow_agent(northbound_fixture())

    assert signal.agent_role is InformationAgentRole.NORTHBOUND_FLOW
    assert signal.agent_role.value == "northbound_flow_agent"
    assert signal.direction is InformationDirection.ACCUMULATION
    assert signal.score > 0
    assert signal.horizon is InformationHorizon.MEDIUM_TERM
    assert any("quarterly after 2024-08-19" in item for item in signal.limitations)


def test_liquidity_regime_agent_detects_expansion() -> None:
    macro, margin, moneyflow, stabilization = liquidity_fixtures()

    signal = run_liquidity_regime_agent(
        macro_policy_events=macro,
        margin_trading_snapshots=margin,
        moneyflow_snapshots=moneyflow,
        stabilization_flow_clues=stabilization,
    )

    assert signal.agent_role is InformationAgentRole.LIQUIDITY_REGIME
    assert signal.agent_role.value == "liquidity_regime_agent"
    assert signal.target == "market"
    assert signal.direction is InformationDirection.EXPANSION
    assert signal.score > 0
    assert signal.regime == "liquidity_expansion"
    assert len(signal.evidence) >= 4


def test_fund_positioning_agent_detects_positioning_support() -> None:
    signal = run_fund_positioning_agent(fund_holdings_fixture())

    assert signal.agent_role is InformationAgentRole.FUND_POSITIONING
    assert signal.agent_role.value == "fund_positioning_agent"
    assert signal.target == "000001.SZ"
    assert signal.direction is InformationDirection.POSITIVE
    assert signal.score > 0
    assert signal.regime == "fund_positioning_supportive"
    assert signal.evidence


def test_valuation_agent_detects_valuation_support_without_profitability_claim() -> None:
    signal = run_valuation_agent(valuation_fixture(), dividend_fixture())

    assert signal.agent_role is InformationAgentRole.VALUATION
    assert signal.agent_role.value == "valuation_agent"
    assert signal.direction is InformationDirection.POSITIVE
    assert signal.score > 0
    assert signal.regime == "valuation_support"
    assert all("profitability" not in item.lower() for item in signal.limitations)


def test_concept_rotation_agent_detects_active_rotation() -> None:
    signal = run_concept_rotation_agent(concept_fixture(), news_fixture(), social_fixture())

    assert signal.agent_role is InformationAgentRole.CONCEPT_ROTATION
    assert signal.agent_role.value == "concept_rotation_agent"
    assert signal.direction is InformationDirection.POSITIVE
    assert signal.score > 0
    assert signal.regime == "concept_rotation_active"
    assert len(signal.evidence) >= 3


def test_shareholder_dividend_agent_detects_support() -> None:
    signal = run_shareholder_dividend_agent(shareholder_fixture(), dividend_fixture(), announcement_fixture())

    assert signal.agent_role is InformationAgentRole.SHAREHOLDER_DIVIDEND
    assert signal.agent_role.value == "shareholder_dividend_agent"
    assert signal.direction is InformationDirection.POSITIVE
    assert signal.score > 0
    assert signal.regime == "shareholder_support"
    assert signal.evidence


def test_moneyflow_structure_agent_detects_institutional_inflow() -> None:
    signal = run_moneyflow_structure_agent(liquidity_fixtures()[2])

    assert signal.agent_role is InformationAgentRole.MONEYFLOW_STRUCTURE
    assert signal.agent_role.value == "moneyflow_structure_agent"
    assert signal.direction is InformationDirection.POSITIVE
    assert signal.score > 0
    assert signal.regime == "institutional_inflow"
    assert signal.evidence


def test_information_decision_report_aggregates_and_reports_conflicts() -> None:
    positive = run_news_impact_agent(news_fixture(), announcement_fixture())
    negative = InformationAgentSignal(
        agent_role=InformationAgentRole.LIQUIDITY_REGIME,
        target="000001.SZ",
        direction=InformationDirection.CONTRACTION,
        score=-0.8,
        confidence=0.8,
        horizon=InformationHorizon.SHORT_TERM,
        regime="liquidity_contraction",
        evidence=("fixture negative liquidity evidence",),
        limitations=("fixture limitation",),
    )

    report = build_information_decision_report((positive, negative), target="000001.SZ")

    assert isinstance(report, InformationDecisionReport)
    assert report.target == "000001.SZ"
    assert report.conflicts
    assert report.aggregate_score < positive.score
    assert report.signals == (positive, negative)
    assert report.limitations


def test_information_agent_tools_are_listed_and_execute_through_registry() -> None:
    registry = build_default_tool_registry()
    expected = (
        "run_news_impact_agent",
        "run_northbound_flow_agent",
        "run_liquidity_regime_agent",
        "run_fund_positioning_agent",
        "run_valuation_agent",
        "run_concept_rotation_agent",
        "run_shareholder_dividend_agent",
        "run_moneyflow_structure_agent",
        "build_information_decision_report",
    )
    for name in expected:
        assert name in registry.list_names()
        assert registry.get(name).side_effect_level is ToolSideEffectLevel.PURE_IN_MEMORY

    news_result = registry.execute(
        "run_news_impact_agent",
        news_events=news_fixture(),
        announcement_events=announcement_fixture(),
    )
    northbound_result = registry.execute("run_northbound_flow_agent", northbound_holdings=northbound_fixture())
    macro, margin, moneyflow, stabilization = liquidity_fixtures()
    liquidity_result = registry.execute(
        "run_liquidity_regime_agent",
        macro_policy_events=macro,
        margin_trading_snapshots=margin,
        moneyflow_snapshots=moneyflow,
        stabilization_flow_clues=stabilization,
    )
    assert news_result.ok is True
    assert northbound_result.ok is True
    assert liquidity_result.ok is True
    fund_result = registry.execute("run_fund_positioning_agent", fund_holdings=fund_holdings_fixture())
    valuation_result = registry.execute(
        "run_valuation_agent",
        valuation_snapshots=valuation_fixture(),
        dividend_records=dividend_fixture(),
    )
    concept_result = registry.execute(
        "run_concept_rotation_agent",
        concept_memberships=concept_fixture(),
        news_events=news_fixture(),
        social_sentiment_events=social_fixture(),
    )
    shareholder_result = registry.execute(
        "run_shareholder_dividend_agent",
        shareholder_snapshots=shareholder_fixture(),
        dividend_records=dividend_fixture(),
        announcement_events=announcement_fixture(),
    )
    moneyflow_result = registry.execute("run_moneyflow_structure_agent", moneyflow_snapshots=liquidity_fixtures()[2])
    assert fund_result.ok is True
    assert valuation_result.ok is True
    assert concept_result.ok is True
    assert shareholder_result.ok is True
    assert moneyflow_result.ok is True

    report_result = registry.execute(
        "build_information_decision_report",
        signals=(
            news_result.output,
            northbound_result.output,
            liquidity_result.output,
            fund_result.output,
            valuation_result.output,
            concept_result.output,
            shareholder_result.output,
            moneyflow_result.output,
        ),
        target="000001.SZ",
    )

    assert report_result.ok is True
    assert isinstance(report_result.output, InformationDecisionReport)
    assert report_result.side_effect_level is ToolSideEffectLevel.PURE_IN_MEMORY


def test_information_agents_have_no_forbidden_runtime_scope() -> None:
    package_root = Path(__file__).parents[2] / "src" / "quantpilot_core" / "information_agents"
    source = "\n".join(path.read_text() for path in package_root.glob("*.py")).lower()

    forbidden_terms = (
        "requests",
        "urllib",
        "http",
        "socket",
        "token",
        "api_key",
        "broker",
        "live",
        "qrun",
        "deepseek",
        "subprocess",
        "os.system",
    )
    assert all(term not in source for term in forbidden_terms)
