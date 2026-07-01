# Cleanup Self-Built Boundaries R1

## Deleted Modules

This cleanup batch deleted obsolete self-built preflight modules and their tests:

- `src/quantpilot_core/qlib_evaluation_preflight`
- `tests/qlib_evaluation_preflight`
- `src/quantpilot_core/rqalpha_adapter_preflight`
- `tests/rqalpha_adapter_preflight`
- `src/quantpilot_core/multi_agent_orchestrator_preflight`
- `tests/multi_agent_orchestrator_preflight`
- `src/quantpilot_core/news_event_agent_preflight`
- `tests/news_event_agent_preflight`
- `src/quantpilot_core/stats_agent_factor_metrics_preflight`
- `tests/stats_agent_factor_metrics_preflight`
- `src/quantpilot_core/performance_attribution_preflight`
- `tests/performance_attribution_preflight`

## Why They Were Deleted

These modules were self-built preflight and evaluation boundaries that made QuantPilot overly conservative. They added historical readiness checks without moving the system closer to controlled executable trading.

Safety must not mean no trading. Safety should block fatal operational errors such as credential leakage, live broker paths before approval, insufficient cash, invalid sellable quantity, price-limit violations, suspension, and impossible order/fill assumptions. It should not block normal strategy execution, paper replay, controlled dry-run progression, or mature framework integration.

AI is for profitability optimization, strategy improvement, parameter tuning, execution realism, and continuous improvement. AI must not become another blocking preflight layer.

## Mature Framework Replacement Path

The deleted capabilities should be replaced by mature frameworks wherever practical:

- Qlib for AI quant workflow and factor research.
- vectorbt for fast portfolio replay and backtesting.
- RQAlpha for A-share-style backtest and trading simulation.
- quantstats and empyrical for performance attribution.
- LangGraph, AutoGen, or CrewAI plus the DeepSeek API for AI agent orchestration.

QuantPilot-owned code should remain focused on contracts, adapters, glue, A-share market reality constraints, account/capital constraints, safety checks for fatal operational errors, orchestration boundaries, and validation layers around mature integrations.

## Final Readiness Refactor

`final_readiness_release_hardening` no longer requires the deleted historical preflight modules or their documents.

The remaining checks should not imply that missing Qlib, RQAlpha, DeepSeek, attribution, or orchestration preflight modules block trading progress. If a check is only a historical preflight blocker, it should be removed rather than replaced with another blocker.

## Explicit Next Cleanup Targets

The next cleanup candidates are:

- `provider_probe_gate`
- `small_sample_data_gate`
- `small_capital_readiness_gate`
- `broker_sandbox_adapter_preflight`
- `gate_pruning_tradability_fill_loop`
- `explicit_fill_simulation_boundary`
- `executable_candidate_paper_bridge`

Each future cleanup should preserve fatal operational safety while reducing overblocking and moving QuantPilot toward controlled executable A-share and ETF trading.
