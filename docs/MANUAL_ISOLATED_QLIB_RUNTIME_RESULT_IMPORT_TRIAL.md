# Manual Isolated Qlib Runtime Result Import Trial

## Objective

P44 connects the P43 isolated manual Qlib runbook to the P42 runtime-like result import boundary.

It does not run qrun, install Qlib, train a model, fetch data, call an LLM, connect to a broker, or claim profitability. The purpose is to prove that a locally captured manual runtime-like result can be loaded, validated, imported through the existing P42 path, and compared against P42/P41/P40 direction.

## Scope

P44 accepts three artifact source types:

- `p43_capture_template`
- `manual_local_result_record`
- `deterministic_fixture`

Default tests use deterministic in-memory records. Local JSON files are supported only when explicitly passed by tests or a manual caller. Remote artifact sources are rejected.

## Artifact Loader

The loader normalizes a local runtime-like result into the existing P42 result record shape. It validates:

- local-only artifact source
- dataset id
- workflow config id
- benchmark
- non-negative stock and ETF counts
- local result source
- manual or import-only execution mode
- no profitability claim
- preserved warnings
- IC or RankIC metric, or explicit missing reason
- cost-aware metric, or explicit missing reason

This keeps P44 aligned with the P43 capture template while avoiding another generic gate.

## Import Trial

The import trial feeds the normalized artifact into the P42 import boundary. It reports:

- import accepted or rejected
- rejection reasons
- dataset and workflow match
- benchmark presence
- mixed stock and ETF coverage
- IC/RankIC availability
- cost-aware metric availability
- profitability claim rejection
- preserved warnings

## Comparison

P44 compares accepted imports against:

- P42 runtime-like comparison expectations
- P41 offline evaluation proxy direction
- P40 AI-shadow-adjusted mixed ETF replay metadata

The comparison reports score delta, cost-aware agreement, factor-signal agreement, ETF coverage, and a promotion decision.

Promotion decisions are intentionally conservative:

- `require_real_qrun_result`
- `require_provider_sample_quality`
- `require_factor_quality`
- `require_cost_model_realism`
- `keep_runtime_disabled`

A deterministic fixture can validate the import path, but it cannot prove real runtime profitability.

## Safety Boundary

P44 keeps the active safety barrier at `140.0%`.

It does not add another research-only wall. It moves the project closer to a controlled real optional Qlib trial by wiring the P43 capture output into P42 import and comparison.

## Next Step

When the artifact is accepted and comparison direction is consistent, the next useful step is to run a real isolated Qlib trial manually, export the local result record, and import it through this same P44 path.
