# Alpha / Factor Foundation

Phase 7A creates the first local factor research foundation. It defines factor metadata, toy computation, and minimal evaluation shape checks.

This is not real alpha evidence. It is not a profitable strategy. It is not trading-ready.

## Why Start Before Final Backtest Engine Selection

Factor contracts and toy computation can be defined before selecting a final backtest engine. These contracts help clarify the inputs and outputs that later validation, backtest, tournament, and portfolio modules will need.

## Data Scope

Phase 7A uses only the fake local fixture:

```text
data/fixtures/a_share_daily_sample_valid.csv
```

No real market data, APIs, providers, or external analytics packages are used.

## Toy Factor

`close_to_close_momentum_1d` computes:

```text
close_today / close_previous_day - 1
```

It is only a shape test for factor observations.

## Toy Rank Correlation

The toy rank correlation compares factor observation ranks with one-step forward return ranks on the fake fixture.

It does not measure statistical significance, robustness, out-of-sample behavior, walk-forward behavior, transaction costs, capacity, liquidity, or profitability.

## Why No External Analytics Yet

Phase 7A does not integrate:

- Alphalens Reloaded
- quantstats
- empyrical / empyrical-reloaded
- Qlib factor/model workflow

These remain later candidates after local contracts, validation metrics, and evidence rules are clearer.

## Future Relationship

Future phases may evaluate:

- Alphalens-style factor tear sheets
- quantstats performance reports
- empyrical metrics
- Qlib factor/model workflows
- walk-forward and OOS validation

Any such integration must pass ChatGPT review, adapter boundaries, dependency review, and license/commercial review.

## Next Likely Phases

- Phase 7B factor validation metrics
- Phase 7C factor candidate library
- Phase 8 strategy tournament
