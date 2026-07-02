from __future__ import annotations

from tests.order_intent.test_order_intent_controller import plan

from quantpilot_core.order_intent import OrderIntentProposal
from quantpilot_core.paper_trading import PaperAccount, PaperTradingLoopResult
from quantpilot_core.quant_firm import DeepSeekAdvisoryRole, build_default_role_skill_registry
from quantpilot_core.tool_registry import build_default_tool_registry


def test_tool_registry_wrappers_work_for_order_intents_and_paper_loop() -> None:
    registry = build_default_tool_registry()

    proposal_result = registry.execute("build_order_intent_proposal", plan=plan(), run_label="registry")
    assert proposal_result.ok is True
    assert isinstance(proposal_result.output, OrderIntentProposal)

    loop_result = registry.execute(
        "run_paper_trading_loop",
        proposal=proposal_result.output,
        latest_prices={"600000": 10.0},
        account=PaperAccount(cash=3_000.0),
    )

    assert loop_result.ok is True
    assert isinstance(loop_result.output, PaperTradingLoopResult)
    assert loop_result.output.account.positions == {"600000": 200}


def test_role_skill_registry_includes_paper_trading_without_broker_live_exposure() -> None:
    registry = build_default_role_skill_registry()
    portfolio_tools = {skill.tool_name for skill in registry.list_enabled_skills(DeepSeekAdvisoryRole.PORTFOLIO_DESK)}
    execution_tools = {
        skill.tool_name for skill in registry.list_enabled_skills(DeepSeekAdvisoryRole.EXECUTION_SIMULATION_DESK)
    }
    backtest_skills = {skill.skill_name for skill in registry.list_enabled_skills(DeepSeekAdvisoryRole.BACKTEST_DESK)}
    learning_tools = {skill.tool_name for skill in registry.list_enabled_skills(DeepSeekAdvisoryRole.LEARNING_DESK)}

    assert "build_order_intent_proposal" in portfolio_tools
    assert "run_paper_trading_loop" in execution_tools
    assert "backtest_vectorbt_order_intent_adapter" in backtest_skills
    assert "run_paper_trading_loop" in learning_tools
    assert registry.validate_no_broker_live_enabled_by_default() == ()


def test_rqalpha_backtrader_order_intent_placeholders_are_disabled() -> None:
    registry = build_default_role_skill_registry()
    placeholders = {
        skill.skill_name: skill
        for skill in registry.list_skills()
        if skill.tool_name
        in {
            "rqalpha_order_intent_adapter_placeholder",
            "backtrader_order_intent_adapter_placeholder",
        }
    }

    assert placeholders["execution_simulation_rqalpha_order_intent_placeholder"].enabled_by_default is False
    assert placeholders["execution_simulation_backtrader_order_intent_placeholder"].enabled_by_default is False
