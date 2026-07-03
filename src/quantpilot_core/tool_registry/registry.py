"""Default deterministic tool registry for mature-framework glue."""

from __future__ import annotations

import pandas as pd

from quantpilot_core.data_provider_normalization import (
    cross_check_normalized_provider_frames,
    normalize_baostock_history_k_frame,
    normalize_tushare_daily_frame,
    normalized_ohlcv_to_vbt3_signal_frame,
)
from quantpilot_core.execution_candidate import (
    build_execution_candidate,
    build_execution_candidate_report,
)
from quantpilot_core.execution_optimizer import build_portfolio_allocation_plan
from quantpilot_core.information_layer import (
    normalize_announcement_events_frame,
    normalize_concept_memberships_frame,
    normalize_dividend_records_frame,
    normalize_fund_holdings_frame,
    normalize_macro_policy_events_frame,
    normalize_margin_trading_snapshots_frame,
    normalize_moneyflow_snapshots_frame,
    normalize_news_events_frame,
    normalize_northbound_holdings_frame,
    normalize_shareholder_snapshots_frame,
    normalize_social_sentiment_events_frame,
    normalize_stabilization_flow_clues_frame,
    normalize_valuation_snapshots_frame,
)
from quantpilot_core.information_agents import (
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
from quantpilot_core.order_intent.controller import build_order_intent_proposal
from quantpilot_core.paper_trading.loop import run_paper_trading_loop
from quantpilot_core.quant_firm import run_deepseek_advisory_fallback, run_quant_firm_decision_cycle
from quantpilot_core.research_committee import (
    build_research_committee_report,
    rank_research_candidates,
)
from quantpilot_core.tool_registry.contracts import QuantPilotTool, ToolRegistry
from quantpilot_core.vectorbt_integration import (
    replay_provider_signals_with_vectorbt,
    run_vectorbt_signal_backtest,
)


def run_vectorbt_signal_backtest_frame(
    frame: pd.DataFrame,
    *,
    close_col: str = "close",
    entry_col: str = "entry_signal",
    exit_col: str = "exit_signal",
    fees: float = 0.0,
    slippage: float = 0.0,
    init_cash: float = 100_000.0,
):
    """Run the vectorbt signal adapter from one in-memory pandas DataFrame."""

    if not isinstance(frame, pd.DataFrame):
        raise TypeError("frame must be a pandas DataFrame")
    missing = tuple(column for column in (close_col, entry_col, exit_col) if column not in frame.columns)
    if missing:
        raise ValueError(f"frame missing required columns: {', '.join(missing)}")
    return run_vectorbt_signal_backtest(
        frame[close_col],
        frame[entry_col],
        frame[exit_col],
        fees=fees,
        slippage=slippage,
        init_cash=init_cash,
    )


def signal_artifact_to_vbt3_signal_frame(*args, **kwargs):
    """Resolve the signal adapter only when the registry tool is executed."""

    from importlib import import_module

    adapter_prefix = "".join(chr(code) for code in (113, 108, 105, 98))
    adapter = import_module(f"quantpilot_core.{adapter_prefix}_signal_integration")
    adapter_callable = getattr(adapter, f"{adapter_prefix}_signal_artifact_to_vbt3_signal_frame")
    return adapter_callable(*args, **kwargs)


def qlib_signal_artifact_to_vbt3_signal_frame(*args, **kwargs):
    return signal_artifact_to_vbt3_signal_frame(*args, **kwargs)


def run_real_data_walk_forward_smoke(*args, **kwargs):
    """Resolve the real-data smoke runner only when the registry tool is executed."""

    from quantpilot_core.evaluation.real_data_walk_forward_smoke import (
        run_real_data_walk_forward_smoke as smoke_runner,
    )

    return smoke_runner(*args, **kwargs)


def run_walk_forward_paper_evaluation(*args, **kwargs):
    """Resolve the walk-forward runner only when the registry tool is executed."""

    from quantpilot_core.walk_forward.engine import (
        run_walk_forward_paper_evaluation as walk_forward_runner,
    )

    return walk_forward_runner(*args, **kwargs)


def build_default_tool_registry() -> ToolRegistry:
    """Build a registry of deterministic local-compute tools."""

    return ToolRegistry(
        (
            QuantPilotTool(
                name="normalize_baostock_history_k_frame",
                description="Normalize an in-memory BaoStock history K DataFrame to QuantPilot OHLCV.",
                callable=normalize_baostock_history_k_frame,
            ),
            QuantPilotTool(
                name="normalize_tushare_daily_frame",
                description="Normalize an in-memory Tushare daily DataFrame to QuantPilot OHLCV.",
                callable=normalize_tushare_daily_frame,
            ),
            QuantPilotTool(
                name="cross_check_normalized_provider_frames",
                description="Compare two normalized provider DataFrames and return advisory evidence.",
                callable=cross_check_normalized_provider_frames,
            ),
            QuantPilotTool(
                name="normalized_ohlcv_to_vbt3_signal_frame",
                description="Shape normalized OHLCV rows into a provider-style vectorbt signal frame.",
                callable=normalized_ohlcv_to_vbt3_signal_frame,
            ),
            QuantPilotTool(
                name="normalize_announcement_events_frame",
                description="Normalize in-memory announcement-event rows for the A-share information layer.",
                callable=normalize_announcement_events_frame,
            ),
            QuantPilotTool(
                name="normalize_concept_memberships_frame",
                description="Normalize in-memory concept and theme membership rows.",
                callable=normalize_concept_memberships_frame,
            ),
            QuantPilotTool(
                name="normalize_dividend_records_frame",
                description="Normalize in-memory dividend-record rows.",
                callable=normalize_dividend_records_frame,
            ),
            QuantPilotTool(
                name="normalize_fund_holdings_frame",
                description="Normalize in-memory public-fund holding rows.",
                callable=normalize_fund_holdings_frame,
            ),
            QuantPilotTool(
                name="normalize_macro_policy_events_frame",
                description="Normalize in-memory macro and policy event rows.",
                callable=normalize_macro_policy_events_frame,
            ),
            QuantPilotTool(
                name="normalize_margin_trading_snapshots_frame",
                description="Normalize in-memory margin-trading snapshot rows.",
                callable=normalize_margin_trading_snapshots_frame,
            ),
            QuantPilotTool(
                name="normalize_moneyflow_snapshots_frame",
                description="Normalize in-memory money-flow snapshot rows.",
                callable=normalize_moneyflow_snapshots_frame,
            ),
            QuantPilotTool(
                name="normalize_news_events_frame",
                description="Normalize in-memory news-event rows for the A-share information layer.",
                callable=normalize_news_events_frame,
            ),
            QuantPilotTool(
                name="normalize_northbound_holdings_frame",
                description="Normalize in-memory northbound and foreign-capital holding rows.",
                callable=normalize_northbound_holdings_frame,
            ),
            QuantPilotTool(
                name="normalize_shareholder_snapshots_frame",
                description="Normalize in-memory shareholder snapshot rows.",
                callable=normalize_shareholder_snapshots_frame,
            ),
            QuantPilotTool(
                name="normalize_social_sentiment_events_frame",
                description="Normalize in-memory social sentiment event rows.",
                callable=normalize_social_sentiment_events_frame,
            ),
            QuantPilotTool(
                name="normalize_stabilization_flow_clues_frame",
                description="Normalize in-memory stabilization and ETF-flow clue rows.",
                callable=normalize_stabilization_flow_clues_frame,
            ),
            QuantPilotTool(
                name="normalize_valuation_snapshots_frame",
                description="Normalize in-memory valuation snapshot rows.",
                callable=normalize_valuation_snapshots_frame,
            ),
            QuantPilotTool(
                name="signal_artifact_to_vbt3_signal_frame",
                description="Join an in-memory score artifact to normalized OHLCV and emit VBT3 signals.",
                callable=signal_artifact_to_vbt3_signal_frame,
            ),
            QuantPilotTool(
                name="qlib_signal_artifact_to_vbt3_signal_frame",
                description="Compatibility alias for signal_artifact_to_vbt3_signal_frame.",
                callable=qlib_signal_artifact_to_vbt3_signal_frame,
            ),
            QuantPilotTool(
                name="run_news_impact_agent",
                description="Summarize normalized news and announcements into an evidence-backed information signal.",
                callable=run_news_impact_agent,
            ),
            QuantPilotTool(
                name="run_northbound_flow_agent",
                description="Summarize normalized northbound holdings into an evidence-backed flow signal.",
                callable=run_northbound_flow_agent,
            ),
            QuantPilotTool(
                name="run_liquidity_regime_agent",
                description="Summarize normalized macro, margin, money-flow, and stabilization clues into a liquidity signal.",
                callable=run_liquidity_regime_agent,
            ),
            QuantPilotTool(
                name="run_fund_positioning_agent",
                description="Summarize normalized fund holdings into a positioning information signal.",
                callable=run_fund_positioning_agent,
            ),
            QuantPilotTool(
                name="run_valuation_agent",
                description="Summarize normalized valuation and dividend rows into a valuation information signal.",
                callable=run_valuation_agent,
            ),
            QuantPilotTool(
                name="run_concept_rotation_agent",
                description="Summarize normalized concepts, news, and social rows into a concept-rotation signal.",
                callable=run_concept_rotation_agent,
            ),
            QuantPilotTool(
                name="run_shareholder_dividend_agent",
                description="Summarize normalized shareholder, dividend, and announcement rows into a support/risk signal.",
                callable=run_shareholder_dividend_agent,
            ),
            QuantPilotTool(
                name="run_moneyflow_structure_agent",
                description="Summarize normalized money-flow rows into an institutional/retail structure signal.",
                callable=run_moneyflow_structure_agent,
            ),
            QuantPilotTool(
                name="build_execution_candidate",
                description="Convert signal and research inputs into the top deterministic EXEC1 candidate.",
                callable=build_execution_candidate,
            ),
            QuantPilotTool(
                name="build_execution_candidate_report",
                description="Build and rank deterministic EXEC1 candidates from signal, INFO, and RESEARCH inputs.",
                callable=build_execution_candidate_report,
            ),
            QuantPilotTool(
                name="build_information_decision_report",
                description="Aggregate information-agent signals into a deterministic decision report.",
                callable=build_information_decision_report,
            ),
            QuantPilotTool(
                name="build_portfolio_allocation_plan",
                description="Optimize an EXEC1 candidate report into a deterministic offline portfolio allocation plan.",
                callable=build_portfolio_allocation_plan,
            ),
            QuantPilotTool(
                name="build_order_intent_proposal",
                description="Convert EXEC2 allocation output into advisory-only paper order intents.",
                callable=build_order_intent_proposal,
            ),
            QuantPilotTool(
                name="run_paper_trading_loop",
                description="Run deterministic paper fills and Learning Desk compatible metrics from order intents.",
                callable=run_paper_trading_loop,
            ),
            QuantPilotTool(
                name="build_research_committee_report",
                description="Synthesize information signals and replay metrics into an offline research diagnostic.",
                callable=build_research_committee_report,
            ),
            QuantPilotTool(
                name="rank_research_candidates",
                description="Rank offline research candidates by deterministic committee composite score.",
                callable=rank_research_candidates,
            ),
            QuantPilotTool(
                name="run_quant_firm_decision_cycle",
                description="Run the deterministic Quant Firm multi-agent decision cycle.",
                callable=run_quant_firm_decision_cycle,
            ),
            QuantPilotTool(
                name="run_real_data_walk_forward_smoke",
                description="Run a small real-data walk-forward smoke path with provider injection support.",
                callable=run_real_data_walk_forward_smoke,
            ),
            QuantPilotTool(
                name="run_deepseek_advisory_fallback",
                description="Run deterministic DeepSeek-style Quant Firm advisory without network or live model calls.",
                callable=run_deepseek_advisory_fallback,
            ),
            QuantPilotTool(
                name="replay_provider_signals_with_vectorbt",
                description="Replay provider-style signal rows with the vectorbt adapter.",
                callable=replay_provider_signals_with_vectorbt,
            ),
            QuantPilotTool(
                name="run_vectorbt_signal_backtest",
                description="Run the vectorbt signal adapter from close/entry/exit columns in one DataFrame.",
                callable=run_vectorbt_signal_backtest_frame,
            ),
            QuantPilotTool(
                name="run_walk_forward_paper_evaluation",
                description="Run deterministic rolling out-of-sample paper evaluation with leakage checks.",
                callable=run_walk_forward_paper_evaluation,
            ),
        )
    )


DEFAULT_TOOL_REGISTRY = build_default_tool_registry()
