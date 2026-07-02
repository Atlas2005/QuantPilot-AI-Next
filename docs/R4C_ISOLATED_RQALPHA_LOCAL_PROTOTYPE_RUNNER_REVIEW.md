# R4C Isolated RQAlpha Local Prototype Runner Review

R4C defines an isolated RQAlpha prototype runner review layer. It records the contract for a future local prototype attempt and the artifact schema expected from that attempt.

R4C does not run RQAlpha, does not add RQAlpha as a dependency, and does not call network or subprocess surfaces from production code. It also does not create a backtest engine, fill simulator, portfolio accounting layer, or fake metrics.

Future real execution must remain under `.venv-prototypes/rqalpha/`. Future real output should be written to:

```text
local_artifacts/backtest_prototypes/rqalpha/rqalpha_local_run_result.json
```

The artifact importer reads only existing JSON output and normalizes explicit metric fields already present in that artifact. It does not require all metrics to exist and does not invent missing metrics.

RQAlpha remains the mature-framework target for A-share event-driven backtest and trading semantics. QuantPilot owns only glue, contracts, artifact import, and agent-facing review boundaries.

Missing RQAlpha, config, data bundle, or local-run evidence must not block vectorbt, Qlib, or DeepSeek multi-agent workflows.
