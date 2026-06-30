# Review Packet

## Task Name

R24: Performance Attribution Flywheel Preflight.

## Changed Files

- `docs/PERFORMANCE_ATTRIBUTION_FLYWHEEL_PREFLIGHT.md`
- `docs/REVIEW_PACKET.md`
- `src/quantpilot_core/performance_attribution_preflight/__init__.py`
- `src/quantpilot_core/performance_attribution_preflight/attribution.py`
- `src/quantpilot_core/performance_attribution_preflight/contracts.py`
- `src/quantpilot_core/performance_attribution_preflight/preflight.py`
- `tests/performance_attribution_preflight/test_performance_attribution_preflight.py`

## Safety Checks

- `src/` changed: Yes. Added standard-library-only R24 performance attribution contracts, input validation, attribution aggregation, and feedback record generation.
- Tests changed: Yes. Added R24 offline attribution preflight tests.
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

R24 keeps new `src/` code on Python standard library only. It adds deterministic replay-output validation, proposal/symbol/source/day attribution, estimated cost derivation, and feedback records.

R24 does not connect to brokers, mutate real accounts, write paper ledger persistence, place live orders, call DeepSeek, perform network calls, train models, update live strategy weights, run Qlib, or run RQAlpha.

R24 consumes R23 `PaperReplayResult` objects as its only input.

## Validation Commands and Results

`python -m compileall src`

Result: not run because bare `python` is not available in this shell.

```text
zsh:1: command not found: python
```

`python -m pytest tests/performance_attribution_preflight`

Result: not run because bare `python` is not available in this shell.

```text
zsh:1: command not found: python
```

`.venv/bin/python -m compileall src`

Result: passed.

`.venv/bin/python -m pytest tests/performance_attribution_preflight`

Result: passed.

```text
platform darwin -- Python 3.12.10, pytest-9.1.1
collected 15 items
15 passed in 0.02s
```

`.venv/bin/python -m pytest`

Result: passed.

```text
platform darwin -- Python 3.12.10, pytest-9.1.1
collected 494 items
494 passed in 0.22s
```

## R24 Performance Attribution Flywheel Preflight Summary

R24 adds an offline deterministic attribution preflight over R23 replay outputs.

The attribution layer validates replay shape, flattens instruction results into proposal attribution records, aggregates by symbol, source, and day, derives estimated costs, and emits feedback records for proposals, symbols, days, and risk rules.

This creates reviewable feedback data for future agent evaluation without model training or live adaptation.

## Risks

- R24 is attribution preflight only; it does not prove trading edge or update any strategy.
- Cash-delta based outcomes are simulation signals, not realized PnL.
- Future readiness gates must still decide how to interpret feedback records.

## Recommended Next Step

Run closure review for R24. A future phase can build a Small-Capital Readiness Gate or Multi-Agent Orchestrator preflight on top of the attribution output.
