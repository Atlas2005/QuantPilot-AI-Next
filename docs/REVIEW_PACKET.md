# Review Packet

## Task Name

R2: Market Reality Sandbox Contracts quality patch.

## Changed Files

- `docs/MARKET_REALITY_SANDBOX_CONTRACTS.md`
- `src/quantpilot_core/market_reality/__init__.py`
- `src/quantpilot_core/market_reality/contracts.py`
- `src/quantpilot_core/market_reality/validation.py`
- `tests/market_reality/test_market_reality_contracts.py`
- `tests/market_reality/test_market_reality_validation.py`
- `README.md`
- `docs/CURRENT_PROJECT_STATE.md`
- `docs/DECISIONS.md`
- `docs/NEXT_CHAT_HANDOFF.md`
- `docs/REVIEW_PACKET.md`

## Safety Checks

- `src/` changed: Yes. Added standard-library-only R2 Market Reality Sandbox contracts and validation helpers, including explicit capital constraint validation.
- Tests changed: Yes. Added R2 Market Reality Sandbox contract and validation tests, including capital-aware validation coverage.
- Integration matrix changed: No.
- Open-source decision table changed: No.
- Manual probe scripts changed: No.
- Dependencies changed: No.
- Packages installed: No.
- Packages uninstalled: No.
- `pyproject.toml` changed: No.
- Market data/API used during implementation: No.
- Manual probes run: No.
- Real data fetched: No.
- Raw data committed: No.
- Any data source approved: No.
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

R2 keeps new `src/` code on Python standard library only. No provider, analytics, backtest, broker, or agent framework package is a project dependency.

R2 adds contracts and validation helpers only. It does not implement a full simulator, backtest engine, risk engine, factor analysis engine, market calendar system, portfolio accounting engine, broker integration, live trading, or order execution path.

R2 respects R1.1 open-source integration guardrails by representing mature open-source projects as adapter boundaries, benchmarks, or future integration candidates.

The R2 quality patch strengthens capital-aware validation for max order notional, max position notional, cash usage ratio, minimum cash reserve, and capital mode.

## Validation Commands and Results

`python -m compileall src`

Result: passed via `.venv/bin/python -m compileall src`.

`python -m pytest`

Result: passed via `.venv/bin/python -m pytest`.

```text
platform darwin -- Python 3.12.10, pytest-9.1.1
collected 173 items
173 passed in 0.09s
```

`git status -sb`

Result:

```text
## r2-market-reality-sandbox-contracts
 M README.md
 M docs/CURRENT_PROJECT_STATE.md
 M docs/DECISIONS.md
 M docs/NEXT_CHAT_HANDOFF.md
 M docs/REVIEW_PACKET.md
?? docs/MARKET_REALITY_SANDBOX_CONTRACTS.md
?? src/quantpilot_core/market_reality/
?? tests/market_reality/
```

## R2 Market Reality Sandbox Summary

R2 adds a Market Reality Sandbox contract layer for A-share trading reality, capital/account constraints, sandbox order drafts, fill assumptions, costs, slippage, provider failure, data latency, and timestamp audit assumptions.

The R2 quality patch makes capital-aware validation explicit for scenario-level capital constraints and order-level notional, reserve, and cash-usage checks.

R2 does not add real data, broker integration, live trading, or order execution.

R2 does not implement full backtest, risk, factor, calendar, or portfolio accounting engines. Mature open-source candidates remain adapter boundaries, benchmarks, or future integration candidates.

## Risks

- Matrix risk labels are preliminary and require future upstream/license review.
- Architecture targets may still need contract design before implementation.
- R2 contracts are validation shapes only; they do not install, select, or approve external packages.
- The Phase 7E readiness gate still blocks real alpha validation until updated, reviewed, and explicitly approved.

## Recommended Next Step

ChatGPT should perform R2 closure review. The next phase should move toward controlled adapter/probe integration or sandbox validation using fixtures, not live trading.
