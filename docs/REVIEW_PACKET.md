# Review Packet

## Task Name

R25: Small-Capital Readiness Gate.

## Changed Files

- `docs/SMALL_CAPITAL_READINESS_GATE.md`
- `docs/REVIEW_PACKET.md`
- `src/quantpilot_core/small_capital_readiness_gate/__init__.py`
- `src/quantpilot_core/small_capital_readiness_gate/contracts.py`
- `src/quantpilot_core/small_capital_readiness_gate/gate.py`
- `src/quantpilot_core/small_capital_readiness_gate/metrics.py`
- `src/quantpilot_core/small_capital_readiness_gate/preflight.py`
- `tests/small_capital_readiness_gate/test_small_capital_readiness_gate.py`

## Safety Checks

- `src/` changed: Yes. Added standard-library-only R25 readiness gate contracts, metric calculations, input validation, and decision logic.
- Tests changed: Yes. Added R25 offline small-capital readiness gate tests.
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

R25 keeps new `src/` code on Python standard library only. It adds deterministic readiness metrics and a PASS / FAIL / MANUAL_REVIEW decision over R23 replay and R24 attribution outputs.

R25 does not connect to brokers, mutate real accounts, write paper ledger persistence, place live orders, call DeepSeek, perform network calls, train models, update live strategy weights, run Qlib, or run RQAlpha.

R25 consumes R23 `PaperReplayResult` and R24 `PerformanceAttributionResult` objects as its only evidence inputs.

## Validation Commands and Results

`python -m compileall src`

Result: not run because bare `python` is not available in this shell.

```text
zsh:1: command not found: python
```

`python -m pytest tests/small_capital_readiness_gate`

Result: not run because bare `python` is not available in this shell.

```text
zsh:1: command not found: python
```

`.venv/bin/python -m compileall src`

Result: passed.

`.venv/bin/python -m pytest tests/small_capital_readiness_gate`

Result: passed.

```text
platform darwin -- Python 3.12.10, pytest-9.1.1
collected 16 items
16 passed in 0.02s
```

`.venv/bin/python -m pytest`

Result: passed.

```text
platform darwin -- Python 3.12.10, pytest-9.1.1
collected 510 items
510 passed in 0.23s
```

## R25 Small-Capital Readiness Gate Summary

R25 adds an offline deterministic readiness gate over replay and attribution evidence.

The gate computes replay-day count, blocked-day ratio, blocked-instruction ratio, accepted-instruction count, critical-risk count, estimated-cost ratio, negative-feedback ratio, cash-drawdown ratio, and optional position concentration.

Hard metric failures return `FAIL`. Warning metrics without hard failures return `MANUAL_REVIEW`. Full pass returns `PASS`.

## Risks

- R25 is a readiness preflight only; it does not approve live trading or broker use.
- Metric thresholds are conservative defaults and may need review before any broker sandbox phase.
- Replay and attribution quality still depend on upstream dry-run and evidence quality.

## Recommended Next Step

Run closure review for R25. A future phase can introduce a broker sandbox adapter preflight or Multi-Agent Orchestrator preflight gated behind this readiness decision.
