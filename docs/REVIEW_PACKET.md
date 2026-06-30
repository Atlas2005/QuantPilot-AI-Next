# Review Packet

## Task Name

P38: Mixed Stock ETF Daily Paper Evaluation.

## Changed Files

- `docs/MIXED_STOCK_ETF_DAILY_PAPER_EVALUATION.md`
- `docs/REVIEW_PACKET.md`
- `src/quantpilot_core/mixed_stock_etf_daily_paper_evaluation/__init__.py`
- `src/quantpilot_core/mixed_stock_etf_daily_paper_evaluation/comparison.py`
- `src/quantpilot_core/mixed_stock_etf_daily_paper_evaluation/contracts.py`
- `src/quantpilot_core/mixed_stock_etf_daily_paper_evaluation/report.py`
- `src/quantpilot_core/mixed_stock_etf_daily_paper_evaluation/scenarios.py`
- `tests/mixed_stock_etf_daily_paper_evaluation/test_mixed_stock_etf_daily_paper_evaluation.py`

## Safety Checks

- `src/` changed: Yes. Added standard-library-only P38 stock-only versus mixed stock/ETF daily paper evaluation.
- Tests changed: Yes. Added deterministic P38 tests.
- Documentation changed: Yes. Added P38 documentation and updated this review packet.
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
- Generic preflight-only gate added: No.

## Value Orientation

P38 compares stock-only daily paper evaluation against mixed stock+ETF daily paper evaluation.

It measures whether ETF inclusion improves fillability, zero-trade days, capital usage, cost drag, diversification proxy, and net PnL after cost. This moves the project toward controlled automated A-share/ETF trading rather than adding another review wall.

## ETF Impact Summary

- Mixed stock+ETF fill-rate delta: `+0.666667`.
- Mixed stock+ETF zero-trade-day delta: `-2`.
- Mixed stock+ETF capital-usage delta: `+0.00677`.
- Mixed stock+ETF cost-drag delta: `-0.004205`.
- Mixed stock+ETF net-PnL-after-cost delta: `+32.5738`.
- ETF small-capital suitability: improved in the deterministic P38 fixture.

## Capital Path Suitability Summary

P38 reports suitability for:

- `1000` CNY stage
- `10000` CNY stage
- `100000` CNY stage

Each stage states whether ETF inclusion helps, whether stock-only remains viable, whether mixed stock+ETF is viable, and whether mixed universe should become the default next-stage paper loop.

## Safety Barrier Status

- Pre-P34 estimated barrier: `185.0%`
- P34/P35/P36/P37/P38 active barrier: `140.0%`
- Target: `<= 140%`
- P38 does not raise the safety barrier. It compares daily paper tradability under the pruned gate set.

## Validation Commands and Results

`.venv/bin/python -m compileall src`

Result: passed.

`.venv/bin/python -m pytest tests/mixed_stock_etf_daily_paper_evaluation`

Result: passed.

```text
platform darwin -- Python 3.12.10, pytest-9.1.1
collected 18 items
18 passed in 0.03s
```

`.venv/bin/python -m pytest`

Result: passed.

```text
platform darwin -- Python 3.12.10, pytest-9.1.1
collected 729 items
729 passed in 0.36s
```

## P38 Summary

P38 adds deterministic stock-only and mixed stock+ETF daily paper scenarios, evaluates both through the P36 daily paper loop, computes ETF impact deltas, reports capital-path suitability for `1000`, `10000`, and `100000` CNY stages, and determines whether mixed stock+ETF should become the next default paper loop.

## Risks

- P38 uses deterministic local scenarios only; it does not approve live trading.
- ETF impact is measured on fixtures, not production market data.
- Cost drag and PnL are local estimates, not broker execution facts.
- Mixed stock+ETF default recommendation should be rechecked as real provider-gated samples mature.

## Recommended Next Step

Use P38 results to set the next paper loop default, then tune ETF selection, sizing, cost model realism, and alpha quality based on the measured stock-only versus mixed stock+ETF deltas.

## Code Evidence Snapshot

- `contracts.py`: defines scenario types, scenario/result contracts, ETF impact summary, capital path suitability, and comparison report.
- `scenarios.py`: builds deterministic stock-only and mixed stock+ETF scenarios with the same capital/window and no external data or broker dependency.
- `comparison.py`: evaluates scenarios through the P36 daily paper loop and computes fill-rate, zero-trade, capital usage, cost drag, PnL, diversification, and capital-stage suitability deltas.
- `report.py`: builds the P38 value report, keeps safety barrier at `<= 140%`, and recommends whether mixed stock+ETF should become the next default.
- `tests`: cover deterministic scenarios, same capital/window, ETF presence/absence, metric deltas, ETF impact, capital-stage suitability, mixed default recommendation, stock-only viability, safety barrier, deterministic ordering, and forbidden runtime behavior.
