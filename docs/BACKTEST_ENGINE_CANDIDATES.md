# Backtest Engine Candidates

This is a metadata-level review only. No installation occurred, no prototype was run, and no final selection was made.

Candidate metadata lives in:

```text
data/backtest_engine_candidates/backtest_engines.json
```

Detailed prototype isolation plans live in:

```text
data/backtest_engine_candidates/prototype_plans.json
```

## Candidates

- Qlib: AI/ML research platform candidate; prototype later, not selected.
- LEAN: full trading platform / architecture reference; live trading capability must remain isolated.
- vectorbt: vectorized research candidate; must evaluate A-share market rule fit.
- Backtrader: event-driven candidate; live-trading related capabilities must be isolated.
- RQAlpha: potentially China-market relevant; requires license and maintenance review.
- vn.py / VeighNa: trading system architecture reference; not an early dependency.
- Zipline-reloaded: event-driven candidate; requires maintenance and compatibility review.
- NautilusTrader: advanced trading engine candidate; likely too heavy for early stage.
- backtesting.py: simple baseline candidate only.
- bt: simple portfolio/backtest baseline candidate only.
