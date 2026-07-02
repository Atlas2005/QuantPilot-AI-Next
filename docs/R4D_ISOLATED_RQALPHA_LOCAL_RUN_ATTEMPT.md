# R4D Isolated RQAlpha Local Run Attempt

R4D adds a manual isolated RQAlpha local run attempt tool:

```text
tools/manual_backtest_prototypes/rqalpha_local_run_attempt.py
```

Run it only from the isolated prototype interpreter:

```bash
.venv-prototypes/rqalpha/bin/python tools/manual_backtest_prototypes/rqalpha_local_run_attempt.py
```

The tool imports RQAlpha only inside the manual prototype script. It does not add
RQAlpha to project dependencies, does not install packages, does not modify the
main `.venv`, and does not run from production `src/quantpilot_core` code.

The output artifact is:

```text
local_artifacts/backtest_prototypes/rqalpha/rqalpha_local_run_result.json
```

The artifact records importability, version, environment path, run API attempted,
symbol, date range, account settings, status, failure stage, exception details,
available report/result keys, explicit metrics, warnings, and conclusion.

If RQAlpha requires a data bundle, config, or local data setup that is not
available, the tool catches the failure, writes a structured
`data_bundle_required_or_missing` or related status, and exits cleanly. This is
evidence for the R4C artifact import/review contract, not production readiness.

Metrics must not be invented. `explicit_metrics` only copies explicit allowed
metric keys from RQAlpha output mappings: `total_return`, `annualized_return`,
`max_drawdown`, `sharpe`, `trade_count`, and `turnover`. Missing metrics are left
missing.

`observed_trade_rows`, if present, is evidence metadata that records the number
of returned trade rows. It is not a performance metric and must not be copied
into `explicit_metrics` as `trade_count`.

The tiny strategy is deliberately inert and does not create broker, live trading,
or real order execution paths. Live-provider modules such as `mod-ctp` and
`mod-vnpy` remain out of scope.

RQAlpha gaps must not block vectorbt, Qlib, or DeepSeek multi-agent workflows.
