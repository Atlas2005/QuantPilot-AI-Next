"""Report builder for P40 AI and open-source provider replay chain."""

from __future__ import annotations

from typing import Any

from quantpilot_core.ai_open_source_provider_small_sample_mixed_etf_replay.ai_shadow_agents import (
    generate_ai_shadow_decision_set,
)
from quantpilot_core.ai_open_source_provider_small_sample_mixed_etf_replay.comparison import (
    build_open_source_backtest_handoffs,
)
from quantpilot_core.ai_open_source_provider_small_sample_mixed_etf_replay.contracts import (
    OpenSourceProviderExportSpec,
    P40AIProviderReplayReport,
)
from quantpilot_core.ai_open_source_provider_small_sample_mixed_etf_replay.open_source_provider_bridge import (
    validate_approved_provider_export,
)
from quantpilot_core.ai_open_source_provider_small_sample_mixed_etf_replay.replay_adjustment import (
    build_ai_adjusted_replay_result,
)
from quantpilot_core.real_provider_mixed_etf_paper_replay import (
    build_provider_mixed_etf_replay_report,
)


def build_p40_ai_provider_replay_report(
    spec: OpenSourceProviderExportSpec,
    records: tuple[dict[str, Any], ...],
    *,
    safety_barrier_percent: float = 140.0,
) -> P40AIProviderReplayReport:
    """Build the P40 AI shadow plus open-source provider replay report."""

    validation = validate_approved_provider_export(spec, records)
    if validation.replay_input is None:
        raise ValueError("approved provider export must validate before P40 replay report")

    baseline_replay = build_provider_mixed_etf_replay_report(
        validation.replay_input,
        safety_barrier_percent=safety_barrier_percent,
    )
    ai_decisions = generate_ai_shadow_decision_set(validation, baseline_replay)
    adjusted = build_ai_adjusted_replay_result(baseline_replay, ai_decisions)
    qlib_handoff, rqalpha_handoff = build_open_source_backtest_handoffs(spec, validation)
    return P40AIProviderReplayReport(
        approved_provider_validation=validation,
        ai_shadow_decisions=ai_decisions,
        ai_adjusted_replay=adjusted,
        qlib_handoff=qlib_handoff,
        rqalpha_handoff=rqalpha_handoff,
        used_approved_local_provider_export_style_data=validation.ok,
        provider_boundary_modeled=validation.provider_name,
        ai_shadow_agents_produced_recommendations=bool(ai_decisions.recommendations),
        meta_review_blocked_unsafe_recommendations=bool(ai_decisions.meta_blocked_roles),
        ai_shadow_adjustment_improved_paper_metrics=(
            adjusted.ai_adjustment_improved_paper_metrics
        ),
        mixed_stock_etf_remained_useful=adjusted.mixed_stock_etf_remains_default,
        created_open_source_backtest_handoffs=(
            qlib_handoff.runtime_disabled_by_default
            and rqalpha_handoff.runtime_disabled_by_default
        ),
        safety_barrier_percent=min(round(safety_barrier_percent, 4), 140.0),
        next_improvement_target=_next_target(validation, adjusted),
        evidence_refs=tuple(sorted(set(spec.evidence_refs))),
    )


def _next_target(validation, adjusted) -> str:
    if validation.blockers:
        return "real provider export quality"
    if not adjusted.ai_adjustment_improved_paper_metrics:
        return "AI alpha proposal quality"
    if adjusted.cost_drag_delta > 0:
        return "cost model realism"
    if adjusted.etf_weight_change == 0:
        return "ETF selection"
    return "Qlib backtest"
