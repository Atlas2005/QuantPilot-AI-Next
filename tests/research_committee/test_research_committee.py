from __future__ import annotations

from dataclasses import fields
from pathlib import Path

import pandas as pd

from quantpilot_core.information_agents import (
    InformationAgentRole,
    InformationAgentSignal,
    InformationDirection,
    InformationHorizon,
)
from quantpilot_core.research_committee import (
    ResearchCandidateRanking,
    ResearchCommitteeReport,
    ResearchCommitteeView,
    ResearchEvidenceBucket,
    build_research_committee_report,
    rank_research_candidates,
)
from quantpilot_core.tool_registry import ToolSideEffectLevel, build_default_tool_registry


def signal(
    role: InformationAgentRole,
    direction: InformationDirection,
    score: float,
    confidence: float,
    evidence: str,
    *,
    target: str = "000001.SZ",
) -> InformationAgentSignal:
    return InformationAgentSignal(
        agent_role=role,
        target=target,
        direction=direction,
        score=score,
        confidence=confidence,
        horizon=InformationHorizon.SHORT_TERM,
        regime="fixture",
        evidence=(evidence,),
        limitations=("fixture-only information signal",),
    )


def bullish_signals(target: str = "000001.SZ") -> tuple[InformationAgentSignal, ...]:
    return (
        signal(
            InformationAgentRole.NEWS_IMPACT,
            InformationDirection.POSITIVE,
            0.72,
            0.82,
            "news impact evidence is supportive",
            target=target,
        ),
        signal(
            InformationAgentRole.NORTHBOUND_FLOW,
            InformationDirection.ACCUMULATION,
            0.58,
            0.75,
            "northbound accumulation evidence",
            target=target,
        ),
    )


def test_report_with_aligned_bullish_info_and_good_replay() -> None:
    report = build_research_committee_report(
        bullish_signals(),
        {
            "symbol": "000001.SZ",
            "total_return": 0.18,
            "sharpe_ratio": 1.4,
            "max_drawdown": -0.04,
            "win_rate": 0.64,
            "turnover": 0.6,
            "trade_count": 6,
        },
    )

    assert isinstance(report, ResearchCommitteeReport)
    assert report.target == "000001.SZ"
    assert report.committee_stance == "bull"
    assert report.composite_score > 0.4
    assert report.confidence > 0.7
    assert report.bull_evidence
    assert not report.conflicts
    assert "Supportive evidence dominates" in report.dominant_thesis
    assert report.candidate_rankings == (
        ResearchCandidateRanking(
            target="000001.SZ",
            rank=1,
            composite_score=report.composite_score,
            information_score=report.views[0].score,
            replay_score=report.views[1].score,
            confidence=report.confidence,
            dominant_thesis=report.dominant_thesis,
            risk_thesis=report.risk_thesis,
            evidence=report.candidate_rankings[0].evidence,
            limitations=report.limitations,
        ),
    )
    assert [field.name for field in fields(ResearchEvidenceBucket)] == [
        "source",
        "stance",
        "score",
        "confidence",
        "evidence",
        "limitations",
    ]
    assert [field.name for field in fields(ResearchCommitteeView)] == [
        "view_name",
        "stance",
        "score",
        "confidence",
        "evidence",
        "risks",
        "limitations",
    ]


def test_report_with_conflicting_info_and_weak_replay() -> None:
    signals = (
        signal(
            InformationAgentRole.NEWS_IMPACT,
            InformationDirection.POSITIVE,
            0.66,
            0.7,
            "event evidence is supportive",
        ),
        signal(
            InformationAgentRole.LIQUIDITY_REGIME,
            InformationDirection.CONTRACTION,
            -0.74,
            0.8,
            "liquidity contraction evidence",
        ),
    )
    replay = pd.Series(
        {
            "target": "000001.SZ",
            "total_return": -0.09,
            "sharpe": -0.45,
            "max_drawdown": -0.22,
            "win_rate": 0.38,
            "turnover": 2.4,
            "trades": 2,
        }
    )

    report = build_research_committee_report(signals, replay)

    assert report.committee_stance in {"bear", "mixed"}
    assert report.bear_evidence
    assert report.conflicts
    assert "committee conflicts" in report.risk_thesis
    assert "Stress transaction costs and slippage assumptions offline." in report.next_experiment_plan
    assert "Isolate conflicting information frames and rerun the committee synthesis." in report.next_experiment_plan


def test_ranking_of_multiple_candidates() -> None:
    rankings = rank_research_candidates(
        (
            {
                "target": "000001.SZ",
                "information_signals": bullish_signals("000001.SZ"),
                "replay_metrics": {
                    "total_return": 0.2,
                    "sharpe_ratio": 1.2,
                    "max_drawdown": -0.05,
                    "win_rate": 0.62,
                    "turnover": 0.4,
                    "trade_count": 5,
                },
            },
            {
                "target": "000002.SZ",
                "information_signals": (
                    signal(
                        InformationAgentRole.NEWS_IMPACT,
                        InformationDirection.NEGATIVE,
                        -0.4,
                        0.7,
                        "negative evidence",
                        target="000002.SZ",
                    ),
                ),
                "replay_metrics": {
                    "total_return": -0.04,
                    "sharpe_ratio": -0.2,
                    "max_drawdown": -0.18,
                    "win_rate": 0.42,
                    "turnover": 1.1,
                    "trade_count": 3,
                },
            },
        )
    )

    assert [ranking.rank for ranking in rankings] == [1, 2]
    assert rankings[0].target == "000001.SZ"
    assert rankings[0].composite_score > rankings[1].composite_score


def test_registry_execution_coverage() -> None:
    registry = build_default_tool_registry()

    report_result = registry.execute(
        "build_research_committee_report",
        information_signals=bullish_signals(),
        replay_metrics=pd.DataFrame(
            [
                {
                    "total_return": 0.12,
                    "sharpe_ratio": 1.1,
                    "max_drawdown": -0.03,
                    "win_rate": 0.6,
                    "turnover": 0.5,
                    "trade_count": 4,
                }
            ]
        ),
    )
    assert report_result.ok is True
    assert report_result.side_effect_level is ToolSideEffectLevel.PURE_IN_MEMORY
    assert isinstance(report_result.output, ResearchCommitteeReport)

    ranking_result = registry.execute(
        "rank_research_candidates",
        candidates=(report_result.output,),
    )
    assert ranking_result.ok is True
    assert ranking_result.side_effect_level is ToolSideEffectLevel.PURE_IN_MEMORY
    assert isinstance(ranking_result.output[0], ResearchCandidateRanking)


def test_forbidden_runtime_scope_and_no_action_words() -> None:
    package_root = Path(__file__).parents[2] / "src" / "quantpilot_core" / "research_committee"
    source = "\n".join(path.read_text() for path in package_root.glob("*.py")).lower()

    forbidden_runtime_terms = (
        "requests",
        "urllib",
        "http://",
        "https://",
        "socket",
        "download",
        "deepseek",
        "openai",
        "anthropic",
        "qrun",
        "mod_ctp",
        "mod-vnpy",
        "vnpy",
    )
    assert all(term not in source for term in forbidden_runtime_terms)

    report = build_research_committee_report(
        bullish_signals(),
        {
            "total_return": 0.1,
            "sharpe_ratio": 1.0,
            "max_drawdown": -0.05,
            "win_rate": 0.6,
            "turnover": 0.5,
            "trade_count": 4,
        },
    )
    rendered = " ".join(
        (
            report.dominant_thesis,
            report.risk_thesis,
            " ".join(report.next_experiment_plan),
            " ".join(view.view_name for view in report.views),
        )
    ).lower()
    assert all(word not in rendered.split() for word in ("buy", "sell", "hold", "order"))
