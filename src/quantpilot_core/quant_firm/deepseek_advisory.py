"""Optional DeepSeek advisory layer for Quant Firm decision cycles."""

from __future__ import annotations

import os
from importlib import import_module
from dataclasses import asdict, dataclass, field, is_dataclass
from enum import Enum
from typing import Any, Callable, Mapping

from quantpilot_core.deepseek_multi_agent.runtime_contracts import (
    DEEPSEEK_V4_FLASH,
    DEEPSEEK_V4_PRO,
    DEPRECATED_DEEPSEEK_MODELS,
)


class DeepSeekAdvisoryRole(str, Enum):
    """Role-specific advisory desks supported by the DeepSeek layer."""

    INVESTMENT_COMMITTEE = "investment_committee"
    RESEARCH_DESK = "research_desk"
    INFORMATION_DESK = "information_desk"
    BACKTEST_DESK = "backtest_desk"
    PORTFOLIO_DESK = "portfolio_desk"
    EXECUTION_SIMULATION_DESK = "execution_simulation_desk"
    LEARNING_DESK = "learning_desk"


_FLASH_ADVISORY_ROLES = frozenset(
    {
        DeepSeekAdvisoryRole.INFORMATION_DESK,
        DeepSeekAdvisoryRole.BACKTEST_DESK,
        DeepSeekAdvisoryRole.EXECUTION_SIMULATION_DESK,
    }
)
_MEDIUM_PRO_ADVISORY_ROLES = frozenset(
    {
        DeepSeekAdvisoryRole.RESEARCH_DESK,
        DeepSeekAdvisoryRole.PORTFOLIO_DESK,
    }
)
_HIGH_PRO_ADVISORY_ROLES = frozenset(
    {
        DeepSeekAdvisoryRole.LEARNING_DESK,
        DeepSeekAdvisoryRole.INVESTMENT_COMMITTEE,
    }
)
_PRO_ADVISORY_ROLES = _MEDIUM_PRO_ADVISORY_ROLES | _HIGH_PRO_ADVISORY_ROLES


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
    raw_response_usage: Mapping[str, Any] | None = None


@dataclass(frozen=True)
class DeepSeekClientConfig:
    """Configuration for the optional OpenAI-compatible DeepSeek client."""

    api_key_env: str = "DEEPSEEK_API_KEY"
    base_url: str = "https" + "://api.deepseek.com"
    model: str = DEEPSEEK_V4_FLASH
    timeout_seconds: float = 30.0
    enable_thinking: bool | None = None
    reasoning_effort: str | None = None
    enable_live_call: bool = False
    _model_was_explicit: bool = field(default=False, repr=False, compare=False)
    _model_normalization_warnings: tuple[str, ...] = field(
        default=(),
        repr=False,
        compare=False,
    )

    def __init__(
        self,
        api_key_env: str = "DEEPSEEK_API_KEY",
        base_url: str = "https" + "://api.deepseek.com",
        model: str | None = None,
        timeout_seconds: float = 30.0,
        enable_thinking: bool | None = None,
        reasoning_effort: str | None = None,
        enable_live_call: bool = False,
    ) -> None:
        default_model = os.environ.get("DEEPSEEK_MODEL_DEFAULT", DEEPSEEK_V4_FLASH)
        normalized = _normalize_deepseek_model(model or default_model)
        object.__setattr__(self, "api_key_env", api_key_env)
        object.__setattr__(self, "base_url", base_url)
        object.__setattr__(self, "model", normalized.model)
        object.__setattr__(self, "timeout_seconds", timeout_seconds)
        object.__setattr__(self, "enable_thinking", enable_thinking)
        object.__setattr__(self, "reasoning_effort", reasoning_effort)
        object.__setattr__(self, "enable_live_call", enable_live_call)
        object.__setattr__(self, "_model_was_explicit", model is not None)
        object.__setattr__(self, "_model_normalization_warnings", normalized.warnings)


class DeepSeekStructuredEvidenceClient:
    """Structured-response adapter for explicitly enabled Quant Firm live calls."""

    def __init__(self, config: DeepSeekClientConfig | None = None) -> None:
        self.config = config or DeepSeekClientConfig(enable_live_call=True)
        self.physical_request_count = 0

    def __call__(self, request: Mapping[str, Any]) -> Mapping[str, Any]:
        credential = os.environ.get(self.config.api_key_env)
        if not self.config.enable_live_call or not credential:
            raise RuntimeError("live DeepSeek structured evidence requires enabled Quant Firm configuration")
        try:
            openai_module = import_module("openai")
        except ImportError as exc:
            raise RuntimeError("OpenAI-compatible runtime is unavailable") from exc
        client = openai_module.OpenAI(
            api_key=credential,
            base_url=self.config.base_url,
            timeout=self.config.timeout_seconds,
        )
        self.physical_request_count += 1
        response = client.chat.completions.create(
            model=request["model"],
            messages=request["messages"],
            response_format={"type": "json_object"},
            reasoning_effort=request.get("reasoning_mode"),
            extra_body={"enable_thinking": request.get("enable_thinking", False)},
        )
        choice = response.choices[0]
        usage = getattr(response, "usage", None)
        return {
            "content": choice.message.content,
            "finish_reason": choice.finish_reason,
            "model": str(getattr(response, "model", "") or request["model"]),
            "usage": {
                "prompt_tokens": getattr(usage, "prompt_tokens", 0),
                "prompt_cache_hit_tokens": getattr(usage, "prompt_cache_hit_tokens", 0),
                "prompt_cache_miss_tokens": getattr(usage, "prompt_cache_miss_tokens", None),
                "completion_tokens": getattr(usage, "completion_tokens", 0),
            },
        }


def create_live_structured_evidence_client(
    config: DeepSeekClientConfig | None = None,
) -> DeepSeekStructuredEvidenceClient:
    """Return the approved Quant Firm structured-response adapter for the CLI."""

    return DeepSeekStructuredEvidenceClient(config)


@dataclass(frozen=True)
class QuantFirmDeepSeekModelSelection:
    """Resolved advisory model settings for a Quant Firm role."""

    model: str
    enable_thinking: bool
    reasoning_effort: str
    warnings: tuple[str, ...] = ()


@dataclass(frozen=True)
class QuantFirmDeepSeekModelPolicy:
    """Role-based DeepSeek V4 model policy for advisory-only Quant Firm desks."""

    default_model: str = DEEPSEEK_V4_FLASH
    flash_model: str = DEEPSEEK_V4_FLASH
    pro_model: str = DEEPSEEK_V4_PRO
    reasoning_effort_default: str = "low"

    @classmethod
    def from_environment(cls) -> "QuantFirmDeepSeekModelPolicy":
        return cls(
            default_model=os.environ.get("DEEPSEEK_MODEL_DEFAULT", DEEPSEEK_V4_FLASH),
            flash_model=os.environ.get("DEEPSEEK_MODEL_FLASH", DEEPSEEK_V4_FLASH),
            pro_model=os.environ.get("DEEPSEEK_MODEL_PRO", DEEPSEEK_V4_PRO),
            reasoning_effort_default=os.environ.get(
                "DEEPSEEK_REASONING_EFFORT_DEFAULT",
                "low",
            ),
        )

    def selection_for(
        self,
        role: DeepSeekAdvisoryRole,
        config: DeepSeekClientConfig | None = None,
    ) -> QuantFirmDeepSeekModelSelection:
        base = self._role_selection(role)
        warnings = list(base.warnings)
        model = base.model
        if config is not None and config._model_was_explicit:
            normalized = _normalize_deepseek_model(config.model, policy=self)
            model = normalized.model
            warnings.extend(config._model_normalization_warnings)
            warnings.extend(normalized.warnings)
        elif role in _FLASH_ADVISORY_ROLES:
            normalized = _normalize_deepseek_model(self.flash_model, policy=self)
            model = normalized.model
            warnings.extend(normalized.warnings)
        elif role in _PRO_ADVISORY_ROLES:
            normalized = _normalize_deepseek_model(self.pro_model, policy=self)
            model = normalized.model
            warnings.extend(normalized.warnings)
        else:
            normalized = _normalize_deepseek_model(self.default_model, policy=self)
            model = normalized.model
            warnings.extend(normalized.warnings)

        enable_thinking = base.enable_thinking
        reasoning_effort = base.reasoning_effort
        if config is not None and config.enable_thinking is not None:
            enable_thinking = config.enable_thinking
        if config is not None and config.reasoning_effort is not None:
            reasoning_effort = config.reasoning_effort
        return QuantFirmDeepSeekModelSelection(
            model=model,
            enable_thinking=enable_thinking,
            reasoning_effort=reasoning_effort,
            warnings=tuple(warnings),
        )

    def normalize_requested_model(self, model: str) -> QuantFirmDeepSeekModelSelection:
        normalized = _normalize_deepseek_model(model, policy=self)
        return QuantFirmDeepSeekModelSelection(
            model=normalized.model,
            enable_thinking=normalized.model == self.pro_model,
            reasoning_effort=self.reasoning_effort_default,
            warnings=normalized.warnings,
        )

    def _role_selection(self, role: DeepSeekAdvisoryRole) -> QuantFirmDeepSeekModelSelection:
        if role in _FLASH_ADVISORY_ROLES:
            return QuantFirmDeepSeekModelSelection(
                model=self.flash_model,
                enable_thinking=False,
                reasoning_effort=self.reasoning_effort_default,
            )
        if role in _MEDIUM_PRO_ADVISORY_ROLES:
            return QuantFirmDeepSeekModelSelection(
                model=self.pro_model,
                enable_thinking=True,
                reasoning_effort="medium",
            )
        return QuantFirmDeepSeekModelSelection(
            model=self.pro_model,
            enable_thinking=True,
            reasoning_effort="high",
        )


@dataclass(frozen=True)
class _NormalizedDeepSeekModel:
    model: str
    warnings: tuple[str, ...] = ()


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


JSON_OUTPUT_CONTRACT_LINES = (
    "Structured JSON output requirements:",
    "Return exactly one valid JSON object.",
    "The response must be JSON only.",
    "Do not use Markdown code fences.",
    "Do not include prose before or after the JSON object.",
    'Use the JSON object keys: "advisory_summary", "evidence_used", "failure_explanation",'
    " \"strategy_mutation_rationale\", \"parameter_tuning_suggestions\", \"research_directions\","
    ' "regime_notes", "risk_notes", "tool_integration_notes", "confidence".',
)


class DeepSeekAdvisoryAgent:
    """Build advisory-only DeepSeek prompts and deterministic fallbacks."""

    def __init__(
        self,
        config: DeepSeekClientConfig | None = None,
        *,
        live_client: Callable[[Mapping[str, Any]], Mapping[str, Any]] | None = None,
    ) -> None:
        self.config = config or DeepSeekClientConfig()
        self.model_policy = QuantFirmDeepSeekModelPolicy.from_environment()
        self.live_client = live_client or create_live_structured_evidence_client(
            self.config
        )

    @property
    def physical_model_calls(self) -> int:
        """Requests that reached the real chat-completions call boundary."""

        value = getattr(self.live_client, "physical_request_count", 0)
        try:
            return max(0, int(value))
        except (TypeError, ValueError):
            return 0

    def advise(self, advisory_input: DeepSeekAdvisoryInput) -> DeepSeekAdvisoryOutput:
        """Return live DeepSeek advice only when explicitly enabled and keyed."""

        prompt = self.build_prompt(advisory_input)
        model_selection = self.model_policy.selection_for(advisory_input.role, self.config)
        api_key = os.environ.get(self.config.api_key_env)
        if not self.config.enable_live_call or not api_key:
            return self._fallback(advisory_input, prompt, model_selection)
        return self._live_advisory(advisory_input, prompt, model_selection)

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
        # Shared JSON-mode contract. DeepSeek requires the literal word "json" in
        # the provider-visible messages whenever response_format json_object is used.
        lines.extend(JSON_OUTPUT_CONTRACT_LINES)
        structured_schema = _announcement_structured_schema(advisory_input)
        if structured_schema:
            lines.extend(structured_schema)
        return "\n".join(lines)

    def _fallback(
        self,
        advisory_input: DeepSeekAdvisoryInput,
        prompt: str,
        model_selection: QuantFirmDeepSeekModelSelection | None = None,
    ) -> DeepSeekAdvisoryOutput:
        evidence_names = tuple(name for name, _ in _evidence_sections(advisory_input))
        guidance = ROLE_GUIDANCE[advisory_input.role]
        regime_notes = (
            (f"market_regime:{_compact(advisory_input.market_regime)}",)
            if advisory_input.market_regime is not None
            else ("market_regime_not_supplied",)
        )
        selection_notes = _model_selection_notes(model_selection)
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
            tool_integration_notes=guidance.tool_notes
            + selection_notes
            + ("advisory_only_no_network_call",),
            confidence=_fallback_confidence(evidence_names),
            used_model="deterministic_fallback",
            is_fallback=True,
            raw_model_response=prompt,
            raw_response_usage=None,
        )

    def _live_advisory(
        self,
        advisory_input: DeepSeekAdvisoryInput,
        prompt: str,
        model_selection: QuantFirmDeepSeekModelSelection,
    ) -> DeepSeekAdvisoryOutput:
        request: dict[str, Any] = {
            "model": model_selection.model,
            "messages": [
                {
                    "role": "system",
                    "content": "You provide advisory-only quant research review. Never execute trades. Return structured JSON advisory output only.",
                },
                {"role": "user", "content": prompt},
            ],
            "reasoning_mode": model_selection.reasoning_effort,
            "enable_thinking": model_selection.enable_thinking,
        }
        response = self.live_client(request)
        if not isinstance(response, Mapping):
            raise RuntimeError("DeepSeek live transport returned a non-object response")
        raw = str(response.get("content") or "")
        model = str(response.get("model") or "").strip()
        usage = response.get("usage")
        if not model:
            raise RuntimeError("DeepSeek live transport response omitted model")
        if not isinstance(usage, Mapping):
            raise RuntimeError("DeepSeek live transport response omitted usage")
        fallback = self._fallback(advisory_input, prompt, model_selection)
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
            tool_integration_notes=fallback.tool_integration_notes
            + ("live_deepseek_chat_completions_used",),
            confidence=fallback.confidence,
            used_model=model,
            is_fallback=False,
            raw_model_response=raw,
            raw_response_usage=usage,
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


def _normalize_deepseek_model(
    model: str,
    policy: QuantFirmDeepSeekModelPolicy | None = None,
) -> _NormalizedDeepSeekModel:
    if model == "deepseek-chat":
        flash_model = (
            policy.flash_model
            if policy is not None
            else os.environ.get("DEEPSEEK_MODEL_FLASH", DEEPSEEK_V4_FLASH)
        )
        return _NormalizedDeepSeekModel(
            model=flash_model,
            warnings=("deprecated_model_normalized:deepseek-chat->deepseek-v4-flash",),
        )
    if model == "deepseek-reasoner":
        pro_model = (
            policy.pro_model
            if policy is not None
            else os.environ.get("DEEPSEEK_MODEL_PRO", DEEPSEEK_V4_PRO)
        )
        return _NormalizedDeepSeekModel(
            model=pro_model,
            warnings=("deprecated_model_normalized:deepseek-reasoner->deepseek-v4-pro",),
        )
    if model in DEPRECATED_DEEPSEEK_MODELS:
        return _NormalizedDeepSeekModel(
            model=DEEPSEEK_V4_FLASH,
            warnings=(f"deprecated_model_normalized:{model}->deepseek-v4-flash",),
        )
    return _NormalizedDeepSeekModel(model=model)


def _model_selection_notes(
    model_selection: QuantFirmDeepSeekModelSelection | None,
) -> tuple[str, ...]:
    if model_selection is None:
        return ()
    thinking = "enabled" if model_selection.enable_thinking else "disabled"
    return (
        f"deepseek_model:{model_selection.model}",
        f"deepseek_thinking:{thinking}",
        f"deepseek_reasoning_effort:{model_selection.reasoning_effort}",
    ) + model_selection.warnings


def _response_usage(response: Any) -> Mapping[str, Any] | None:
    usage = getattr(response, "usage", None)
    if usage is None and isinstance(response, Mapping):
        usage = response.get("usage")
    if usage is None:
        return None
    if isinstance(usage, Mapping):
        return dict(usage)
    if is_dataclass(usage) and not isinstance(usage, type):
        return asdict(usage)
    model_dump = getattr(usage, "model_dump", None)
    if callable(model_dump):
        dumped = model_dump()
        return dict(dumped) if isinstance(dumped, Mapping) else None
    result: dict[str, Any] = {}
    for key in (
        "prompt_tokens",
        "completion_tokens",
        "total_tokens",
        "prompt_tokens_details",
        "completion_tokens_details",
    ):
        if hasattr(usage, key):
            result[key] = getattr(usage, key)
    return result or None


def _announcement_structured_schema(advisory_input: DeepSeekAdvisoryInput) -> tuple[str, ...]:
    if advisory_input.role is not DeepSeekAdvisoryRole.INFORMATION_DESK:
        return ()
    summary = advisory_input.information_agent_summary
    if not isinstance(summary, Mapping) or not summary.get("announcement_structured_output_schema"):
        return ()
    return (
        "Announcement-specific output requirement:",
        "Return exactly one JSON object and no markdown or prose outside JSON.",
        'Required JSON keys: "direction", "horizon", "severity", "confidence", "evidence", "rationale", "limitations".',
        "direction must be one of: positive, negative, neutral, mixed, uncertain.",
        "horizon must be one of: immediate, short_term, medium_term.",
        "severity and confidence must be numbers from 0.0 to 1.0.",
        "evidence and limitations must be arrays of short strings.",
        "rationale must be a concise final rationale, not hidden reasoning or chain-of-thought.",
        "Do not include expected returns, profitability claims, broker actions, or orders.",
    )


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
