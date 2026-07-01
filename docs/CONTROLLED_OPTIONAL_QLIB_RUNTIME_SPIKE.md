# P42 Controlled Optional Qlib Runtime Spike

P42 prepares a controlled optional Qlib runtime boundary without making Qlib required for default tests.

This phase does not run qrun by default, install dependencies, connect to brokers, call LLM runtimes, fetch network data, or claim real profitability. It builds glue around optional runtime detection, manual execution planning, local result import, and comparison against the P41 offline workflow proxy and P40 AI-shadow-adjusted replay direction.

## Objective

P42 answers:

- did Qlib remain optional?
- was qrun disabled by default?
- was a manual execution plan produced?
- was a runtime result import boundary produced?
- was the imported runtime-like result validated?
- was comparison against P41/P40 completed?
- did mixed stock+ETF coverage remain visible?
- did P42 avoid profitability claims?
- is the safety barrier still at or below `140%`?

## Runtime Detection

Runtime detection uses a package spec lookup only. It does not import Qlib in default tests.

Default execution mode is `DISABLED_DEFAULT`. If the optional dependency is unavailable, P42 reports `UNAVAILABLE_OPTIONAL_DEPENDENCY`. If it appears available, P42 still reports disabled-by-default behavior unless explicit manual-local mode is requested.

Network, broker, LLM, and qrun execution remain disabled by default.

## Manual Execution Plan

The manual plan includes:

- dataset id from P41 metadata
- workflow config summary
- qrun disabled by default
- manual local-only execution
- required user confirmation
- no network requirement
- no broker requirement
- no account requirement
- result import path placeholder
- warnings
- exact statement that default pytest does not execute Qlib or qrun

The plan is data only. It does not execute qrun.

## Runtime Result Import

P42 validates manually produced local runtime-like result records.

Validation checks:

- result source is local
- dataset id matches the plan
- workflow config id matches the plan when provided
- IC/RankIC or explicit missing reason is present
- cost-aware metric or explicit missing reason is present
- profitability claim is false
- benchmark is explicit
- stock and ETF counts are preserved
- execution mode is manual or import-only
- warnings are preserved

## Comparison

P42 compares imported runtime-like results against:

- P41 offline evaluation proxy
- P40 AI-shadow-adjusted replay metadata when available

The comparison reports runtime import status, optional dependency status, offline-vs-runtime score delta, cost-aware agreement, factor-signal agreement, ETF coverage preservation, and promotion decision.

Promotion decisions include:

- `promote_to_real_qlib_runtime_trial`
- `require_provider_sample_quality`
- `require_factor_quality`
- `require_cost_model_realism`
- `keep_runtime_disabled`

## Safety Boundary

P42 does not:

- connect to brokers
- read real accounts
- place real orders
- import broker SDKs
- call DeepSeek
- call OpenAI
- make network calls in default tests
- fetch live or remote provider data in default tests
- install packages
- modify project dependencies
- run Qlib or qrun by default
- require Qlib for default tests
- claim real profitability
- add generic preflight-only gates

## Recommended Next Step

Install a separate optional Qlib environment outside default pytest and manually produce a local runtime result file that can be imported through the P42 boundary.
