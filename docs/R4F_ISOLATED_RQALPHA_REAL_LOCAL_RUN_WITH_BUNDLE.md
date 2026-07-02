# R4F Isolated RQAlpha Real Local Run With Bundle

R4F uses the existing manual RQAlpha prototype runner to attempt a real minimal local run only when an authorized local bundle is available.

Run command:

```bash
.venv-prototypes/rqalpha/bin/python tools/manual_backtest_prototypes/rqalpha_local_run_attempt.py
```

R4F does not add RQAlpha to the main `pyproject.toml`, does not modify production `src/quantpilot_core`, does not modify the main `.venv`, and does not commit bundles, raw market data, `.external` data, `local_artifacts` output, or large data files.

## Bundle Policy

The runner follows R4E:

- default bundle path: `~/.rqalpha/bundle`;
- optional explicit bundle path: `RQALPHA_BUNDLE_PATH`;
- explicit bundle paths must stay outside tracked source, except ignored `.external/` policy paths when separately authorized;
- if the bundle is missing, the artifact status is `data_bundle_required_or_missing` with `download_required=true`;
- missing bundle evidence must not block vectorbt, Qlib, DeepSeek, paper ledger, or paper replay workflows.

The runner does not download data. Any bundle acquisition must be a separate authorized manual step.

## Runtime Boundary

RQAlpha is imported only inside `tools/manual_backtest_prototypes/rqalpha_local_run_attempt.py` and only when executed by `.venv-prototypes/rqalpha/bin/python`.

The tool must not touch broker, live trading, `mod-ctp`, or `mod-vnpy` paths. It remains a local backtest prototype attempt.

## Metrics Boundary

Only explicit allowed metric keys returned by RQAlpha output mappings may be copied:

- `total_return`
- `annualized_return`
- `max_drawdown`
- `sharpe`
- `trade_count`
- `turnover`

The runner must not infer `trade_count` from row counts, must not invent total return, Sharpe, drawdown, returns, profitability, or any missing metric, and must keep `observed_trade_rows` as evidence metadata only.

## Artifact

The ignored output artifact is:

```text
local_artifacts/backtest_prototypes/rqalpha/rqalpha_local_run_result.json
```

Expected structured statuses include:

- `data_bundle_required_or_missing`
- `bundle_authorization_required`
- `config_required_or_invalid`
- `rqalpha_run_failed`
- `output_metrics_missing`
- `local_run_succeeded`
