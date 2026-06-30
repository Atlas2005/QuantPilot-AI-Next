# Review Packet

## Task Name

P32: Offline Qlib Runtime Spike.

## Changed Files

- `docs/OFFLINE_QLIB_RUNTIME_SPIKE.md`
- `docs/REVIEW_PACKET.md`
- `src/quantpilot_core/offline_qlib_runtime_spike/__init__.py`
- `src/quantpilot_core/offline_qlib_runtime_spike/contracts.py`
- `src/quantpilot_core/offline_qlib_runtime_spike/optional_runner.py`
- `src/quantpilot_core/offline_qlib_runtime_spike/report.py`
- `src/quantpilot_core/offline_qlib_runtime_spike/validation.py`
- `tests/offline_qlib_runtime_spike/test_offline_qlib_runtime_spike.py`

## Safety Checks

- `src/` changed: Yes. Added standard-library-only P32 offline Qlib runtime spike contracts, validation, report generation, and optional manual runner boundary.
- Tests changed: Yes. Added P32 offline Qlib runtime spike tests.
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

P32 keeps new `src/` code on Python standard library only. It adds deterministic offline Qlib runtime plan contracts, local-only dataset boundary validation, explicit/fixture calendar validation, benchmark boundary validation, R28-compatible factor metric handoff checks, readiness report generation, and an optional manual runner interface.

P32 does not run Qlib, run qrun, run agents, connect to brokers, mutate accounts, place orders, import broker SDKs, call DeepSeek, call OpenAI, perform network calls in tests, train models, update live strategy weights, or run RQAlpha.

P32 verifies whether QuantPilot's existing factor metric / Qlib evaluation preflight handoff can be represented as a Qlib-compatible offline runtime plan without making Qlib a required dependency.

## Validation Commands and Results

`python -m compileall src`

Result: not run because bare `python` is not available in this shell.

```text
zsh:1: command not found: python
```

`python -m pytest tests/offline_qlib_runtime_spike`

Result: not run because bare `python` is not available in this shell.

```text
zsh:1: command not found: python
```

`.venv/bin/python -m compileall src`

Result: passed.

`.venv/bin/python -m pytest tests/offline_qlib_runtime_spike`

Result: passed.

```text
platform darwin -- Python 3.12.10, pytest-9.1.1
collected 14 items
14 passed in 0.03s
```

`.venv/bin/python -m pytest`

Result: passed.

```text
platform darwin -- Python 3.12.10, pytest-9.1.1
collected 631 items
631 passed in 0.31s
```

## P32 Offline Qlib Runtime Spike Summary

P32 adds an offline deterministic runtime-plan boundary for future Qlib evaluation work.

The preflight validates local-only dataset paths, explicit or fixture-backed calendars, benchmark declarations, R28-compatible factor metric handoff fields, network-disabled defaults, manual-only runtime execution, integration boundary evidence, and forbidden-scope evidence.

Only clean offline plans return `READY`. Blocking checks return `NOT_READY`. Warning-only plans return `MANUAL_REVIEW`.

## Risks

- P32 is an offline runtime spike boundary only; it does not prove production Qlib runtime compatibility.
- Qlib remains optional and is not a required dependency.
- Optional manual runtime checks remain operator-gated and are not used by default tests.

## Recommended Next Step

Run closure review for P32. A future phase can prepare offline runtime fixtures once P31 stability evidence and P32 runtime-plan evidence are both ready or explicitly manual-reviewed.
