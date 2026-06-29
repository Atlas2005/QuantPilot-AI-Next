# RQAlpha Adapter Preflight Spike

R10 starts a small optional integration path for RQAlpha as an open-source backtesting framework candidate.

## Why RQAlpha

RQAlpha is relevant because QuantPilot-AI-Next is A-share focused and should evaluate mature open-source infrastructure before building generic backtest infrastructure internally.

R10 does not select RQAlpha as the final engine. It only checks whether gated normalized daily-bar samples and project constraints are sufficient to prepare a future RQAlpha dry-run fixture.

## Optional Dependency

RQAlpha remains optional. The project does not require it at runtime, and the preflight module can run when the dependency is missing.

Missing RQAlpha produces a warning, not a fatal failure, because R10 is a preflight spike rather than an execution phase.

## No Real Backtest Yet

R10 does not run a real RQAlpha backtest. It does not create a strategy, call network, fetch data, add live trading, replace existing internal backtest modules, or write production artifacts.

The preflight only validates:

- symbol is present
- date range is valid
- bar count is positive
- required OHLCV fields are available
- the small-sample gate passed
- cash is positive
- frequency is initially `1d`

## Open-Source-First Support

R10 supports the open-source-first requirement by keeping RQAlpha visible as an integration candidate behind adapter/preflight glue. The project remains focused on contracts, adapters, safety gates, validation, and orchestration boundaries rather than reinventing a full generic backtest engine.

## Future Path

- R11: BaoStock fallback provider.
- R12: paper ledger fed by gated real-provider samples.
- R13: actual RQAlpha dry-run fixture once dependency and data format are ready.
