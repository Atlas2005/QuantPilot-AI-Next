# ALIGN1 Architecture Alignment Audit

## Executive Judgment

QuantPilot-AI-Next is now mostly aligned with the corrected vision at the default-tool boundary: the default registry favors normalized A-share provider data, Qlib-style signal artifacts, INFO agents, RESEARCH committee diagnostics, and vectorbt replay/backtest adapters.

No source modules are safe to delete in ALIGN1. The legacy safety/replay modules are still imported by tests, bridge modules, or historical documents. Deleting them now would create churn without improving the profit-first path.

Safe pruning performed in ALIGN1 is therefore registry/path pruning by confirmation: the default `ToolRegistry` does not register old gate, preflight, readiness, sandbox, release-hardening, DeepSeek, or self-built replay entry points. Tests now lock in that mature replacement path.

## Phase-By-Phase Alignment Judgment

| Phase family | Current alignment | Judgment |
| --- | --- | --- |
| Early R7-R30 preflight/sandbox/readiness | Useful as historical diagnostics, but not the target architecture. These modules risk encouraging no-trade behavior if promoted back into default orchestration. | Keep out of default paths. Downgrade to advisory/config/sizing unless the check represents impossible execution or explicit broker/live risk. |
| Cleanup R1/R2 | Directionally correct. Cleanup already downgraded many provenance, metadata, and readiness blockers into warnings or manual-review evidence. | Preserve. Do not add new gates or readiness layers. |
| Vectorbt replacement | Strong alignment. `vectorbt_integration` and provider-facing vectorbt replay are the default backtest/replay direction for local research metrics. | Prefer over C1/C2/C3 self-built replay. |
| BaoStock/Tushare normalized data | Strong alignment. Provider normalization is the right boundary for organizing A-share price-relevant information without fetching external data in default tools. | Keep in default registry. |
| Qlib-style signal bridge | Strong alignment. Qlib artifacts can feed vectorbt replay through a thin adapter. | Keep in default registry and expand toward factor/model optimization. |
| INFO1/INFO2/INFO3 | Strong alignment. Information agents organize stock-price-relevant non-price evidence into deterministic signals. | Preserve behavior; continue broadening source coverage through normalized frames. |
| RESEARCH1 | Strong alignment. Research committee adds institution-like synthesis without calling model APIs or creating execution gates. | Keep in default registry as advisory research/ranking. |
| RQAlpha prototype/review work | Partial alignment. Useful for event-driven A-share semantics, but not default runtime. | Keep as optional/prototype/advisory until a clean framework-backed path is ready. |

## Over-Safety / No-Trade Risk Inventory

| Area | Risk | ALIGN1 classification | Recommendation |
| --- | --- | --- | --- |
| `provider_probe_gate` | Provider metadata and review gaps can become a data-acquisition blocker. | B, E | Keep as provider policy diagnostics; do not register as a default trading or research blocker. |
| `small_sample_data_gate` | Historical R4/R3/R2 provenance references can overblock usable normalized data. | B, E | Keep data-shape validation; keep provenance messages advisory. |
| `data.real_data_readiness` | Readiness wording can imply global approval/no-approval architecture. | A, E | Keep for legacy fixture validation only; do not wire into default registry/orchestration. |
| `provider_sample_fetch_preflight` | Sample-size and metadata checks can block exploratory learning loops. | B, E | Treat as sample-quality warnings unless normalized bars are structurally unusable. |
| `pit_feature_store_preflight` | PIT checks are valuable, but can become an endless readiness layer. | A, E | Keep as leakage diagnostic, not a global preflight layer. |
| `account_profile_preflight` | Account checks can block paper research when used outside execution context. | A, E | Keep only for account/broker-specific contexts; keep out of research defaults. |
| `small_capital_readiness_gate` | Capital metrics can become a central no-trade gate. | B, E | Use as sizing/capital diagnostics; do not let it block signal research. |
| `broker_sandbox_adapter_preflight` | Sandbox readiness language can pull the project toward broker/live architecture. | A, E | Keep only as adapter-config review. Do not extend broker/live/mod-ctp/vn.py paths. |
| `final_readiness_release_hardening` | Release hardening can resurrect old historical gates as launch blockers. | B, E | Keep as documentation/release diagnostic only; do not make it default runtime policy. |
| `deepseek_multi_agent` | Required gates and sandbox-only constraints can overfit the old AI-agent safety model. | C, E | Replace default AI flow with INFO/RESEARCH deterministic local tools. Do not call model APIs. |
| `multi_day_paper_replay` | Self-built replay can compete with vectorbt and preserve obsolete preflight coupling. | C, E | Keep for legacy comparison only; prefer vectorbt default. |
| `real_provider_mixed_etf_paper_replay` | Old provider replay chain is replaced by provider/vectorbt replay. | C, E | Keep as legacy/reference while tests depend on it. |
| `gate_pruning_tradability_fill_loop` | The name and policy records preserve gate-centric thinking. | A, C, E | Keep as an audit artifact and tradability/fill diagnostic; avoid default orchestration. |
| `vectorbt_old_chain_metrics_comparison` | Useful only to prove replacement equivalence. | A, E | Keep as migration audit until old-chain tests are retired. |

## Mature Replacement Mapping

| Legacy/self-built area | Mature or aligned replacement |
| --- | --- |
| C1 legacy provider paper replay: `real_provider_mixed_etf_paper_replay` | `provider_vectorbt_replay`, `vectorbt_replay_adapter`, `vectorbt_integration.replay_provider_signals_with_vectorbt` |
| C2 legacy daily replay/fill chain: `daily_paper_trading_loop_tradability_metrics`, `gate_pruning_tradability_fill_loop`, `mixed_stock_etf_daily_paper_evaluation`, `qlib_offline_tradability_evaluation_fixture` | vectorbt for portfolio replay metrics; Qlib for research signals; RQAlpha only for optional event-driven A-share semantics |
| C3 paper ledger dry-run replay: `paper_ledger_dry_run`, `multi_day_paper_replay`, `executable_candidate_paper_bridge` | vectorbt-backed research replay now; future broker/paper-ledger boundary only when explicitly scoped |
| DeepSeek-era multi-agent contract preflight | INFO agents plus RESEARCH committee local deterministic synthesis |
| Provider readiness/gate layers | BaoStock/Tushare normalized provider frames plus advisory cross-check reports |
| Qlib preflight/runtime spike artifacts | `qlib_signal_integration` bridge now; future controlled Qlib runtime as optional framework path |
| Release-hardening readiness matrix | Targeted smoke tests and registry contract tests, not global readiness blockers |

## Keep / Downgrade / Replace / Delete Recommendations

| Module or family | Recommendation | Reason |
| --- | --- | --- |
| `tool_registry` default tools | Keep mature default path | Already registers provider normalization, information normalization, INFO agents, RESEARCH committee, Qlib bridge, and vectorbt replay/backtest only. |
| `information_agents`, `information_layer` | Keep and expand | They directly serve all-stock-price-relevant information fusion. |
| `research_committee` | Keep and expand | It matches institution-like research committee synthesis without model API calls or execution gates. |
| `qlib_signal_integration` | Keep | Thin adapter to mature Qlib-style signal output. |
| `vectorbt_integration`, `provider_vectorbt_replay`, `vectorbt_replay_adapter` | Keep and prefer | Framework-backed replay should replace old self-built replay defaults. |
| `rqalpha_*` review/adapter modules | Keep as optional/prototype | Useful mature-framework direction, but current code is still review/adapter evidence. |
| `provider_probe_gate`, `small_sample_data_gate`, `provider_sample_fetch_preflight` | Downgrade/keep advisory | Retain data-quality diagnostics; avoid blocking usable normalized data. |
| `small_capital_readiness_gate` | Downgrade to sizing/advisory | Capital metrics should influence sizing and cost-aware decisions, not central no-trade outcomes. |
| `broker_sandbox_adapter_preflight`, `account_profile_preflight` | Keep isolated | Valid only for account/broker sandbox config contexts, not default research. |
| `final_readiness_release_hardening` | Downgrade to release checklist | Avoid resurrecting historical readiness gates. |
| `deepseek_multi_agent` | Replace in default architecture | INFO/RESEARCH local tools now cover the aligned agent direction without model APIs. |
| `multi_day_paper_replay`, `real_provider_mixed_etf_paper_replay`, C1/C2/C3 old chain | Replace as default, keep compatibility | Tests/imports still depend on them; not safe to delete yet. |
| Source deletion | Do not delete in ALIGN1 | No inspected legacy source family met the standard of no imports, no tests, and no documented current use. |

## Default Registry / Orchestration Finding

The default `ToolRegistry` path should remain pure local compute and should not register:

- gate/preflight/readiness/sandbox/release-hardening tools,
- DeepSeek/OpenAI/Anthropic/model runtime tools,
- broker/live/mod-ctp/vn.py tools,
- legacy C1/C2/C3 replay entry points.

ALIGN1 tests confirm the default registry prefers:

- BaoStock/Tushare normalization,
- normalized provider-to-vectorbt signal shaping,
- Qlib signal artifact integration,
- INFO information-decision agents,
- RESEARCH committee diagnostics/ranking,
- vectorbt replay/backtest tools.

## Safe Legacy Pruning Performed

No source module was deleted. No default registry tool had to be removed because the currently inspected registry does not expose the legacy blockers or old replay entry points.

The safe pruning outcome is a locked default path: tests now fail if old blockers are added back to the default registry or if the registry source grows a new hard-blocking safety layer.

## Next AI Optimization Roadmap

1. Build a unified candidate scorecard that fuses price factors, Qlib scores, INFO signals, research committee scores, transaction costs, slippage assumptions, and fill realism.
2. Add deterministic parameter-search loops over Qlib thresholds, top-N selection, holding period, rebalance cadence, fees, slippage, and stop/exit logic using vectorbt metrics.
3. Promote cost-after-fill profitability as the primary objective: optimize net profit, drawdown, turnover, hit rate, and rejected-fill sensitivity together.
4. Expand INFO agents toward event taxonomy coverage: earnings, guidance, policy, industry chain, fund flows, northbound changes, valuation, shareholder/dividend signals, social/news regime shifts.
5. Keep RQAlpha as the next mature-framework candidate for event-driven A-share market semantics only after vectorbt/Qlib signal and cost loops are stable.
6. Convert old C1/C2/C3 modules into migration tests or archived docs once their current tests/imports are replaced by vectorbt/Qlib/RQAlpha equivalents.
7. Add an optimization controller that ranks experiments by expected learning value and compute cost, without introducing model API calls or blocking readiness gates.
