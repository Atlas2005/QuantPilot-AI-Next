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

## Phase 6C-1 Result Reference

Phase 6C-1 tested vectorbt first because it has a lower broker/live-trading surface than Backtrader and RQAlpha. The manual local-fixture probe showed that vectorbt can consume the fake Phase 3 daily OHLCV fixture and produce toy metrics, but it did not prove A-share realism, T+1 handling, limit-up/down behavior, suspension handling, liquidity realism, or production readiness.

Phase 6C-1 also showed that installing prototype frameworks in the main Python environment is unsafe: the local vectorbt install changed the environment and downgraded an already-present pandas version. Future prototypes must use `.venv-prototypes/<tool-name>/`. Backtrader, RQAlpha, Qlib, and any deeper vectorbt tests must not run in the main project environment. No future framework prototype should proceed without environment isolation.

Detailed result summary lives in:

```text
docs/BACKTEST_PROTOTYPE_RESULTS.md
```

## Phase 6C-2 Result Reference

Phase 6C-2 tested Backtrader only inside `.venv-prototypes/backtrader/` because Backtrader has live-trading related capabilities. The manual local-fixture probe showed that Backtrader can consume a converted fake Phase 3 daily OHLCV fixture and produce a minimal event-driven toy result, but it did not prove A-share realism or production readiness.

Backtrader, RQAlpha, Qlib, and any other external engine prototypes must continue to run outside the main project environment.

## Phase 6C-3A RQAlpha Preflight

Phase 6C-3A is preflight only. RQAlpha is not installed, imported, or run in this phase.

RQAlpha remains interesting because of China-market relevance, but any prototype must be approved later and must run only in `.venv-prototypes/rqalpha/`. No fallback to the main project environment is allowed.

Preflight metadata lives in:

```text
data/backtest_engine_candidates/rqalpha_preflight.json
```

## Phase 6C-3B RQAlpha Result Reference

Phase 6C-3B tested RQAlpha only inside `.venv-prototypes/rqalpha/`. No fallback to the main project environment occurred.

RQAlpha installed and imported in isolation, but fake-fixture-only local run support was not proven. The probe stopped before any backtest because data bundle/config requirements need further review.

Any future deeper RQAlpha work must remain isolated and must not create production adapters, project dependencies, broker/live/order paths, or final engine-selection claims.

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
