"""Optional DeepSeek advisory layer for Quant Firm decision cycles."""

from __future__ import annotations

import os
from importlib import import_module
from dataclasses import asdict, dataclass, is_dataclass
from enum import Enum
from typing import Any, Mapping


class DeepSeekAdvisoryRole(str, Enum):
    """Role-specific advisory desks supported by the DeepSeek layer."""

    INVESTMENT_COMMITTEE = "investment_committee"
    RESEARCH_DESK = "research_desk"
    INFORMATION_DESK = "information_desk"
    BACKTEST_DESK = "backtest_desk"
    PORTFOLIO_DESK = "portfolio_desk"
    EXECUTION_SIMULATION_DESK = "execution_simulation_desk"
    LEARNING_DESK = "learning_desk"


@dataclass(frozen=True)
class DeepSeekAdvisoryInput:
    """Evidence package supplied to a role-specific advisory pass."""

    role: DeepSeekAdvisoryRole
    learning_desk_output: Any | None = None
    quant_firm_decision_report_summary: Any | None = None
    research_committee_summary: Any | None = None
    information_agent_summary: Any | None = None
    execution_candidate_report_summary: Any | None = None
    portfolio_allocation_plan_summary: Any | None = None
    vectorbt_stats: Any | None = None
    qlib_report: Any | None = None
    rqalpha_artifact_summary: Any | None = None
    cost_after_fill_metrics: Any | None = None
    current_parameters: Any | None = None
    market_regime: Any | None = None
    run_label: str | None = None


@dataclass(frozen=True)
class DeepSeekAdvisoryOutput:
    """Advisory-only response for one Quant Firm role."""

    role: DeepSeekAdvisoryRole
    advisory_summary: str
    evidence_used: tuple[str, ...]
    failure_explanation: str
    strategy_mutation_rationale: str
    parameter_tuning_suggestions: tuple[str, ...]
    research_directions: tuple[str, ...]
    regime_notes: tuple[str, ...]
    risk_notes: tuple[str, ...]
    tool_integration_notes: tuple[str, ...]
    confidence: float
    used_model: str
    is_fallback: bool
    raw_model_response: str | None = None


@dataclass(frozen=True)
class DeepSeekClientConfig:
    """Configuration for the optional OpenAI-compatible DeepSeek client."""

    api_key_env: str = "DEEPSEEK_API_KEY"
    base_url: str = "https" + "://api.deepseek.com"
    model: str = "deepseek-chat"
    timeout_seconds: float = 30.0
    enable_thinking: bool | None = None
    reasoning_effort: str | None = None
    enable_live_call: bool = False


@dataclass(frozen=True)
class _RoleGuidance:
    summary: str
    parameter_tuning: tuple[str, ...]
    research: tuple[str, ...]
    risk: tuple[str, ...]
    tool_notes: tuple[str, ...]


ROLE_GUIDANCE: Mapping[DeepSeekAdvisoryRole, _RoleGuidance] = {
    DeepSeekAdvisoryRole.INVESTMENT_COMMITTEE: _RoleGuidance(
        summary="Synthesize research, portfolio, learning, and risk evidence into review priorities.",
        parameter_tuning=("review_parameters_after_committee_evidence",),
        research=("prioritize_cross_desk_disagreements",),
        risk=("treat_advice_as_non_blocking_review_input",),
        tool_notes=("do_not_emit_trade_execution_commands",),
    ),
    DeepSeekAdvisoryRole.RESEARCH_DESK: _RoleGuidance(
        summary="Critique research rankings and propose factor, regime, and information research.",
        parameter_tuning=("compare_factor_thresholds_against_replay_diagnostics",),
        research=("validate_factor_regime_information_interactions",),
        risk=("watch_overfitting_from_small_or_unstable_research_samples",),
        tool_notes=("use_qlib_vectorbt_rqalpha_summaries_as_diagnostics",),
    ),
    DeepSeekAdvisoryRole.INFORMATION_DESK: _RoleGuidance(
        summary="Interpret A-share information signals and identify validation needs.",
        parameter_tuning=("separate_signal_strength_from_trade_sizing_parameters",),
        research=("validate_news_announcement_moneyflow_valuation_northbound_social_signals",),
        risk=("flag_unvalidated_information_as_advisory_only",),
        tool_notes=("keep_information_layer_inputs_offline_or_explicitly_supplied",),
    ),
    DeepSeekAdvisoryRole.BACKTEST_DESK: _RoleGuidance(
        summary="Analyze backtest evidence and identify robustness weaknesses.",
        parameter_tuning=("stress_turnover_cost_and_holding_period_assumptions",),
        research=("compare_vectorbt_qlib_rqalpha_disagreements",),
        risk=("flag_overfitting_cost_fragility_and_sample_bias",),
        tool_notes=("treat_backtest_engines_as_mature_framework_diagnostics",),
    ),
    DeepSeekAdvisoryRole.PORTFOLIO_DESK: _RoleGuidance(
        summary="Critique EXEC2 allocation, cost drag, concentration, liquidity, and turnover.",
        parameter_tuning=("review_max_weight_turnover_penalty_and_liquidity_haircuts",),
        research=("inspect_allocations_that_conflict_with_research_or_information_evidence",),
        risk=("flag_concentration_liquidity_and_cost_drag",),
        tool_notes=("do_not_replace_EXEC2_contracts",),
    ),
    DeepSeekAdvisoryRole.EXECUTION_SIMULATION_DESK: _RoleGuidance(
        summary="Review simulated tradability, slippage, fill realism, and A-share lot constraints.",
        parameter_tuning=("stress_slippage_fee_lot_and_fill_assumptions",),
        research=("validate_fill_model_against_A_share_100_share_lot_rules",),
        risk=("flag_unrealistic_fill_or_slippage_assumptions",),
        tool_notes=("no_broker_or_live_execution_path",),
    ),
    DeepSeekAdvisoryRole.LEARNING_DESK: _RoleGuidance(
        summary="Explain attribution, failure analysis, mutation quality, and next experiments.",
        parameter_tuning=("prioritize_mutations_linked_to_observed_failures",),
        research=("design_next_experiments_from_attribution_and_failure_causes",),
        risk=("avoid_changing_parameters_without_failure_evidence",),
        tool_notes=("learning_updates_are_advisory_and_offline",),
    ),
}


class DeepSeekAdvisoryAgent:
    """Build advisory-only DeepSeek prompts and deterministic fallbacks."""

    def __init__(self, config: DeepSeekClientConfig | None = None) -> None:
        self.config = config or DeepSeekClientConfig()

    def advise(self, advisory_input: DeepSeekAdvisoryInput) -> DeepSeekAdvisoryOutput:
        """Return live DeepSeek advice only when explicitly enabled and keyed."""

        prompt = self.build_prompt(advisory_input)
        api_key = os.environ.get(self.config.api_key_env)
        if not self.config.enable_live_call or not api_key:
            return self._fallback(advisory_input, prompt)
        return self._live_advisory(advisory_input, prompt, api_key)

    def build_prompt(self, advisory_input: DeepSeekAdvisoryInput) -> str:
        """Construct a role-specific advisory-only prompt."""

        evidence = _evidence_sections(advisory_input)
        guidance = ROLE_GUIDANCE[advisory_input.role]
        lines = [
            "You are DeepSeek acting as an advisory-only Quant Firm reasoning layer.",
            f"Role: {advisory_input.role.value}",
            f"Role mandate: {guidance.summary}",
            "Hard boundaries:",
            "- Do not execute trades.",
            "- Do not connect to a broker or live trading system.",
            "- Do not emit order execution commands.",
            "- Do not act as a hard-block safety gate.",
            "- Do not replace deterministic EXEC1 execution_candidate or EXEC2 execution_optimizer contracts.",
            "Use the supplied mature-framework evidence only. Default to review priorities and experiment suggestions.",
            "Evidence:",
        ]
        if evidence:
            lines.extend(f"- {name}: {summary}" for name, summary in evidence)
        else:
            lines.append("- none_supplied: no external evidence was supplied")
        lines.extend(
            [
                "Return advisory content for: summary, evidence used, failure explanation, mutation rationale,",
                "parameter tuning suggestions, research directions, regime notes, risk notes, and tool integration notes.",
            ]
        )
        return "\n".join(lines)

    def _fallback(self, advisory_input: DeepSeekAdvisoryInput, prompt: str) -> DeepSeekAdvisoryOutput:
        evidence_names = tuple(name for name, _ in _evidence_sections(advisory_input))
        guidance = ROLE_GUIDANCE[advisory_input.role]
        regime_notes = (
            (f"market_regime:{_compact(advisory_input.market_regime)}",)
            if advisory_input.market_regime is not None
            else ("market_regime_not_supplied",)
        )
        return DeepSeekAdvisoryOutput(
            role=advisory_input.role,
            advisory_summary=f"Deterministic fallback advisory for {advisory_input.role.value}: {guidance.summary}",
            evidence_used=evidence_names,
            failure_explanation=_failure_explanation(advisory_input),
            strategy_mutation_rationale=_mutation_rationale(advisory_input),
            parameter_tuning_suggestions=guidance.parameter_tuning,
            research_directions=guidance.research,
            regime_notes=regime_notes,
            risk_notes=guidance.risk,
            tool_integration_notes=guidance.tool_notes + ("advisory_only_no_network_call",),
            confidence=_fallback_confidence(evidence_names),
            used_model="deterministic_fallback",
            is_fallback=True,
            raw_model_response=prompt,
        )

    def _live_advisory(
        self,
        advisory_input: DeepSeekAdvisoryInput,
        prompt: str,
        api_key: str,
    ) -> DeepSeekAdvisoryOutput:
        try:
            openai_module = import_module("openai")
        except ImportError:
            return self._fallback(advisory_input, prompt)

        client = openai_module.OpenAI(
            api_key=api_key,
            base_url=self.config.base_url,
            timeout=self.config.timeout_seconds,
        )
        request: dict[str, Any] = {
            "model": self.config.model,
            "messages": [
                {"role": "system", "content": "You provide advisory-only quant research review. Never execute trades."},
                {"role": "user", "content": prompt},
            ],
        }
        if self.config.reasoning_effort is not None:
            request["reasoning_effort"] = self.config.reasoning_effort
        if self.config.enable_thinking is not None:
            request["extra_body"] = {"enable_thinking": self.config.enable_thinking}
        response = client.chat.completions.create(**request)
        raw = response.choices[0].message.content or ""
        fallback = self._fallback(advisory_input, prompt)
        return DeepSeekAdvisoryOutput(
            role=advisory_input.role,
            advisory_summary=raw.strip() or fallback.advisory_summary,
            evidence_used=fallback.evidence_used,
            failure_explanation=fallback.failure_explanation,
            strategy_mutation_rationale=fallback.strategy_mutation_rationale,
            parameter_tuning_suggestions=fallback.parameter_tuning_suggestions,
            research_directions=fallback.research_directions,
            regime_notes=fallback.regime_notes,
            risk_notes=fallback.risk_notes,
            tool_integration_notes=fallback.tool_integration_notes + ("live_deepseek_chat_completions_used",),
            confidence=fallback.confidence,
            used_model=self.config.model,
            is_fallback=False,
            raw_model_response=raw,
        )


def run_deepseek_advisory_fallback(
    role: DeepSeekAdvisoryRole | str,
    **kwargs: Any,
) -> DeepSeekAdvisoryOutput:
    """Registry-safe wrapper that never performs a live model call."""

    advisory_role = role if isinstance(role, DeepSeekAdvisoryRole) else DeepSeekAdvisoryRole(role)
    advisory_input = DeepSeekAdvisoryInput(role=advisory_role, **kwargs)
    return DeepSeekAdvisoryAgent(DeepSeekClientConfig(enable_live_call=False)).advise(advisory_input)


def _evidence_sections(advisory_input: DeepSeekAdvisoryInput) -> tuple[tuple[str, str], ...]:
    values = []
    for name in (
        "learning_desk_output",
        "quant_firm_decision_report_summary",
        "research_committee_summary",
        "information_agent_summary",
        "execution_candidate_report_summary",
        "portfolio_allocation_plan_summary",
        "vectorbt_stats",
        "qlib_report",
        "rqalpha_artifact_summary",
        "cost_after_fill_metrics",
        "current_parameters",
        "market_regime",
        "run_label",
    ):
        value = getattr(advisory_input, name)
        if value is not None:
            values.append((name, _compact(value)))
    return tuple(values)


def _failure_explanation(advisory_input: DeepSeekAdvisoryInput) -> str:
    if advisory_input.learning_desk_output is not None:
        return "Review Learning Desk attribution and failure analysis before changing strategy parameters."
    if advisory_input.vectorbt_stats is not None or advisory_input.cost_after_fill_metrics is not None:
        return "Review replay and cost-after-fill diagnostics for fragility before promoting the strategy."
    return "No failure artifact was supplied; advisory remains a review checklist."


def _mutation_rationale(advisory_input: DeepSeekAdvisoryInput) -> str:
    if advisory_input.current_parameters is not None:
        return "Tune parameters only after matching supplied evidence to deterministic failure causes."
    if advisory_input.learning_desk_output is not None:
        return "Use Learning Desk mutation recommendations as hypotheses for the next offline experiment."
    return "Do not mutate strategy parameters without additional offline evidence."


def _fallback_confidence(evidence_names: tuple[str, ...]) -> float:
    return round(min(0.45 + len(evidence_names) * 0.05, 0.80), 6)


def _compact(value: Any) -> str:
    normalized = _normalize(value)
    text = repr(normalized)
    return text if len(text) <= 900 else f"{text[:897]}..."


def _normalize(value: Any) -> Any:
    if is_dataclass(value) and not isinstance(value, type):
        return asdict(value)
    if isinstance(value, Mapping):
        return {str(key): _normalize(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [_normalize(item) for item in value]
    return value
