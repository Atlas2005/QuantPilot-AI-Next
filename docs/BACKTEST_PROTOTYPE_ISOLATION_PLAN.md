# Backtest Prototype Isolation Plan

Phase 6B does not install or run engines. It creates a manual-only isolation plan for future prototype runs.

## Why No Engine Runs in Phase 6B

Backtest framework experiments can introduce dependencies, hidden assumptions, broker/live modules, and misleading results. Phase 6B only plans how future prototypes should be isolated and evaluated.

## Future Phase 6C Isolation

Future prototypes should run manually, outside CI, in isolated environments. Raw outputs must stay under `local_artifacts/`. Early prototypes should use only fake local Phase 3 fixtures.

## First-Wave Prototype Order

1. vectorbt
2. Backtrader
3. RQAlpha

These are first-wave because they represent different useful categories: vectorized research, event-driven research, and China-market relevance.

## Second Wave

Qlib is second-wave because it is more ML research platform than minimal backtest adapter.

backtesting.py, bt, and Zipline-reloaded are also second-wave candidates for baseline or compatibility review.

## Deferred Candidates

LEAN, vn.py / VeighNa, and NautilusTrader are deferred because live-trading and full-platform risks must remain isolated from early core.

## Prototype Output Evaluation

Future prototype outputs should document:

- input fixture compatibility
- output artifact shape
- A-share rule fit
- T+1 behavior
- lot-size handling
- limit-up/down handling
- suspension assumptions
- fee/slippage limitations
- broker/live module isolation

## No Final Selection

No engine is selected in Phase 6B. Any future integration must pass ChatGPT review, adapter boundaries, and contract tests.

