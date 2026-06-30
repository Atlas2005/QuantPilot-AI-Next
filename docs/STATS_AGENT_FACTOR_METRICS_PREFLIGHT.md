# R28 Stats Agent / Factor Metrics Preflight

R28 adds a deterministic preflight layer for factor metric evidence that future Stats Agent, Factor Agent, Qlib Evaluation, Supervisor, and Multi-Agent Orchestrator stages can consume.

It does not call DeepSeek, call the network, connect to brokers, place orders, mutate accounts, train models, update live strategy weights, run Qlib, or run RQAlpha. It is an offline validation and metric-record layer only.

## Purpose

The project needs factor evidence to be structured before any agent or open-source evaluation engine can rely on it. R28 checks whether a factor sample is well-formed, computes simple deterministic metrics, compares them with default thresholds, and emits pass, warning, or fail records.

This keeps the Stats Agent / Factor Agent path evidence-first and avoids letting informal factor impressions flow directly into action proposals.

## Metric Definitions

R28 emits these metric records:

- `sample_count`: number of observations
- `coverage_ratio`: unique observed symbols divided by expected universe size, capped at `1.0`
- `ic`: Pearson correlation between factor value and forward return
- `rank_ic`: Pearson correlation between average ranks of factor value and forward return
- `hit_rate`: directional sign-hit rate based on factor direction
- `turnover`: supplied estimated turnover
- `max_drawdown`: peak-to-trough drawdown over the deterministic forward-return path sorted by date then symbol
- `cost_aware_score`: `abs(IC) + abs(RankIC) + hit_rate - estimated_cost_ratio - estimated_turnover`

If a correlation denominator is zero, R28 returns `0.0` for that correlation and marks the metric as a warning.

## Direction Semantics

- `long_only`: hit when `factor_value > 0` and `forward_return > 0`
- `short_only`: hit when `factor_value < 0` and `forward_return < 0`
- `long_short`: hit when factor value and forward return have the same non-zero sign
- `neutral`: uses the same sign-consistency rule as `long_short`

## Default Thresholds

- minimum sample count: `20`
- minimum coverage ratio: `0.50`
- minimum absolute IC: `0.02`
- minimum absolute RankIC: `0.02`
- minimum hit rate: `0.50`
- maximum turnover: `0.80`
- maximum drawdown: `0.20`
- minimum cost-aware score: `0.05`

Coverage below threshold is a warning. Low IC, low RankIC, low hit rate, and high turnover are warnings. Small sample count, high drawdown, and low cost-aware score are failures.

## Decisions

R28 returns:

- `PASS` only when all validation checks and metrics pass
- `MANUAL_REVIEW` when warnings exist and no metric fails
- `FAIL` when validation produces critical risk flags or any metric fails

`ok` is true only for `PASS`.

## Integration Boundary

R28 is compatible with the open-source-first architecture because it is deliberately small: contracts, validation, simple metric records, and adapter-ready output. It does not attempt to replace Qlib, RQAlpha, or mature analytics packages.

Future Qlib Evaluation Preflight can consume these records to decide whether a factor sample is ready for a Qlib fixture or external analytics adapter. Future Multi-Agent Orchestrator phases can place this preflight between PIT feature readiness and action proposal stages.

## Safety Boundary

R28 does not:

- call DeepSeek
- fetch market data
- call news or provider APIs
- connect to brokers
- place orders
- mutate accounts
- train models
- update live strategy weights
- run Qlib
- run RQAlpha

It is a deterministic offline guardrail for factor evidence quality.
