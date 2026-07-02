from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from quantpilot_core.execution_candidate import (
    ExecutionCandidate,
    ExecutionCandidateBuilder,
    ExecutionCandidateReport,
    build_execution_candidate_report,
)


def test_builder_converts_mock_signals_to_top_n_candidates() -> None:
    timestamp = datetime(2026, 1, 2, 9, 30, tzinfo=UTC)
    builder = ExecutionCandidateBuilder(strategy_id="alpha-demo", top_n=2, timestamp=timestamp)

    report = builder.build(
        qlib_signals=[
            {"instrument": "000001.SZ", "score": 0.8, "liquidity_score": 0.9},
            {"instrument": "000002.SZ", "score": -0.6, "liquidity_score": 0.5},
            {"instrument": "000003.SZ", "score": 0.1, "liquidity_score": 0.8},
        ],
        info_signals=[
            {"target": "000001.SZ", "aggregate_score": 0.4, "aggregate_bias": "positive"},
            {"target": "000002.SZ", "aggregate_score": 0.3, "aggregate_bias": "negative"},
            {"target": "000003.SZ", "aggregate_score": 0.0, "aggregate_bias": "neutral"},
        ],
        research_committee_output=[
            {"target": "000001.SZ", "composite_score": 0.7, "committee_stance": "bull"},
            {"target": "000002.SZ", "composite_score": 0.5, "committee_stance": "bear"},
            {"target": "000003.SZ", "composite_score": 0.2, "committee_stance": "neutral"},
        ],
    )

    assert isinstance(report, ExecutionCandidateReport)
    assert report.strategy_id == "alpha-demo"
    assert report.aggregate_score == 0.083333
    assert [candidate.symbol for candidate in report.candidates] == ["000001.SZ", "000002.SZ"]
    assert report.candidates == (
        ExecutionCandidate(
            symbol="000001.SZ",
            direction="long",
            confidence=0.633333,
            expected_return=0.633333,
            risk_score=0.286667,
            liquidity_score=0.9,
            timestamp=timestamp,
            lot_size=100,
            metadata=report.candidates[0].metadata,
        ),
        ExecutionCandidate(
            symbol="000002.SZ",
            direction="short",
            confidence=0.466667,
            expected_return=-0.466667,
            risk_score=0.523333,
            liquidity_score=0.5,
            timestamp=timestamp,
            lot_size=100,
            metadata=report.candidates[1].metadata,
        ),
    )


def test_output_is_deterministic_for_identical_inputs() -> None:
    qlib_signals = {"000001.SZ": {"score": 0.5}, "000002.SZ": {"score": 0.5}}
    info_signals = {"000001.SZ": {"info_score": 0.2}, "000002.SZ": {"info_score": 0.2}}
    research_committee_output = {
        "000001.SZ": {"research_score": 0.4},
        "000002.SZ": {"research_score": -0.4},
    }

    first = build_execution_candidate_report(
        qlib_signals,
        info_signals,
        research_committee_output,
        strategy_id="deterministic",
        top_n=2,
    )
    second = build_execution_candidate_report(
        qlib_signals,
        info_signals,
        research_committee_output,
        strategy_id="deterministic",
        top_n=2,
    )

    assert first == second
    assert [candidate.symbol for candidate in first.candidates] == ["000001.SZ", "000002.SZ"]
    assert [candidate.expected_return for candidate in first.candidates] == [0.366667, 0.1]


def test_a_share_lot_constraint_is_metadata_only() -> None:
    report = build_execution_candidate_report(
        [{"symbol": "000001.SZ", "signal_score": 0.6}],
        [{"symbol": "000001.SZ", "info_score": 0.3}],
        [{"symbol": "000001.SZ", "research_score": 0.9}],
    )

    candidate = report.candidates[0]

    assert candidate.lot_size == 100
    assert candidate.metadata["lot_constraint"] == "100_share_lot_metadata_only"
    assert candidate.metadata["lot_constraint_enforced"] is False
    assert "quantity" not in candidate.metadata


def test_execution_candidate_package_has_no_runtime_scope() -> None:
    package_root = Path(__file__).parents[2] / "src" / "quantpilot_core" / "execution_candidate"
    source_text = "\n".join(path.read_text() for path in sorted(package_root.glob("*.py"))).lower()

    forbidden_fragments = (
        "requests",
        "urllib",
        "http://",
        "https://",
        "socket",
        "download",
        "akshare",
        "baostock",
        "tushare",
        "import qlib",
        "qlib.init",
        "qrun",
        "rqalpha",
        "deepseek",
        "openai",
        "anthropic",
        "mod_ctp",
        "mod-vnpy",
        "vnpy",
        "place_order",
        "send_order",
        "submit_order",
        "preflight",
        "readiness",
        "block_trade",
    )
    assert not any(fragment in source_text for fragment in forbidden_fragments)
