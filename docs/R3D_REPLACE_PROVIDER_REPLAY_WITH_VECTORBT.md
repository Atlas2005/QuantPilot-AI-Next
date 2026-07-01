# R3D Replace Provider Replay With Vectorbt

## Objective

R3D changes the provider mixed ETF replay direction from comparison-first to replacement-first.

The preferred primary provider replay engine is now the optional vectorbt-backed path in `provider_vectorbt_replay`. The old `real_provider_mixed_etf_paper_replay` path remains available only as legacy/reference compatibility while mature framework-backed replay replaces generic self-built replay mechanics.

## What R3D Adds

R3D adds a provider sample to vectorbt bridge:

- validates and normalizes local provider mixed stock/ETF samples with the existing provider sample validator
- converts close prices into an existing `SignalReplaySample`
- recreates the deterministic provider signal pattern used by the legacy path
- calls the existing optional vectorbt replay comparison path
- reports vectorbt metrics as the primary provider replay output

It does not call the old P36 daily paper loop and does not simulate fills itself.

## Replacement Boundary

QuantPilot keeps project-specific glue:

- provider sample validation and normalization
- A-share, account, and capital rules
- broker and execution adapters
- AI and multi-agent orchestration

Generic replay, portfolio metrics, and framework-level analysis should move to mature open-source frameworks where suitable. vectorbt is the preferred provider replay engine for this stage. RQAlpha and Qlib remain future replacement candidates for A-share-style backtesting and AI quant workflows.

## Optional Runtime Availability

Missing vectorbt is reported as `vectorbt_framework_missing`. That is a runtime availability state, not an execution gate and not a reason to add another self-built replay engine.

Default tests remain offline and deterministic. The project does not hard-import vectorbt, pandas, or NumPy from the new provider replay package.

## Legacy Status

The old P36/P39 provider replay path is legacy/reference compatibility. It can still be useful for comparing historical behavior, but it should not be treated as the preferred/default provider replay engine when vectorbt can replace the generic replay and portfolio metrics layer.

## Next Step

Replace more self-built replay, fill, and metrics modules with vectorbt, RQAlpha, or Qlib where those mature frameworks fit. Preserve only the QuantPilot-specific A-share, account, capital, broker adapter, and AI orchestration glue that mature frameworks do not own.
