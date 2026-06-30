# Review Packet

## Task Name

R28: Stats Agent / Factor Metrics Preflight.

## Changed Files

- `docs/STATS_AGENT_FACTOR_METRICS_PREFLIGHT.md`
- `docs/REVIEW_PACKET.md`
- `src/quantpilot_core/stats_agent_factor_metrics_preflight/__init__.py`
- `src/quantpilot_core/stats_agent_factor_metrics_preflight/contracts.py`
- `src/quantpilot_core/stats_agent_factor_metrics_preflight/metrics.py`
- `src/quantpilot_core/stats_agent_factor_metrics_preflight/preflight.py`
- `tests/stats_agent_factor_metrics_preflight/test_stats_agent_factor_metrics_preflight.py`

## Safety Checks

- `src/` changed: Yes. Added standard-library-only R28 stats-agent factor metrics contracts, validation, deterministic metric helpers, metric records, and preflight decision logic.
- Tests changed: Yes. Added R28 offline stats-agent factor metrics preflight tests.
- Local fixture changed: No.
- Integration matrix changed: No.
- Open-source decision table changed: No.
- Manual probe scripts changed: No.
- Dependencies changed: No.
- Packages installed: No.
- Packages uninstalled: No.
- `pyproject.toml` changed: No.
- Market data/API used during implementation: No.
- Provider API called during implementation: No.
- Production data assets written: No.
- Manual probes run: No.
- Real data fetched: No.
- Raw data committed: No.
- Any data source approved: No.
- Full data provider implementation added: No.
- Real news crawling added: No.
- DeepSeek/API call added: No.
- Model training added: No.
- Live strategy weight update added: No.
- Real account API read: No.
- Broker connection added: No.
- Vendor broker SDK imported: No.
- Paper ledger persistence write added: No.
- Live order path added: No.
- Real alpha evidence produced: No.
- Statistical significance claimed: No.
- External analytics installed/imported: No.
- Broker/live/order submission path created: No.
- Real backtest/model/agent implementation added: No.
- Full backtest/risk/factor/calendar/accounting engine added: No.
- External frameworks installed/imported in `src/`: No.
- Final technical selections made: No.
- Profitability claim made: No.

## Language / Runtime Decision

R28 keeps new `src/` code on Python standard library only. It adds deterministic factor metric evidence validation, IC, RankIC, hit-rate, turnover, drawdown, coverage, sample-count, and cost-aware score records for future Stats Agent / Factor Agent consumption.

R28 does not run agents, connect to brokers, mutate accounts, place orders, import broker SDKs, call DeepSeek, perform network calls, train models, update live strategy weights, run Qlib, or run RQAlpha.

R28 builds on the R16-R27 control surfaces by adding an offline factor-evidence preflight layer before future Qlib Evaluation or Multi-Agent Orchestrator runtime work.

## Validation Commands and Results

`python -m compileall src`

Result: not run because bare `python` is not available in this shell.

```text
zsh:1: command not found: python
```

`python -m pytest tests/stats_agent_factor_metrics_preflight`

Result: not run because bare `python` is not available in this shell.

```text
zsh:1: command not found: python
```

`.venv/bin/python -m compileall src`

Result: passed.

`.venv/bin/python -m pytest tests/stats_agent_factor_metrics_preflight`

Result: passed.

```text
platform darwin -- Python 3.12.10, pytest-9.1.1
collected 17 items
17 passed in 0.03s
```

`.venv/bin/python -m pytest`

Result: passed.

```text
platform darwin -- Python 3.12.10, pytest-9.1.1
collected 563 items
563 passed in 0.26s
```

## R28 Stats Agent / Factor Metrics Preflight Summary

R28 adds an offline deterministic preflight for factor metric evidence that future Stats Agent, Factor Agent, Qlib Evaluation, Supervisor, and Multi-Agent Orchestrator stages can consume.

The preflight validates factor identity, direction, evidence, observations, strict ISO dates, finite values, duplicate symbol/date pairs, expected universe size, turnover, and cost ratio.

It computes sample count, coverage ratio, IC, RankIC, hit rate, turnover, max drawdown, and cost-aware score. `PASS` is returned only when all metrics pass, `MANUAL_REVIEW` is returned when warnings exist without failures, and `FAIL` is returned for critical validation flags or failed metrics.

## Risks

- R28 is preflight only; it does not implement or prove alpha, statistical significance, Qlib evaluation, or a live factor agent.
- Simple deterministic metrics are not a replacement for mature analytics frameworks.
- Future Qlib or external analytics work must remain behind explicit preflight and adapter boundaries.

## Recommended Next Step

Run closure review for R28. A future phase can define Qlib Evaluation Preflight or richer external analytics adapters while keeping this deterministic preflight as the factor-evidence boundary.
