# R30 Final Readiness / Release Hardening

R30 closes the preflight/sandbox MVP by adding a deterministic final readiness report layer.

It inventories required modules, verifies required documentation, checks explicit forbidden-scope evidence, and emits a structured final readiness decision before any post-MVP work moves toward real data stability trials, optional runtime integrations, or broker research.

R30 does not call DeepSeek, call the network, connect to brokers, place orders, mutate accounts, run Qlib, run RQAlpha, train models, update live strategy weights, or add broker SDKs as required dependencies.

## What R30 Checks

R30 produces release checks for:

- input shape and release evidence
- required module importability
- required document presence
- explicit forbidden-scope evidence

Repository-wide scanning is intentionally not part of R30. The package validates the provided `ForbiddenScopeCheck` objects deterministically. A broader repository scan belongs in a future CI hardening step with carefully reviewed exclusions.

## Required Module Inventory

The default module inventory covers the preflight/sandbox MVP surface:

- `quantpilot_core.small_sample_data_gate`
- `quantpilot_core.real_data_provider`
- `quantpilot_core.provider_fallback_selector`
- `quantpilot_core.provider_sample_fetch_preflight`
- `quantpilot_core.rqalpha_adapter_preflight`
- `quantpilot_core.paper_ledger`
- `quantpilot_core.deepseek_multi_agent`
- `quantpilot_core.pit_feature_store_preflight`
- `quantpilot_core.news_event_agent_preflight`
- `quantpilot_core.account_profile_preflight`
- `quantpilot_core.ai_action_paper_bridge`
- `quantpilot_core.paper_ledger_dry_run`
- `quantpilot_core.multi_day_paper_replay`
- `quantpilot_core.performance_attribution_preflight`
- `quantpilot_core.small_capital_readiness_gate`
- `quantpilot_core.broker_sandbox_adapter_preflight`
- `quantpilot_core.multi_agent_orchestrator_preflight`
- `quantpilot_core.stats_agent_factor_metrics_preflight`
- `quantpilot_core.qlib_evaluation_preflight`

Required module checks import only the explicitly listed module paths.

## Required Document Inventory

The default document inventory covers:

- `docs/PIT_DATA_FEATURE_STORE_PREFLIGHT.md`
- `docs/NEWS_EVENT_AGENT_PREFLIGHT.md`
- `docs/ACCOUNT_PROFILE_BROKER_CONFIG_PREFLIGHT.md`
- `docs/AI_ACTION_PROPOSAL_PAPER_LEDGER_BRIDGE.md`
- `docs/PAPER_LEDGER_DRY_RUN_INTEGRATION.md`
- `docs/MULTI_DAY_PAPER_REPLAY.md`
- `docs/PERFORMANCE_ATTRIBUTION_FLYWHEEL_PREFLIGHT.md`
- `docs/SMALL_CAPITAL_READINESS_GATE.md`
- `docs/BROKER_SANDBOX_ADAPTER_PREFLIGHT.md`
- `docs/MULTI_AGENT_ORCHESTRATOR_PREFLIGHT.md`
- `docs/STATS_AGENT_FACTOR_METRICS_PREFLIGHT.md`
- `docs/QLIB_EVALUATION_PREFLIGHT.md`

Document checks use explicit `Path.exists` checks only for the listed files.

## Forbidden-Scope Checks

R30 validates provided forbidden-scope evidence strings for signals such as order placement, live trading, broker SDK usage, runtime Qlib commands, network calls, live model training, and real-account mutation.

Default checks are evidence-based and preflight-only. They do not crawl the repository and do not execute any runtime.

## Decisions

R30 returns:

- `READY` when all checks pass
- `MANUAL_REVIEW` when warnings exist and no check fails
- `BLOCKED` when critical validation flags or failed checks exist

`ok` is true only for `READY`.

## Safety Boundary

R30 remains a final readiness report, not a production launch mechanism.

It does not:

- call DeepSeek
- fetch market data
- call provider APIs
- connect to brokers
- import broker SDKs
- place orders
- mutate real accounts
- run Qlib or qrun
- run RQAlpha
- train models
- update live strategy weights

## What Remains Before Real Capital Usage

R30 does not approve real capital usage. Before any capital touches a broker, the project still needs:

- real data stability trial
- offline Qlib runtime spike
- broker SDK research in a separate isolated branch
- manual small-capital shadow trial
- human approval workflow
- explicit risk and account-control review

The preflight/sandbox MVP is now structured enough to support those next steps without weakening the safety boundary.
