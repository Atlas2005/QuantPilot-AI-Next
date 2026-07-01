# Final Readiness / Release Hardening

The final readiness package now tracks the remaining executable-trading MVP surface without requiring obsolete historical preflight modules.

It inventories required modules, verifies required documentation, checks explicit forbidden-scope evidence, and emits a structured final readiness decision.

It does not call DeepSeek, call the network, connect to brokers, place orders, mutate accounts, run Qlib, run RQAlpha, train models, update live strategy weights, or add broker SDKs as required dependencies.

## What It Checks

The package produces release checks for:

- input shape and release evidence
- required module importability
- required document presence
- explicit forbidden-scope evidence

Repository-wide scanning is intentionally not part of this package. The package validates the provided `ForbiddenScopeCheck` objects deterministically.

## Required Module Inventory

The default module inventory covers the remaining executable-trading MVP surface:

- `quantpilot_core.small_sample_data_gate`
- `quantpilot_core.real_data_provider`
- `quantpilot_core.provider_fallback_selector`
- `quantpilot_core.provider_sample_fetch_preflight`
- `quantpilot_core.paper_ledger`
- `quantpilot_core.deepseek_multi_agent`
- `quantpilot_core.pit_feature_store_preflight`
- `quantpilot_core.account_profile_preflight`
- `quantpilot_core.ai_action_paper_bridge`
- `quantpilot_core.paper_ledger_dry_run`
- `quantpilot_core.multi_day_paper_replay`
- `quantpilot_core.small_capital_readiness_gate`
- `quantpilot_core.broker_sandbox_adapter_preflight`

Required module checks import only the explicitly listed module paths.

## Required Document Inventory

The default document inventory covers:

- `docs/PIT_DATA_FEATURE_STORE_PREFLIGHT.md`
- `docs/ACCOUNT_PROFILE_BROKER_CONFIG_PREFLIGHT.md`
- `docs/AI_ACTION_PROPOSAL_PAPER_LEDGER_BRIDGE.md`
- `docs/PAPER_LEDGER_DRY_RUN_INTEGRATION.md`
- `docs/MULTI_DAY_PAPER_REPLAY.md`
- `docs/SMALL_CAPITAL_READINESS_GATE.md`
- `docs/BROKER_SANDBOX_ADAPTER_PREFLIGHT.md`

Document checks use explicit `Path.exists` checks only for the listed files.

## Forbidden-Scope Checks

The package validates provided forbidden-scope evidence strings for signals such as order placement, live trading, broker SDK usage, runtime Qlib commands, network calls, live model training, and real-account mutation.

Default checks are evidence-based. They do not crawl the repository and do not execute any runtime.

## Decisions

The package returns:

- `READY` when all checks pass
- `MANUAL_REVIEW` when warnings exist and no check fails
- `BLOCKED` when critical validation flags or failed checks exist

`ok` is true only for `READY`.

## Safety Boundary

This remains a final readiness report, not a production launch mechanism.

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

This package does not approve real capital usage. Before any capital touches a broker, the project still needs:

- real data stability trial
- mature framework-backed replay and attribution integration
- broker SDK research in a separate isolated branch
- manual small-capital shadow trial
- human approval workflow
- explicit risk and account-control review

Safety must not mean no trading. Missing historical Qlib, RQAlpha, DeepSeek, attribution, or orchestration preflight modules should not block paper replay or controlled trading progress.
