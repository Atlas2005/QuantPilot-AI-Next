# Review Packet

## Task Name

R26: Broker Sandbox Adapter Preflight.

## Changed Files

- `docs/BROKER_SANDBOX_ADAPTER_PREFLIGHT.md`
- `docs/REVIEW_PACKET.md`
- `src/quantpilot_core/broker_sandbox_adapter_preflight/__init__.py`
- `src/quantpilot_core/broker_sandbox_adapter_preflight/adapter.py`
- `src/quantpilot_core/broker_sandbox_adapter_preflight/contracts.py`
- `src/quantpilot_core/broker_sandbox_adapter_preflight/preflight.py`
- `tests/broker_sandbox_adapter_preflight/test_broker_sandbox_adapter_preflight.py`

## Safety Checks

- `src/` changed: Yes. Added standard-library-only R26 broker sandbox adapter preflight contracts, validation, conversion, and handoff decision logic.
- Tests changed: Yes. Added R26 offline broker sandbox adapter preflight tests.
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

R26 keeps new `src/` code on Python standard library only. It adds deterministic broker-sandbox handoff contracts, readiness checks, account/broker permission checks, mode semantics, and candidate-instruction conversion.

R26 does not connect to brokers, mutate accounts, place orders, import broker SDKs, call DeepSeek, perform network calls, train models, update live strategy weights, run Qlib, or run RQAlpha.

R26 consumes R21/R22 candidate instructions, R20 account profiles, and R25 readiness results.

## Validation Commands and Results

`python -m compileall src`

Result: not run because bare `python` is not available in this shell.

```text
zsh:1: command not found: python
```

`python -m pytest tests/broker_sandbox_adapter_preflight`

Result: not run because bare `python` is not available in this shell.

```text
zsh:1: command not found: python
```

`.venv/bin/python -m compileall src`

Result: passed.

`.venv/bin/python -m pytest tests/broker_sandbox_adapter_preflight`

Result: passed.

```text
platform darwin -- Python 3.12.10, pytest-9.1.1
collected 19 items
19 passed in 0.02s
```

`.venv/bin/python -m pytest`

Result: passed.

```text
platform darwin -- Python 3.12.10, pytest-9.1.1
collected 529 items
529 passed in 0.24s
```

## R26 Broker Sandbox Adapter Preflight Summary

R26 adds an offline deterministic preflight for broker sandbox handoff records.

The preflight validates readiness PASS, account status, broker permissions, A-share capability, query-only behavior, adapter mode, evidence, notional consistency, A-share lot size, cash sufficiency, and sellable quantity.

Only valid `BROKER_SANDBOX` instructions can be accepted for sandbox handoff. `PAPER_ONLY`, `READ_ONLY_CHECK`, and `HOLD` do not claim executable broker readiness.

## Risks

- R26 is preflight only; it does not implement or prove any broker adapter.
- Future broker sandbox work must still remain behind readiness, account, and manual review gates.
- Broker-specific rule gaps remain unknown until a future adapter design phase.

## Recommended Next Step

Run closure review for R26. A future phase can define a broker sandbox adapter interface or Multi-Agent Orchestrator preflight while keeping this preflight as the handoff boundary.
