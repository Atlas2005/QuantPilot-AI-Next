# Backtest Prototype Results

## Phase 6C-1: vectorbt Manual Local-Fixture Prototype

This result is manual prototype evidence only. It is not production integration, not a real A-share backtest, not a final engine selection, and not trading-ready.

## Commands Run

```text
python tools/manual_backtest_prototypes/vectorbt_local_fixture_probe.py
python -m pip install vectorbt
python tools/manual_backtest_prototypes/vectorbt_local_fixture_probe.py
python tools/manual_backtest_prototypes/summarize_vectorbt_probe.py
```

The first probe run confirmed clean failure behavior when `vectorbt` was missing.

## Package Status

`vectorbt` was installed manually for the local prototype only. It was not added to `pyproject.toml` and is not a project dependency.

The install pulled vectorbt-related packages into the local Python environment and downgraded an already-present `pandas` installation from `3.0.2` to `2.3.3` because of vectorbt's dependency constraint. This is a local environment risk and should be reviewed before future prototype work.

Phase 6C-1.1 adds the follow-up policy: future external-framework prototypes must run in isolated `.venv-prototypes/<tool-name>/` environments. The vectorbt result remains useful as local fixture shape-compatibility evidence, but it is not enough for engine selection. Any deeper vectorbt test should be rerun in an isolated prototype environment if needed.

## Prototype Result

- Fake local fixture used: yes, `data/fixtures/a_share_daily_sample_valid.csv`.
- Real market data used: no.
- Provider/API used: no.
- Symbol selected: `000001.SZ`.
- Row count: 3.
- vectorbt importable after manual install: yes.
- Prototype ran: yes.
- Output metrics produced: yes, 28 metric keys were available.
- Production adapter created: no.

The prototype indicates that vectorbt can consume the Phase 3 fake daily OHLCV fixture shape and produce toy portfolio metrics from a minimal signal. This is shape-compatibility evidence only.

## A-share Rule Gaps

- T+1 not proven.
- Limit-up/limit-down not proven.
- Suspension handling not proven.
- ST/delisting special cases not proven.
- Liquidity constraints not proven.
- Realistic fees/slippage not proven.

## Recommendation

vectorbt deserves a deeper isolated prototype later if ChatGPT approves. The next prototype should remain manual-only and should focus on whether A-share market-rule constraints can be represented cleanly without polluting QuantPilot core contracts or creating a production adapter prematurely.
