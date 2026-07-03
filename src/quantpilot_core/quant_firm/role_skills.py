"""Role-to-skill bindings for the Quant Firm advisory organization."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from quantpilot_core.quant_firm.deepseek_advisory import DeepSeekAdvisoryRole
from quantpilot_core.tool_registry.contracts import ToolSideEffectLevel


@dataclass(frozen=True)
class QuantFirmRoleSkill:
    """One mature-tool or internal-adapter skill available to a Quant Firm role."""

    role: DeepSeekAdvisoryRole
    skill_name: str
    tool_name: str
    source_layer: str
    purpose: str
    side_effect_level: ToolSideEffectLevel
    mature_framework: str | None
    enabled_by_default: bool


class QuantFirmRoleSkillRegistry:
    """Deterministic in-memory registry of role-specific Quant Firm skills."""

    def __init__(self, skills: Iterable[QuantFirmRoleSkill]) -> None:
        self._skills = tuple(skills)

    def list_skills(self) -> tuple[QuantFirmRoleSkill, ...]:
        return self._skills

    def list_by_role(self, role: DeepSeekAdvisoryRole | str) -> tuple[QuantFirmRoleSkill, ...]:
        resolved_role = role if isinstance(role, DeepSeekAdvisoryRole) else DeepSeekAdvisoryRole(role)
        return tuple(skill for skill in self._skills if skill.role is resolved_role)

    def list_enabled_skills(self, role: DeepSeekAdvisoryRole | str | None = None) -> tuple[QuantFirmRoleSkill, ...]:
        skills = self._skills if role is None else self.list_by_role(role)
        return tuple(skill for skill in skills if skill.enabled_by_default)

    def validate_no_broker_live_enabled_by_default(self) -> tuple[str, ...]:
        """Return enabled skills that look like broker or live-trading capabilities."""

        return tuple(
            skill.skill_name
            for skill in self._skills
            if skill.enabled_by_default and _has_broker_live_scope(skill)
        )

    def validate_deepseek_has_no_direct_broker_live_skill(self) -> tuple[str, ...]:
        """Return DeepSeek advisory skills that point at broker or live scope."""

        return tuple(
            skill.skill_name
            for skill in self._skills
            if skill.tool_name == "run_deepseek_advisory_fallback" and _has_broker_live_scope(skill)
        )

    def validate_each_role_has_useful_skill(self) -> tuple[str, ...]:
        """Return advisory roles that have no enabled skill bindings."""

        return tuple(
            role.value
            for role in DeepSeekAdvisoryRole
            if not self.list_enabled_skills(role)
        )

    def validate_known_tools_or_disabled_placeholders(
        self,
        known_tool_names: Iterable[str],
    ) -> tuple[str, ...]:
        """Return enabled skills that do not point at a registered tool."""

        known = set(known_tool_names)
        return tuple(
            skill.skill_name
            for skill in self._skills
            if skill.enabled_by_default and skill.tool_name not in known
        )


def build_default_role_skill_registry() -> QuantFirmRoleSkillRegistry:
    """Build the default Quant Firm role skill registry."""

    return QuantFirmRoleSkillRegistry(DEFAULT_ROLE_SKILLS)


PURE = ToolSideEffectLevel.PURE_IN_MEMORY


DEFAULT_ROLE_SKILLS: tuple[QuantFirmRoleSkill, ...] = (
    QuantFirmRoleSkill(
        role=DeepSeekAdvisoryRole.INVESTMENT_COMMITTEE,
        skill_name="committee_research_synthesis",
        tool_name="build_research_committee_report",
        source_layer="research_committee",
        purpose="Synthesize research, information, and replay diagnostics before committee review.",
        side_effect_level=PURE,
        mature_framework="internal_research_committee",
        enabled_by_default=True,
    ),
    QuantFirmRoleSkill(
        role=DeepSeekAdvisoryRole.INVESTMENT_COMMITTEE,
        skill_name="committee_exec2_portfolio_review",
        tool_name="build_portfolio_allocation_plan",
        source_layer="execution_optimizer",
        purpose="Review deterministic EXEC2 allocation output as committee evidence.",
        side_effect_level=PURE,
        mature_framework="internal_exec2_optimizer",
        enabled_by_default=True,
    ),
    QuantFirmRoleSkill(
        role=DeepSeekAdvisoryRole.INVESTMENT_COMMITTEE,
        skill_name="committee_quant_firm_cycle",
        tool_name="run_quant_firm_decision_cycle",
        source_layer="quant_firm",
        purpose="Run the offline multi-agent firm cycle without external side effects.",
        side_effect_level=PURE,
        mature_framework="quant_firm_internal_simulation",
        enabled_by_default=True,
    ),
    QuantFirmRoleSkill(
        role=DeepSeekAdvisoryRole.INVESTMENT_COMMITTEE,
        skill_name="committee_walk_forward_metrics_review",
        tool_name="run_walk_forward_paper_evaluation",
        source_layer="walk_forward",
        purpose="Review aggregate rolling out-of-sample paper evaluation metrics.",
        side_effect_level=PURE,
        mature_framework="walk_forward_paper_evaluation",
        enabled_by_default=True,
    ),
    QuantFirmRoleSkill(
        role=DeepSeekAdvisoryRole.INVESTMENT_COMMITTEE,
        skill_name="committee_deepseek_fallback_advice",
        tool_name="run_deepseek_advisory_fallback",
        source_layer="deepseek_advisory",
        purpose="Produce advisory-only review notes without model or network calls.",
        side_effect_level=PURE,
        mature_framework="deepseek_advisory_fallback",
        enabled_by_default=True,
    ),
    QuantFirmRoleSkill(
        role=DeepSeekAdvisoryRole.RESEARCH_DESK,
        skill_name="research_qlib_signal_handoff",
        tool_name="qlib_signal_artifact_to_vbt3_signal_frame",
        source_layer="signal_integration",
        purpose="Transform offline Qlib signal artifacts into vectorbt-ready signal rows.",
        side_effect_level=PURE,
        mature_framework="qlib_artifact_adapter",
        enabled_by_default=True,
    ),
    QuantFirmRoleSkill(
        role=DeepSeekAdvisoryRole.RESEARCH_DESK,
        skill_name="research_committee_report",
        tool_name="build_research_committee_report",
        source_layer="research_committee",
        purpose="Build deterministic research diagnostics from information and replay evidence.",
        side_effect_level=PURE,
        mature_framework="internal_research_committee",
        enabled_by_default=True,
    ),
    QuantFirmRoleSkill(
        role=DeepSeekAdvisoryRole.RESEARCH_DESK,
        skill_name="research_candidate_ranking",
        tool_name="rank_research_candidates",
        source_layer="research_committee",
        purpose="Rank research candidates by deterministic committee score.",
        side_effect_level=PURE,
        mature_framework="internal_research_committee",
        enabled_by_default=True,
    ),
    QuantFirmRoleSkill(
        role=DeepSeekAdvisoryRole.INFORMATION_DESK,
        skill_name="information_decision_report",
        tool_name="build_information_decision_report",
        source_layer="information_agents",
        purpose="Aggregate A-share information-agent evidence into a decision report.",
        side_effect_level=PURE,
        mature_framework="a_share_information_layer",
        enabled_by_default=True,
    ),
    QuantFirmRoleSkill(
        role=DeepSeekAdvisoryRole.INFORMATION_DESK,
        skill_name="information_news_impact",
        tool_name="run_news_impact_agent",
        source_layer="information_agents",
        purpose="Interpret normalized news and announcements as advisory evidence.",
        side_effect_level=PURE,
        mature_framework="a_share_information_layer",
        enabled_by_default=True,
    ),
    QuantFirmRoleSkill(
        role=DeepSeekAdvisoryRole.INFORMATION_DESK,
        skill_name="information_northbound_flow",
        tool_name="run_northbound_flow_agent",
        source_layer="information_agents",
        purpose="Review northbound and foreign-capital flow signals.",
        side_effect_level=PURE,
        mature_framework="a_share_information_layer",
        enabled_by_default=True,
    ),
    QuantFirmRoleSkill(
        role=DeepSeekAdvisoryRole.INFORMATION_DESK,
        skill_name="information_moneyflow_structure",
        tool_name="run_moneyflow_structure_agent",
        source_layer="information_agents",
        purpose="Review money-flow structure as institutional or retail support evidence.",
        side_effect_level=PURE,
        mature_framework="a_share_information_layer",
        enabled_by_default=True,
    ),
    QuantFirmRoleSkill(
        role=DeepSeekAdvisoryRole.INFORMATION_DESK,
        skill_name="information_valuation",
        tool_name="run_valuation_agent",
        source_layer="information_agents",
        purpose="Review valuation and dividend evidence for support or risk.",
        side_effect_level=PURE,
        mature_framework="a_share_information_layer",
        enabled_by_default=True,
    ),
    QuantFirmRoleSkill(
        role=DeepSeekAdvisoryRole.INFORMATION_DESK,
        skill_name="information_concept_rotation",
        tool_name="run_concept_rotation_agent",
        source_layer="information_agents",
        purpose="Review concept, theme, and social-sentiment rotation evidence.",
        side_effect_level=PURE,
        mature_framework="a_share_information_layer",
        enabled_by_default=True,
    ),
    QuantFirmRoleSkill(
        role=DeepSeekAdvisoryRole.BACKTEST_DESK,
        skill_name="backtest_vectorbt_provider_replay",
        tool_name="replay_provider_signals_with_vectorbt",
        source_layer="vectorbt_integration",
        purpose="Replay provider-style signal rows through the vectorbt adapter.",
        side_effect_level=PURE,
        mature_framework="vectorbt_adapter",
        enabled_by_default=True,
    ),
    QuantFirmRoleSkill(
        role=DeepSeekAdvisoryRole.BACKTEST_DESK,
        skill_name="backtest_vectorbt_signal_backtest",
        tool_name="run_vectorbt_signal_backtest",
        source_layer="vectorbt_integration",
        purpose="Run vectorbt signal diagnostics from in-memory close and signal columns.",
        side_effect_level=PURE,
        mature_framework="vectorbt_adapter",
        enabled_by_default=True,
    ),
    QuantFirmRoleSkill(
        role=DeepSeekAdvisoryRole.BACKTEST_DESK,
        skill_name="backtest_vectorbt_order_intent_adapter",
        tool_name="build_order_intent_proposal",
        source_layer="order_intent",
        purpose="Review order-intent target weights and shares before vectorbt-style replay mapping.",
        side_effect_level=PURE,
        mature_framework="vectorbt_order_intent_adapter",
        enabled_by_default=True,
    ),
    QuantFirmRoleSkill(
        role=DeepSeekAdvisoryRole.BACKTEST_DESK,
        skill_name="backtest_walk_forward_paper_evaluation",
        tool_name="run_walk_forward_paper_evaluation",
        source_layer="walk_forward",
        purpose="Run leakage-checked rolling out-of-sample paper evaluation over historical windows.",
        side_effect_level=PURE,
        mature_framework="walk_forward_paper_evaluation",
        enabled_by_default=True,
    ),
    QuantFirmRoleSkill(
        role=DeepSeekAdvisoryRole.BACKTEST_DESK,
        skill_name="backtest_qlib_signal_handoff",
        tool_name="qlib_signal_artifact_to_vbt3_signal_frame",
        source_layer="signal_integration",
        purpose="Use Qlib signal artifacts as mature-framework handoff evidence.",
        side_effect_level=PURE,
        mature_framework="qlib_artifact_adapter",
        enabled_by_default=True,
    ),
    QuantFirmRoleSkill(
        role=DeepSeekAdvisoryRole.BACKTEST_DESK,
        skill_name="backtest_rqalpha_artifact_review_placeholder",
        tool_name="build_rqalpha_isolated_prototype_runner_review_report",
        source_layer="rqalpha_artifact_review",
        purpose="Future registry binding for local RQAlpha artifact report review.",
        side_effect_level=PURE,
        mature_framework="rqalpha_artifact_adapter",
        enabled_by_default=False,
    ),
    QuantFirmRoleSkill(
        role=DeepSeekAdvisoryRole.PORTFOLIO_DESK,
        skill_name="portfolio_exec1_candidate_report",
        tool_name="build_execution_candidate_report",
        source_layer="execution_candidate",
        purpose="Review EXEC1 candidate report before deterministic portfolio allocation.",
        side_effect_level=PURE,
        mature_framework="internal_exec1_candidate_builder",
        enabled_by_default=True,
    ),
    QuantFirmRoleSkill(
        role=DeepSeekAdvisoryRole.PORTFOLIO_DESK,
        skill_name="portfolio_exec2_allocation_plan",
        tool_name="build_portfolio_allocation_plan",
        source_layer="execution_optimizer",
        purpose="Review EXEC2 allocation, cost drag, concentration, liquidity, and turnover.",
        side_effect_level=PURE,
        mature_framework="internal_exec2_optimizer",
        enabled_by_default=True,
    ),
    QuantFirmRoleSkill(
        role=DeepSeekAdvisoryRole.PORTFOLIO_DESK,
        skill_name="portfolio_build_order_intent_proposal",
        tool_name="build_order_intent_proposal",
        source_layer="order_intent",
        purpose="Convert EXEC2 allocation plans into advisory-only paper trading order intents.",
        side_effect_level=PURE,
        mature_framework="order_intent_controller",
        enabled_by_default=True,
    ),
    QuantFirmRoleSkill(
        role=DeepSeekAdvisoryRole.EXECUTION_SIMULATION_DESK,
        skill_name="execution_simulation_vectorbt_replay",
        tool_name="replay_provider_signals_with_vectorbt",
        source_layer="vectorbt_integration",
        purpose="Use replay diagnostics as paper execution simulation evidence.",
        side_effect_level=PURE,
        mature_framework="vectorbt_adapter",
        enabled_by_default=True,
    ),
    QuantFirmRoleSkill(
        role=DeepSeekAdvisoryRole.EXECUTION_SIMULATION_DESK,
        skill_name="execution_simulation_paper_trading_loop",
        tool_name="run_paper_trading_loop",
        source_layer="paper_trading",
        purpose="Run deterministic paper fills and account metrics from advisory order intents.",
        side_effect_level=PURE,
        mature_framework="paper_trading_loop",
        enabled_by_default=True,
    ),
    QuantFirmRoleSkill(
        role=DeepSeekAdvisoryRole.EXECUTION_SIMULATION_DESK,
        skill_name="execution_simulation_rqalpha_order_intent_placeholder",
        tool_name="rqalpha_order_intent_adapter_placeholder",
        source_layer="paper_trading",
        purpose="Disabled pure mapping placeholder for RQAlpha-style paper order semantics.",
        side_effect_level=PURE,
        mature_framework="rqalpha_order_intent_adapter",
        enabled_by_default=False,
    ),
    QuantFirmRoleSkill(
        role=DeepSeekAdvisoryRole.EXECUTION_SIMULATION_DESK,
        skill_name="execution_simulation_backtrader_order_intent_placeholder",
        tool_name="backtrader_order_intent_adapter_placeholder",
        source_layer="paper_trading",
        purpose="Disabled pure mapping placeholder for Backtrader-style paper order semantics.",
        side_effect_level=PURE,
        mature_framework="backtrader_order_intent_adapter",
        enabled_by_default=False,
    ),
    QuantFirmRoleSkill(
        role=DeepSeekAdvisoryRole.EXECUTION_SIMULATION_DESK,
        skill_name="execution_simulation_signal_backtest",
        tool_name="run_vectorbt_signal_backtest",
        source_layer="vectorbt_integration",
        purpose="Inspect simulated entries, exits, slippage, and fees without external execution.",
        side_effect_level=PURE,
        mature_framework="vectorbt_adapter",
        enabled_by_default=True,
    ),
    QuantFirmRoleSkill(
        role=DeepSeekAdvisoryRole.EXECUTION_SIMULATION_DESK,
        skill_name="execution_simulation_cost_after_fill_placeholder",
        tool_name="evaluate_cost_after_fill",
        source_layer="cost_after_fill_profitability",
        purpose="Future registry binding for cost-after-fill profitability diagnostics.",
        side_effect_level=PURE,
        mature_framework="cost_after_fill_evaluator",
        enabled_by_default=False,
    ),
    QuantFirmRoleSkill(
        role=DeepSeekAdvisoryRole.LEARNING_DESK,
        skill_name="learning_quant_firm_cycle",
        tool_name="run_quant_firm_decision_cycle",
        source_layer="quant_firm",
        purpose="Use the returned Learning Desk attribution, failure, and mutation outputs.",
        side_effect_level=PURE,
        mature_framework="mlflow_style_in_memory_experiment_tracking",
        enabled_by_default=True,
    ),
    QuantFirmRoleSkill(
        role=DeepSeekAdvisoryRole.LEARNING_DESK,
        skill_name="learning_consume_paper_loop_metrics",
        tool_name="run_paper_trading_loop",
        source_layer="paper_trading",
        purpose="Consume paper trading loop performance, rejection, and mutation metrics.",
        side_effect_level=PURE,
        mature_framework="paper_trading_loop",
        enabled_by_default=True,
    ),
    QuantFirmRoleSkill(
        role=DeepSeekAdvisoryRole.LEARNING_DESK,
        skill_name="learning_consume_walk_forward_results",
        tool_name="run_walk_forward_paper_evaluation",
        source_layer="walk_forward",
        purpose="Consume walk-forward paper results, aggregate metrics, and parameter update evidence.",
        side_effect_level=PURE,
        mature_framework="walk_forward_paper_evaluation",
        enabled_by_default=True,
    ),
    QuantFirmRoleSkill(
        role=DeepSeekAdvisoryRole.LEARNING_DESK,
        skill_name="learning_outputs_internal_adapter_placeholder",
        tool_name="learning_desk_outputs",
        source_layer="quant_firm_learning",
        purpose="Future direct binding for Learning Desk output extraction.",
        side_effect_level=PURE,
        mature_framework="mlflow_style_in_memory_experiment_tracking",
        enabled_by_default=False,
    ),
    QuantFirmRoleSkill(
        role=DeepSeekAdvisoryRole.LEARNING_DESK,
        skill_name="learning_deepseek_fallback_advice",
        tool_name="run_deepseek_advisory_fallback",
        source_layer="deepseek_advisory",
        purpose="Review attribution, failure analysis, and mutation recommendations as advisory notes.",
        side_effect_level=PURE,
        mature_framework="deepseek_advisory_fallback",
        enabled_by_default=True,
    ),
)


def _has_broker_live_scope(skill: QuantFirmRoleSkill) -> bool:
    text = " ".join(
        (
            skill.skill_name,
            skill.tool_name,
            skill.source_layer,
            skill.purpose,
            skill.mature_framework or "",
        )
    ).lower()
    forbidden = ("broker", "live_trading", "live trading", "place_order", "send_order", "execute_order")
    return any(term in text for term in forbidden)
