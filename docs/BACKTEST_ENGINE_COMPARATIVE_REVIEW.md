# Backtest Engine Comparative Review

Phase 6D exists to compare evidence before any adapter work or final engine selection. It does not install frameworks, run prototypes, implement adapters, or select a backtest engine.

## Evidence Collected So Far

- Phase 6A created metadata-level candidate evaluation.
- Phase 6B created the prototype isolation plan.
- Phase 6C-1 ran a manual vectorbt toy prototype.
- Phase 6C-2 ran a manual Backtrader toy prototype.
- Phase 6C-3A created RQAlpha preflight metadata.
- Phase 6C-3B installed and imported RQAlpha in isolation, then stopped before any backtest.

## vectorbt

vectorbt consumed the fake Phase 3 daily OHLCV fixture and produced toy metrics. This is useful shape-compatibility evidence, but A-share realism remains unproven.

Potential next action: deeper local rule-gap prototype later.

Not recommended: final engine selection.

## Backtrader

Backtrader consumed a converted fake fixture and produced a toy event-driven result inside `.venv-prototypes/backtrader/`. It remains useful as an event-driven candidate, but live-trading related surfaces and maintenance status require caution.

Potential next action: keep as isolated event-driven candidate.

Not recommended: adapter creation now.

## RQAlpha

RQAlpha installed and imported inside `.venv-prototypes/rqalpha/`. Fake-fixture-only execution was not proven, and data bundle/config requirements need further review. License and commercial suitability remain unresolved.

Potential next action: investigate data bundle and license before any deeper run.

Not recommended: selection or adapter work.

## Qlib

Qlib remains metadata-only. It is an ML research platform candidate, not a currently tested backtest engine candidate.

Potential next action: Qlib preflight later if the alpha/ML route requires it.

Not recommended: install now without need.

## Language And Runtime Notes

Python remains suitable for the current research prototype and backtest candidate layer because the active candidates are Python-based.

LEAN/C# remains deferred as an architecture reference, not a current implementation target.

TypeScript/React remains future dashboard work only.

DuckDB, SQL, and Parquet remain future data lake or analytics infrastructure, not part of Phase 6D.

Language/runtime choices should still be reviewed at every major module boundary.

## No Final Selection

No final engine is selected in Phase 6D.

No engine is approved for adapter work.

No engine is trading-ready.

## Recommended Route After Phase 6D

- Do not build a custom backtester yet.
- Do not create adapters yet.
- Decide through ChatGPT closure review whether the next step should be Qlib preflight, a deeper vectorbt local rule-gap prototype, data bundle/config investigation, or Phase 7 alpha/factor foundation with local fixture and rule constraints.
