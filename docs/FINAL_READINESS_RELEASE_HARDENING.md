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

- `quantpilot_core.real_data_provider`
- `quantpilot_core.provider_fallback_selector`
- `quantpilot_core.paper_ledger`
- `quantpilot_core.deepseek_multi_agent`
- `quantpilot_core.ai_action_paper_bridge`
- `quantpilot_core.paper_ledger_dry_run`
- `quantpilot_core.multi_day_paper_replay`

Required module checks import only the explicitly listed module paths.

## Required Document Inventory

The default document inventory covers:

- `docs/AI_ACTION_PROPOSAL_PAPER_LEDGER_BRIDGE.md`
- `docs/PAPER_LEDGER_DRY_RUN_INTEGRATION.md`
- `docs/MULTI_DAY_PAPER_REPLAY.md`

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

This package is not the capital deployment controller. Capital deployment is governed by account configuration, broker permissions, rollout mode, and explicit order-routing controls.

Before any capital touches a broker, the project still needs:

- real data stability trial
- mature framework-backed replay and attribution integration
- broker SDK research in a separate isolated branch
- manual small-capital shadow trial
- human approval workflow
- explicit risk and account-control review

Safety must not mean no trading. Missing historical Qlib, RQAlpha, provider sample, PIT, account profile, small-capital readiness, attribution, broker sandbox, or orchestration preflight modules should not block paper replay or controlled trading progress.
