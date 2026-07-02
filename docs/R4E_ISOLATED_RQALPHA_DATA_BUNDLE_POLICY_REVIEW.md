# R4E Isolated RQAlpha Data Bundle Policy Review

R4E is a policy and review step for future isolated RQAlpha data bundle acquisition. It does not download data, does not install packages, does not add RQAlpha to the main project dependencies, and does not run RQAlpha.

## Allowed Bundle Locations

Allowed bundle locations are local-only and must remain outside tracked source:

- the default RQAlpha user bundle location, `~/.rqalpha/bundle`;
- an explicit local bundle path supplied to the isolated prototype environment;
- a temporary ignored workspace location under `.external/` only when a later approved manual step requires it.

No bundle, `.external` data, `local_artifacts` output, market data archive, binary data file, or large data file may be committed.

## Default Bundle Behavior

RQAlpha may look for its default bundle under `~/.rqalpha/bundle`. R4E does not create, refresh, inspect, or download that bundle. If the default bundle is missing, R4D/R4F-style tooling should record a structured local status such as `data_bundle_required_or_missing` or `download_required`, then exit cleanly.

## Explicit Bundle Path

A future R4F local run may use an explicit bundle path only if the path is local, authorized, and outside tracked source. The path should be passed as configuration to the isolated manual tool, not hard-coded into production `src/quantpilot_core` code.

## Ignore And No-Data Policy

The repository must continue to ignore:

- `.venv-prototypes/`
- `.external/`
- `local_artifacts/`

The RQAlpha bundle, raw provider data, generated result artifacts, and any large local files must stay out of git. R4E should add policy and tests only, not data files.

## License And Authorization Warning

RQAlpha bundle acquisition may involve license, non-commercial, redistribution, market-data-vendor, exchange, or user authorization constraints. R4E does not approve commercial use, redistribution, vendoring, or production use of any data bundle. A human must verify authorization before any download or local bundle use.

## Isolated Environment Only

Any future real RQAlpha bundle check or local run must use the isolated environment:

```bash
.venv-prototypes/rqalpha/bin/python tools/manual_backtest_prototypes/rqalpha_local_run_attempt.py
```

The main project `.venv` must not be modified. RQAlpha must not be added to `pyproject.toml` required dependencies. Production `src/quantpilot_core` must not import RQAlpha, run subprocesses for RQAlpha, call network APIs, or download bundles.

## Structured Missing-Bundle Status

Missing bundle or download-required conditions must be explicit local statuses, not global blockers. Accepted status language includes:

- `data_bundle_required_or_missing`
- `download_required`
- `config_required_or_invalid`
- `bundle_authorization_required`

These statuses should be written to ignored local artifacts such as:

```text
local_artifacts/backtest_prototypes/rqalpha/rqalpha_local_run_result.json
```

They must not block vectorbt, Qlib, or DeepSeek multi-agent workflows.

## Broker And Live-Trading Boundary

R4E does not permit broker, live trading, real order execution, `mod-ctp`, `mod-vnpy`, live provider, or account-connection paths. The future R4F run must remain a local backtest prototype attempt only.

## R4F Handoff Requirements

Before R4F attempts a real local run with a bundle, it must have:

- a confirmed isolated interpreter under `.venv-prototypes/rqalpha/`;
- a documented bundle source and authorization basis;
- either confirmed default bundle availability at `~/.rqalpha/bundle` or a documented explicit local bundle path;
- no committed bundle or raw data files;
- a structured output path under `local_artifacts/backtest_prototypes/rqalpha/`;
- clear handling for `data_bundle_required_or_missing`, `download_required`, and authorization failures;
- no production dependency, network, subprocess, broker, live trading, `mod-ctp`, or `mod-vnpy` expansion;
- a reminder that explicit metrics may only be copied from RQAlpha output mappings and must not be invented.
