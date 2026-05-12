# Backtest Engine Candidates

This started as a metadata-level review. Later manual local-fixture prototypes added limited evidence for selected candidates. No final selection has been made.

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
- vectorbt: vectorized research candidate; Phase 6C-1 produced manual local-fixture shape-compatibility evidence, but no final selection has been made and A-share market rule fit remains unproven.
- Backtrader: event-driven candidate; Phase 6C-2 produced manual local-fixture prototype evidence in isolated `.venv-prototypes/backtrader/`, but no final selection has been made. Live-trading related capabilities must be isolated, and maintenance risk remains because the PyPI latest release appears older and must be refreshed before any adapter phase.
- RQAlpha: potentially China-market relevant; Phase 6C-3A added dedicated preflight review and Phase 6C-3B added isolated install/import evidence. Fake-fixture-only local run support was not proven, no final selection has been made, license/commercial risk remains unresolved, and broker/live/trading framework surfaces remain isolated.
- vn.py / VeighNa: trading system architecture reference; not an early dependency.
- Zipline-reloaded: event-driven candidate; requires maintenance and compatibility review.
- NautilusTrader: advanced trading engine candidate; likely too heavy for early stage.
- backtesting.py: simple baseline candidate only.
- bt: simple portfolio/backtest baseline candidate only.
