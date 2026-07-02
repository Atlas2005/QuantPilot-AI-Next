from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from quantpilot_core.execution_candidate import ExecutionCandidate, ExecutionCandidateReport
from quantpilot_core.execution_optimizer import (
    CostModel,
    ExecutionPlanner,
    OptimizationAssumption,
    PortfolioAllocationPlan,
    PortfolioOptimizer,
    PositionSizer,
    build_portfolio_allocation_plan,
)
from quantpilot_core.tool_registry import ToolSideEffectLevel, build_default_tool_registry


def exec1_report() -> ExecutionCandidateReport:
    timestamp = datetime(2026, 1, 2, 9, 30, tzinfo=UTC)
    return ExecutionCandidateReport(
        candidates=(
            ExecutionCandidate(
                symbol="000001.SZ",
                direction="long",
                confidence=0.8,
                expected_return=0.8,
                risk_score=0.2,
                liquidity_score=0.9,
                timestamp=timestamp,
            ),
            ExecutionCandidate(
                symbol="000002.SZ",
                direction="long",
                confidence=0.6,
                expected_return=0.4,
                risk_score=0.3,
                liquidity_score=0.8,
                timestamp=timestamp,
            ),
            ExecutionCandidate(
                symbol="000003.SZ",
                direction="short",
                confidence=0.7,
                expected_return=-0.5,
                risk_score=0.4,
                liquidity_score=0.7,
                timestamp=timestamp,
            ),
        ),
        aggregate_score=0.233333,
        strategy_id="EXEC1-fixture",
    )


def test_cost_model_estimates_fee_slippage_and_turnover_penalty() -> None:
    model = CostModel(OptimizationAssumption(capital=100_000.0, fee_rate=0.0003, slippage_bps=2.0, turnover_penalty_rate=0.0005))

    estimate = model.estimate_total(target_notional=10_000.0, turnover_notional=5_000.0, liquidity_score=0.5)

    assert estimate.fee == 3.0
    assert estimate.slippage == 3.0
    assert estimate.turnover_penalty == 2.5
    assert estimate.total_cost == 8.5


def test_position_sizer_converts_weights_to_a_share_integer_lots() -> None:
    sizer = PositionSizer(OptimizationAssumption(capital=100_000.0, lot_size=100))

    assert sizer.shares_for_weight(target_weight=0.123, price=10.0) == 1200
    assert sizer.notional_for_shares(shares=1200, price=10.0) == 12_000.0
    assert sizer.shares_for_weight(target_weight=0.01, price=250.0) == 0


def test_portfolio_optimizer_allocates_by_softmax_and_applies_cost_rounded_lots() -> None:
    plan = build_portfolio_allocation_plan(
        exec1_report(),
        last_prices={"000001.SZ": 10.0, "000002.SZ": 20.0, "000003.SZ": 8.0},
        assumptions=OptimizationAssumption(capital=100_000.0, lot_size=100),
    )

    assert isinstance(plan, PortfolioAllocationPlan)
    assert plan.strategy_id == "EXEC1-fixture:EXEC2"
    assert [allocation.symbol for allocation in plan.allocations] == ["000001.SZ", "000002.SZ", "000003.SZ"]
    assert plan.allocations[0].normalized_score == 1.0
    assert plan.allocations[0].target_shares % 100 == 0
    assert plan.allocations[1].target_shares % 100 == 0
    assert plan.allocations[2].target_weight == 0.0
    assert plan.gross_exposure < 1.0
    assert plan.vectorbt_weights == {
        allocation.symbol: allocation.vectorbt_weight for allocation in plan.allocations
    }
    assert plan.target_shares["000001.SZ"] > plan.target_shares["000002.SZ"]


def test_high_cost_assumptions_reduce_target_exposure_without_dropping_candidates() -> None:
    low_cost = build_portfolio_allocation_plan(
        exec1_report(),
        last_prices={"000001.SZ": 10.0, "000002.SZ": 20.0, "000003.SZ": 8.0},
        assumptions=OptimizationAssumption(capital=100_000.0, fee_rate=0.0001, slippage_bps=1.0, turnover_penalty_rate=0.0001),
    )
    high_cost = build_portfolio_allocation_plan(
        exec1_report(),
        last_prices={"000001.SZ": 10.0, "000002.SZ": 20.0, "000003.SZ": 8.0},
        assumptions=OptimizationAssumption(capital=100_000.0, fee_rate=0.02, slippage_bps=500.0, turnover_penalty_rate=0.02),
    )

    assert len(high_cost.allocations) == len(low_cost.allocations)
    assert high_cost.total_estimated_cost > low_cost.total_estimated_cost
    assert high_cost.gross_exposure < low_cost.gross_exposure


def test_execution_planner_accepts_exec1_report_and_exposes_vectorbt_weights() -> None:
    planner = ExecutionPlanner(PortfolioOptimizer(assumptions=OptimizationAssumption(capital=50_000.0)))

    plan = planner.build_plan(exec1_report(), last_prices={"000001.SZ": 10.0, "000002.SZ": 20.0})

    assert plan.vectorbt_weights["000001.SZ"] > 0
    assert plan.vectorbt_weights["000002.SZ"] > 0
    assert plan.vectorbt_weights["000003.SZ"] == 0.0
    assert set(plan.vectorbt_weights) == {"000001.SZ", "000002.SZ", "000003.SZ"}


def test_execution_optimizer_tool_runs_through_registry() -> None:
    registry = build_default_tool_registry()

    result = registry.execute(
        "build_portfolio_allocation_plan",
        report=exec1_report(),
        last_prices={"000001.SZ": 10.0, "000002.SZ": 20.0, "000003.SZ": 8.0},
        assumptions=OptimizationAssumption(capital=100_000.0),
    )

    assert result.ok is True
    assert result.side_effect_level is ToolSideEffectLevel.PURE_IN_MEMORY
    assert isinstance(result.output, PortfolioAllocationPlan)
    assert registry.get("build_portfolio_allocation_plan").side_effect_level is ToolSideEffectLevel.PURE_IN_MEMORY


def test_execution_optimizer_has_no_forbidden_runtime_scope() -> None:
    package_root = Path(__file__).parents[2] / "src" / "quantpilot_core" / "execution_optimizer"
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
    )
    assert not any(fragment in source_text for fragment in forbidden_fragments)
