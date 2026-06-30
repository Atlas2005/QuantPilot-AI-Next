# Review Packet

## Task Name

P35: Qlib Offline Tradability Evaluation Fixture.

## Changed Files

- `docs/QLIB_OFFLINE_TRADABILITY_EVALUATION_FIXTURE.md`
- `docs/REVIEW_PACKET.md`
- `src/quantpilot_core/qlib_offline_tradability_evaluation_fixture/__init__.py`
- `src/quantpilot_core/qlib_offline_tradability_evaluation_fixture/contracts.py`
- `src/quantpilot_core/qlib_offline_tradability_evaluation_fixture/evaluation.py`
- `src/quantpilot_core/qlib_offline_tradability_evaluation_fixture/fixture.py`
- `src/quantpilot_core/qlib_offline_tradability_evaluation_fixture/report.py`
- `tests/qlib_offline_tradability_evaluation_fixture/test_qlib_offline_tradability_evaluation_fixture.py`

## Safety Checks

- `src/` changed: Yes. Added standard-library-only P35 Qlib offline tradability evaluation fixture contracts, deterministic fixtures, evaluation, and report generation.
- Tests changed: Yes. Added P35 offline Qlib tradability evaluation fixture tests.
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

P35 keeps new `src/` code on Python standard library only. It adds deterministic A-share-like daily bars, deterministic signals, Qlib-compatible metadata, P34 fill-loop evaluation, fill-rate reporting, cost-after-fill evaluation, zero-trade diagnosis, and next-improvement targeting.

P35 does not install or import broker SDKs, connect to brokers, read real accounts, place orders, create credential handling, call DeepSeek, call OpenAI, perform network calls in tests, train models, update live strategy weights, run Qlib/qrun, or run RQAlpha.

P35 moves from gate pruning to offline tradability evaluation. It does not add another generic safety/preflight wall.

## Safety Barrier Before / After

- Before P34: `185.0%`
- P34/P35 active barrier: `140.0%`
- Target: `<= 140%`
- P35 keeps the safety barrier at or below target while measuring fillability.

## Validation Commands and Results

`python -m compileall src`

Result: not run because bare `python` is not available in this shell.

```text
zsh:1: command not found: python
```

`python -m pytest tests/qlib_offline_tradability_evaluation_fixture`

Result: not run because bare `python` is not available in this shell.

```text
zsh:1: command not found: python
```

`.venv/bin/python -m compileall src`

Result: passed.

`.venv/bin/python -m pytest tests/qlib_offline_tradability_evaluation_fixture`

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
collected 679 items
679 passed in 0.34s
```

## P35 Qlib Offline Tradability Evaluation Fixture Summary

P35 creates deterministic local fixture objects for Qlib-compatible offline tradability evaluation.

The fixture includes A-share-like daily bars, deterministic signals, expected order intents, expected simulated fills, expected fee/slippage/tax, and expected zero-trade diagnosis. Evaluation reuses P34 fill simulation and emits fill rate, cost-after-fill, net PnL after cost, capital-used ratio, drawdown/turnover estimates, and Qlib compatibility notes.

P35 answers whether signals became order intents, whether intents became simulated fills, whether fill rate was positive, whether net PnL after cost was positive/zero/negative, and what should improve next.

## Risks

- P35 uses deterministic local fixtures only; it does not approve live trading.
- Qlib compatibility is metadata-only; Qlib is not imported, required, or run.
- Fill estimates are local approximations and not production execution guarantees.

## Recommended Next Step

Run closure review for P35. The next phase should use offline fixture results to improve alpha quality, sizing, liquidity/tradability, cost model accuracy, or data fixture quality before any optional runtime spike proceeds.

## Code Evidence Snapshot

- `contracts.py`: defines offline daily bars, tradability fixture dataset, signal fixture, evaluation window, Qlib-compatible plan, evaluation result, and evaluation report.
- `fixture.py`: creates deterministic local A-share-like bars, deterministic signals, expected order/fill/cost diagnostics, zero-trade fixture, evaluation window, and Qlib-compatible metadata.
- `evaluation.py`: validates local-only metadata, reuses P34 fill simulation, computes fill rate, costs, PnL after costs, capital used ratio, drawdown/turnover estimates, and compatibility notes.
- `report.py`: answers produced-signals/intents/fills, fill-rate positivity, PnL sign, safety barrier status, overblocking status, and next-improvement target.
- `tests`: cover deterministic bars/signals, intent/fill generation, cost/tax/slippage, fill rate, zero-trade reasons, local-only dataset acceptance, remote URI rejection, no Qlib requirement/import, no default qrun/runtime execution, Qlib compatibility metadata, deterministic ordering, safety barrier <= 140, and no broker/network/LLM behavior.
