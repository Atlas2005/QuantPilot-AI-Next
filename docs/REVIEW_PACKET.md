# Review Packet

## Task Name

P31: Real Data Stability Trial.

## Changed Files

- `docs/REAL_DATA_STABILITY_TRIAL.md`
- `docs/REVIEW_PACKET.md`
- `src/quantpilot_core/real_data_stability_trial/__init__.py`
- `src/quantpilot_core/real_data_stability_trial/contracts.py`
- `src/quantpilot_core/real_data_stability_trial/manual_runner.py`
- `src/quantpilot_core/real_data_stability_trial/report.py`
- `src/quantpilot_core/real_data_stability_trial/validation.py`
- `tests/real_data_stability_trial/test_real_data_stability_trial.py`

## Safety Checks

- `src/` changed: Yes. Added standard-library-only P31 real data stability trial contracts, validation, report building, and optional manual runner boundary.
- Tests changed: Yes. Added P31 offline real data stability trial tests.
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

P31 keeps new `src/` code on Python standard library only. It adds deterministic A-share sample universe validation, provider trial config validation, provider row shape checks, OHLCV numeric sanity checks, provider stability reports, fallback compatibility warnings, and an optional manual runner interface.

P31 does not run Qlib, run qrun, run agents, connect to brokers, mutate accounts, place orders, import broker SDKs, call DeepSeek, perform network calls in tests, train models, update live strategy weights, or run RQAlpha.

P31 starts the post-R30 real-data stability phase while keeping provider-specific real network access optional/manual only.

## Validation Commands and Results

`python -m compileall src`

Result: not run because bare `python` is not available in this shell.

```text
zsh:1: command not found: python
```

`python -m pytest tests/real_data_stability_trial`

Result: not run because bare `python` is not available in this shell.

```text
zsh:1: command not found: python
```

`.venv/bin/python -m compileall src`

Result: passed.

`.venv/bin/python -m pytest tests/real_data_stability_trial`

Result: passed.

```text
platform darwin -- Python 3.12.10, pytest-9.1.1
collected 20 items
20 passed in 0.03s
```

`.venv/bin/python -m pytest`

Result: passed.

```text
platform darwin -- Python 3.12.10, pytest-9.1.1
collected 617 items
617 passed in 0.30s
```

## P31 Real Data Stability Trial Summary

P31 adds an offline deterministic real data stability trial layer for supplied provider rows and fixed A-share sample universes.

The trial validates universe metadata, provider configs, provider row shape, required field coverage, symbol/date coverage, missing-row ratio, duplicate rows, OHLCV numeric sanity, network/manual-review boundaries, and provider fallback compatibility across reports.

Only clean provider evidence returns `STABLE`. Critical validation flags or failed checks return `UNSTABLE`. Warning-only checks return `MANUAL_REVIEW`.

## Risks

- P31 validates supplied rows only; it does not approve a production data provider.
- AkShare and BaoStock remain optional and are not required dependencies.
- Optional manual network trials remain operator-gated and are not used by default tests.

## Recommended Next Step

Run closure review for P31. P32 can use P31 stability evidence to prepare an offline Qlib runtime spike while keeping provider network access, Qlib runtime, and broker work behind explicit manual gates.
