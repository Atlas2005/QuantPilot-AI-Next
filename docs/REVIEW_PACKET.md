# Review Packet

## Task Name

P37: Alpha, Sizing, and ETF Universe Tuning Loop.

## Changed Files

- `docs/ALPHA_SIZING_ETF_UNIVERSE_TUNING_LOOP.md`
- `docs/REVIEW_PACKET.md`
- `src/quantpilot_core/alpha_sizing_etf_universe_tuning_loop/__init__.py`
- `src/quantpilot_core/alpha_sizing_etf_universe_tuning_loop/contracts.py`
- `src/quantpilot_core/alpha_sizing_etf_universe_tuning_loop/report.py`
- `src/quantpilot_core/alpha_sizing_etf_universe_tuning_loop/sizing.py`
- `src/quantpilot_core/alpha_sizing_etf_universe_tuning_loop/tuning.py`
- `src/quantpilot_core/alpha_sizing_etf_universe_tuning_loop/universe.py`
- `tests/alpha_sizing_etf_universe_tuning_loop/test_alpha_sizing_etf_universe_tuning_loop.py`

## Safety Checks

- `src/` changed: Yes. Added standard-library-only P37 ETF universe, sizing, tuning, and report boundary.
- Tests changed: Yes. Added deterministic P37 tests.
- Documentation changed: Yes. Added P37 documentation and updated this review packet.
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

## Value Orientation

P37 expands the tradable universe from A-share stocks only to A-share stocks plus exchange-listed ETFs, then tunes alpha and sizing toward actual tradability.

The patch does not add another generic safety/preflight wall. It keeps the active barrier at or below `140%`, separates ETF rules from stock rules, and produces deterministic recommendations that can feed the daily paper loop.

## ETF Coverage Summary

- ETF category is explicit and mandatory.
- ETF candidates cannot silently become stock candidates.
- ETF minimum trade unit is `100` units.
- ETF minimum tick is `0.001`.
- Equity ETFs default to `T+1`.
- Bond, gold, cross-border, and money-market ETFs may use `T+0` only when explicitly declared.
- ETF fee model is separate from the stock stamp-duty model.
- Universe reports stock and ETF counts separately.
- ETF candidates can be prioritized for small-capital diversification without hard-blocking stock candidates.

## Safety Barrier Status

- Pre-P34 estimated barrier: `185.0%`
- P34/P35/P36/P37 active barrier: `140.0%`
- Target: `<= 140%`
- P37 does not raise the safety barrier. It improves fillability and candidate selection under the pruned gate set.

## Validation Commands and Results

`.venv/bin/python -m compileall src`

Result: passed.

`.venv/bin/python -m pytest tests/alpha_sizing_etf_universe_tuning_loop`

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
collected 711 items
711 passed in 0.35s
```

## P37 Summary

P37 adds a deterministic alpha, sizing, and ETF universe tuning loop.

It accepts valid stock and ETF candidates, rejects invalid ETF candidates with missing categories, builds ETF-specific rule profiles, recommends valid 100-unit sizing, scores alpha/sizing/tradability/cost-after-fill, and reports whether ETF inclusion improves small-capital tradability.

## Risks

- P37 is deterministic tuning only; it does not approve live trading.
- ETF rule profiles are conservative local representations and not broker execution guarantees.
- Cost drag and alpha quality scores are deterministic estimates, not real performance evidence.
- The next daily paper loop should validate whether ETF inclusion improves fill rate and net PnL after cost.

## Recommended Next Step

Feed P37 mixed stock/ETF sizing recommendations into the P36 daily paper loop and compare fill rate, capital usage, cost drag, and net PnL after cost against the stock-only fixture.

## Code Evidence Snapshot

- `contracts.py`: defines instrument types, ETF categories, tradable instruments, rule profiles, alpha quality, sizing candidates, tuning decisions, universe selection, and report contracts.
- `universe.py`: validates stocks and ETFs separately, rejects unknown types and ETFs without categories, builds ETF-specific rule profiles, and reports stock/ETF counts.
- `sizing.py`: rounds recommendations to valid trade units, estimates capital usage, cost drag, tradability score, and zero-trade risk reduction.
- `tuning.py`: combines alpha quality, sizing, tradability, and cost-after-fill scores into deterministic recommended actions.
- `report.py`: builds the P37 value report, preserves the `<= 140%` safety barrier, and answers ETF/sizing/cost improvement questions.
- `tests`: cover stock and ETF acceptance, missing ETF category rejection, ETF-not-stock behavior, ETF settlement/tick/unit/fee rules, separate counts, small-capital ETF preference, sizing zero-trade reduction, cost drag, safety barrier, deterministic ordering, and forbidden runtime behavior.
