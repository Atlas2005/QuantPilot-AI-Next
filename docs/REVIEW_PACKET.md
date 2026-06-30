# Review Packet

## Task Name

R20: Account Profile / Broker Config Preflight.

## Changed Files

- `docs/ACCOUNT_PROFILE_BROKER_CONFIG_PREFLIGHT.md`
- `docs/REVIEW_PACKET.md`
- `src/quantpilot_core/account_profile_preflight/__init__.py`
- `src/quantpilot_core/account_profile_preflight/contracts.py`
- `src/quantpilot_core/account_profile_preflight/limits.py`
- `src/quantpilot_core/account_profile_preflight/preflight.py`
- `tests/account_profile_preflight/test_account_profile_preflight.py`

## Safety Checks

- `src/` changed: Yes. Added standard-library-only R20 account profile and broker config contracts, limit helpers, and preflight validation.
- Tests changed: Yes. Added R20 offline account profile preflight tests.
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
- Real account API read: No.
- Broker connection added: No.
- Order generation added: No.
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

R20 keeps new `src/` code on Python standard library only. It adds typed contracts, deterministic account/broker validation, sellable quantity normalization, and concentration weight calculations.

R20 does not connect to brokers, read account APIs, generate orders, place trades, call DeepSeek, perform network calls, run Qlib, or run RQAlpha.

R20 strengthens the capital/account-aware boundary that future AI action proposal, paper ledger, and Market Reality Sandbox flows must satisfy before any downstream dry path proceeds.

## Validation Commands and Results

`python -m compileall src`

Result: not run because bare `python` is not available in this shell.

```text
zsh:1: command not found: python
```

`python -m pytest tests/account_profile_preflight`

Result: not run because bare `python` is not available in this shell.

```text
zsh:1: command not found: python
```

`.venv/bin/python -m compileall src`

Result: passed.

`.venv/bin/python -m pytest tests/account_profile_preflight`

Result: passed.

```text
platform darwin -- Python 3.12.10, pytest-9.1.1
collected 21 items
21 passed in 0.01s
```

`.venv/bin/python -m pytest`

Result: passed.

```text
platform darwin -- Python 3.12.10, pytest-9.1.1
collected 426 items
426 passed in 0.19s
```

## R20 Account Profile / Broker Config Preflight Summary

R20 adds an offline deterministic preflight for explicit account and broker configuration.

The preflight validates account identity, evidence, cash shape, positions, fees, broker capabilities, permissions, risk limits, and concentration limits.

The result returns structured risk flags plus deterministic normalized maps:

- sellable quantity by symbol
- position weight by symbol
- industry weight

Critical flags make the preflight fail.

## Risks

- R20 is a contract/preflight layer only; it does not prove broker compatibility or account API correctness.
- Future adapters must still map real or paper account snapshots into these contracts before sandbox use.
- Fee and slippage settings are configurable assumptions, not execution evidence.

## Recommended Next Step

Run closure review for R20. The next phase can connect account profile preflight to an AI Action Proposal -> Paper Ledger Bridge while keeping the bridge offline and sandbox-only.
