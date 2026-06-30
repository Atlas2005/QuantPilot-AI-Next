# Review Packet

## Task Name

R23: Multi-day Paper Replay.

## Changed Files

- `docs/MULTI_DAY_PAPER_REPLAY.md`
- `docs/REVIEW_PACKET.md`
- `src/quantpilot_core/multi_day_paper_replay/__init__.py`
- `src/quantpilot_core/multi_day_paper_replay/contracts.py`
- `src/quantpilot_core/multi_day_paper_replay/preflight.py`
- `src/quantpilot_core/multi_day_paper_replay/replay.py`
- `tests/multi_day_paper_replay/test_multi_day_paper_replay.py`

## Safety Checks

- `src/` changed: Yes. Added standard-library-only R23 multi-day paper replay contracts, input validation, and in-memory replay orchestration.
- Tests changed: Yes. Added R23 offline multi-day replay tests.
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

R23 keeps new `src/` code on Python standard library only. It adds typed contracts, replay input validation, daily in-memory account-state construction, and deterministic cash/position/sellable carry-forward.

R23 does not connect to brokers, mutate real accounts, write paper ledger persistence, place live orders, call DeepSeek, perform network calls, run Qlib, or run RQAlpha.

R23 consumes R21 `PaperLedgerCandidateInstruction` objects and reuses R22 dry-run logic day by day.

## Validation Commands and Results

`python -m compileall src`

Result: not run because bare `python` is not available in this shell.

```text
zsh:1: command not found: python
```

`python -m pytest tests/multi_day_paper_replay`

Result: not run because bare `python` is not available in this shell.

```text
zsh:1: command not found: python
```

`.venv/bin/python -m compileall src`

Result: passed.

`.venv/bin/python -m pytest tests/multi_day_paper_replay`

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
collected 479 items
479 passed in 0.23s
```

## R23 Multi-day Paper Replay Summary

R23 adds an offline deterministic multi-day replay for daily batches of R21 paper candidate instructions.

The replay validates day ordering, strict date shape, duplicate trading dates, duplicate proposal IDs across replay, account preflight, and A-share T+1 sellability. It carries simulated cash, total positions, and sellable quantities forward across trading days.

Blocked days or instructions do not mutate replay state. Partial replay can continue from the last valid state unless `fail_fast=True`.

## Risks

- R23 is replay-only; it does not write the existing paper ledger or prove execution quality.
- Future attribution/readiness gates still need explicit review.
- Fee estimates and daily prices remain candidate-instruction assumptions, not broker-confirmed facts.

## Recommended Next Step

Run closure review for R23. A future phase can add Performance Attribution Flywheel or Small-Capital Readiness Gate logic on top of the structured replay result.
