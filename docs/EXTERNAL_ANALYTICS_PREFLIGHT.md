# External Analytics Preflight

Phase 7D reviews external factor and performance analytics candidates before any package installation or integration.

No candidate is installed in Phase 7D. No tear sheets, portfolio reports, factor analysis, or external analytics output exists yet.

## Candidate Roles

- Alphalens / Alphalens Reloaded: factor analysis and factor tear sheets.
- quantstats / quantstats-reloaded: portfolio performance reports.
- empyrical / empyrical-reloaded: risk and performance metrics.
- Qlib: ML research workflow and factor/model platform candidate.

## Why Fake Fixture Data Is Insufficient

The current fake fixture is tiny and artificial. External analytics tools need meaningful panels or return streams. Running them now would create polished-looking output without evidence.

## Preconditions Before External Analytics

External analytics require:

- larger real historical dataset
- clean factor values
- clean forward returns
- symbol/date alignment
- OOS split
- walk-forward validation
- transaction cost model
- A-share execution rule integration
- strategy return series for portfolio analytics

## Future Prototype Rules

- isolated environment only
- no `pyproject.toml` dependency until adapter phase
- no raw outputs committed
- no alpha claim without evidence
- no trading-ready claim
- no strategy tournament shortcut

## Current Status

Phase 7D creates metadata, validation helpers, docs, and tests only. External analytics remain candidates, not proof.
