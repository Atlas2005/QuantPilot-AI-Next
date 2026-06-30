# Review Packet

## Task Name

P36: Daily Paper Trading Loop with Tradability Metrics.

## Changed Files

- `docs/DAILY_PAPER_TRADING_LOOP_TRADABILITY_METRICS.md`
- `docs/REVIEW_PACKET.md`
- `src/quantpilot_core/daily_paper_trading_loop_tradability_metrics/__init__.py`
- `src/quantpilot_core/daily_paper_trading_loop_tradability_metrics/contracts.py`
- `src/quantpilot_core/daily_paper_trading_loop_tradability_metrics/loop.py`
- `src/quantpilot_core/daily_paper_trading_loop_tradability_metrics/metrics.py`
- `src/quantpilot_core/daily_paper_trading_loop_tradability_metrics/report.py`
- `tests/daily_paper_trading_loop_tradability_metrics/test_daily_paper_trading_loop_tradability_metrics.py`

## Safety Checks

- `src/` changed: Yes. Added standard-library-only daily paper trading loop contracts, loop execution, metrics aggregation, and report generation.
- Tests changed: Yes. Added deterministic P36 daily paper trading loop tests.
- Documentation changed: Yes. Added P36 documentation and updated this review packet.
- Dependencies changed: No.
- Packages installed: No.
- Packages uninstalled: No.
- `pyproject.toml` changed: No.
- Market data/API used during implementation: No.
- Provider API called during implementation: No.
- Network calls in default tests: No.
- Production data assets written: No.
- Real data fetched: No.
- DeepSeek/API call added: No.
- OpenAI/API call added: No.
- Model training added: No.
- Live strategy weight update added: No.
- Real account API read: No.
- Broker connection added: No.
- Vendor broker SDK imported: No.
- Broker credentials handling added: No.
- Live order path added: No.
- Real order placement added: No.
- Real alpha evidence produced: No.
- Profitability claim made: No.

## Language / Runtime Decision

P36 keeps new implementation code on Python standard library only. It reuses the P34 deterministic tradability and fill simulation rather than creating another backtest engine, broker route, or generic preflight wall.

The daily loop consumes deterministic multi-day signals, simulates A-share order intent fillability, updates local paper cash and positions, aggregates tradability/cost/PnL/capital metrics, and recommends the next improvement target.

## Safety Barrier

- Pre-P34 estimated barrier: `185.0%`
- P34/P35/P36 active barrier: `140.0%`
- Target: `<= 140%`
- P36 does not raise the safety barrier. It measures fillability under the pruned gate set.

## Validation Commands and Results

`.venv/bin/python -m compileall src`

Result: passed.

`.venv/bin/python -m pytest tests/daily_paper_trading_loop_tradability_metrics`

Result: passed.

```text
platform darwin -- Python 3.12.10, pytest-9.1.1
collected 13 items
13 passed in 0.02s
```

`.venv/bin/python -m pytest`

Result: passed.

```text
platform darwin -- Python 3.12.10, pytest-9.1.1
collected 692 items
692 passed in 0.35s
```

## P36 Summary

P36 adds a deterministic daily paper trading loop with tradability metrics.

It answers whether deterministic signals can produce order intents across multiple days, whether at least one simulated fill occurs, how cash and positions move after local paper fills, what costs/taxes/slippage were incurred, whether net PnL after cost is positive/zero/negative, which days had zero trades, and what exact rejection reasons explain those zero-trade days.

## Risks

- P36 is deterministic paper simulation only; it does not approve live trading.
- PnL, turnover, drawdown, and cost figures are local estimates, not broker execution facts.
- The loop relies on P34 simulation rules and fixture-like inputs; production data quality and broker behavior remain outside this patch.

## Recommended Next Step

Use P36 daily paper loop output to tune alpha quality, sizing, tradability constraints, cost model realism, or deterministic data quality before any broker-facing phase proceeds.

## Code Evidence Snapshot

- `contracts.py`: defines daily loop input, day result, loop report, tradability metrics, adjustment recommendation, and zero-trade diagnosis summary.
- `loop.py`: runs deterministic day-by-day fill simulation, updates local paper cash/positions, and emits daily recommendations.
- `metrics.py`: aggregates fill rate, costs, net PnL, capital usage, turnover, drawdown, zero-trade reasons, and suspected overblocking days.
- `report.py`: builds the value-oriented P36 report and selects the next improvement target.
- `tests`: cover deterministic multi-day input, all day outputs, intents, fills, cash/position updates, cost aggregation, fill rate, zero-trade diagnosis, net PnL, capital usage, turnover/drawdown, overblocking counts, safety barrier limit, deterministic ordering, and forbidden runtime behavior.
