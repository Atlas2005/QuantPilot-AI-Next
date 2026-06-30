# Review Packet

## Task Name

P39: Real Provider Mixed ETF Paper Replay.

## Changed Files

- `docs/REAL_PROVIDER_MIXED_ETF_PAPER_REPLAY.md`
- `docs/REVIEW_PACKET.md`
- `src/quantpilot_core/real_provider_mixed_etf_paper_replay/__init__.py`
- `src/quantpilot_core/real_provider_mixed_etf_paper_replay/comparison.py`
- `src/quantpilot_core/real_provider_mixed_etf_paper_replay/contracts.py`
- `src/quantpilot_core/real_provider_mixed_etf_paper_replay/replay.py`
- `src/quantpilot_core/real_provider_mixed_etf_paper_replay/report.py`
- `src/quantpilot_core/real_provider_mixed_etf_paper_replay/sample_bridge.py`
- `tests/real_provider_mixed_etf_paper_replay/test_real_provider_mixed_etf_paper_replay.py`

## Safety Checks

- `src/` changed: Yes. Added standard-library-only P39 provider-like local sample bridge, replay, comparison, and report boundary.
- Tests changed: Yes. Added deterministic P39 tests.
- Documentation changed: Yes. Added P39 documentation and updated this review packet.
- Dependencies changed: No.
- Packages installed: No.
- Packages uninstalled: No.
- `pyproject.toml` changed: No.
- Market data/API used during implementation: No.
- Provider API called during implementation: No.
- Live/remote provider fetch in default tests: No.
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

P39 moves from deterministic fixture-only mixed stock/ETF comparison toward provider-gated local sample replay.

It validates provider-like local sample quality, replays accepted mixed stock/ETF samples through the daily paper loop, compares replay output against the P38 mixed baseline, and reports whether ETF inclusion remains useful with provider-like local inputs.

## Provider Sample Quality Summary

- Local-only sample source is required.
- Stock and ETF rows are both required for mixed replay.
- ETF category is explicit and mandatory.
- Required OHLCV-like fields are validated.
- Dates must be sorted.
- Duplicate symbol/date rows are rejected.
- Rows beyond the evaluation window are rejected.
- Missing close or volume blocks replay.

## ETF Replay Impact Summary

- Provider-like replay preserves mixed stock+ETF fillability in the deterministic local fixture.
- Provider-like replay produces simulated fills in the deterministic local fixture.
- Provider-like replay reports cost/tax/slippage and net PnL after cost.
- Provider-like replay comparison notes include fill-rate, zero-trade, cost-drag, capital-usage, and net-PnL deltas versus the P38 mixed baseline.

## Capital Path Suitability Summary

P39 reports suitability for:

- `1000` CNY stage
- `10000` CNY stage
- `100000` CNY stage

Each stage states whether ETF inclusion helps, whether stock-only remains viable, whether mixed stock+ETF is viable, and whether mixed stock+ETF should remain the default next-stage paper loop.

## Safety Barrier Status

- Pre-P34 estimated barrier: `185.0%`
- P34 through P39 active barrier: `140.0%`
- Target: `<= 140%`
- P39 does not raise the safety barrier. It moves the mixed ETF loop toward provider-gated local sample replay under the pruned gate set.

## Validation Commands and Results

`.venv/bin/python -m compileall src`

Result: passed.

`.venv/bin/python -m pytest tests/real_provider_mixed_etf_paper_replay`

Result: passed.

```text
platform darwin -- Python 3.12.10, pytest-9.1.1
collected 21 items
21 passed in 0.03s
```

`.venv/bin/python -m pytest`

Result: passed.

```text
platform darwin -- Python 3.12.10, pytest-9.1.1
collected 750 items
750 passed in 0.37s
```

## P39 Summary

P39 adds a provider-like local sample bridge for mixed stock/ETF daily bars, validates sample quality, converts accepted samples into a mixed daily paper replay, compares replay output against the P38 mixed baseline, and reports capital-stage suitability for `1000`, `10000`, and `100000` CNY stages.

## Risks

- P39 uses deterministic local provider-like samples only; it does not approve live trading.
- Provider replay quality depends on future approved sample governance.
- Cost drag and PnL are local estimates, not broker execution facts.
- Real provider adapters remain optional and are not called by default tests.

## Recommended Next Step

Use P39 results to improve provider sample quality and then run the mixed stock/ETF daily paper loop on approved provider-gated small samples with alpha, sizing, and cost-model tuning.

## Code Evidence Snapshot

- `contracts.py`: defines source types, replay input, mixed sample, validation result, replay result, and report contracts.
- `sample_bridge.py`: validates local-only source, OHLCV fields, ETF category, sorted dates, duplicate rows, future rows, close/volume presence, and mixed stock/ETF coverage.
- `replay.py`: converts accepted provider-like samples into P36 daily paper input and reports replay metrics.
- `comparison.py`: compares provider replay to the P38 mixed baseline and reports capital-stage suitability.
- `report.py`: builds the P39 report, keeps safety barrier at `<= 140%`, and selects the next improvement target.
- `tests`: cover accepted local sample, rejected remote source, missing ETF category, missing fields, duplicate rows, unsorted dates, future rows, missing close/volume, mixed sample requirement, replay metrics, baseline comparison, capital stages, safety barrier, deterministic ordering, and forbidden runtime behavior.
