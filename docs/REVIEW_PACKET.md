# Review Packet

## Task Name

P40: AI + Open-Source Provider Small Sample Mixed ETF Replay.

## Changed Files

- `docs/AI_OPEN_SOURCE_PROVIDER_SMALL_SAMPLE_MIXED_ETF_REPLAY.md`
- `docs/REVIEW_PACKET.md`
- `src/quantpilot_core/ai_open_source_provider_small_sample_mixed_etf_replay/__init__.py`
- `src/quantpilot_core/ai_open_source_provider_small_sample_mixed_etf_replay/ai_shadow_agents.py`
- `src/quantpilot_core/ai_open_source_provider_small_sample_mixed_etf_replay/comparison.py`
- `src/quantpilot_core/ai_open_source_provider_small_sample_mixed_etf_replay/contracts.py`
- `src/quantpilot_core/ai_open_source_provider_small_sample_mixed_etf_replay/open_source_provider_bridge.py`
- `src/quantpilot_core/ai_open_source_provider_small_sample_mixed_etf_replay/replay_adjustment.py`
- `src/quantpilot_core/ai_open_source_provider_small_sample_mixed_etf_replay/report.py`
- `tests/ai_open_source_provider_small_sample_mixed_etf_replay/test_ai_open_source_provider_small_sample_mixed_etf_replay.py`

## Safety Checks

- `src/` changed: Yes. Added standard-library-only P40 open-source provider boundary, AI shadow agents, replay adjustment, comparison, and report chain.
- Tests changed: Yes. Added deterministic P40 tests.
- Documentation changed: Yes. Added P40 documentation and updated this review packet.
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
- Runtime LLM call added: No.
- Model training added: No.
- Live strategy weight update added: No.
- Real account API read: No.
- Broker connection added: No.
- Vendor broker SDK imported: No.
- Broker credentials handling added: No.
- Live order path added: No.
- Real order placement added: No.
- Qlib runtime run by default: No.
- RQAlpha runtime run by default: No.
- Real alpha evidence produced: No.
- Profitability claim made: No.
- Generic preflight-only gate added: No.

## Value Orientation

P40 brings AI shadow decisioning and open-source provider boundaries into the mixed stock+ETF paper replay chain.

It models approved local exports from AkShare, BaoStock, and manual approved exports, runs deterministic AI shadow-agent recommendations, applies bounded replay adjustments, and creates Qlib/RQAlpha handoff metadata without calling live runtimes.

## Open-Source Integration Summary

- AkShare boundary modeled as approved local export schema.
- BaoStock boundary modeled as approved local export schema.
- Manual approved export boundary modeled.
- Provider schema mapping is explicit.
- Qlib offline AI quant backtest handoff metadata is produced.
- RQAlpha later event-driven backtest handoff metadata is produced.
- No optional provider or backtest package is required for default tests.

## AI Shadow Agent Summary

P40 deterministic shadow agents cover:

- market data quality
- alpha research
- ETF selection
- sizing/capital
- cost/execution
- portfolio manager
- meta reviewer

The meta reviewer blocks unsafe recommendations such as unsupported profitability claims, live trading suggestions, broker connection suggestions, cost-blind suggestions, sample-quality bypass, and market-rule bypass.

## AI-Adjusted Replay Impact Summary

The AI shadow adjustment plan:

- prefers mixed stock+ETF universe
- uses bounded position-size multiplier
- adjusts ETF preference within bounds
- preserves cost-after-fill and sample-validation checks
- rejects forbidden adjustments
- computes fill-rate, zero-trade, capital-usage, cost-drag, net-PnL, turnover, and ETF-weight deltas

## Qlib/RQAlpha Handoff Summary

P40 creates metadata-only handoffs for:

- Qlib next-stage offline AI quant backtest
- RQAlpha later event-driven backtest

Both handoffs keep runtime execution disabled by default and include sample identifier, provider name, field mapping, calendar assumptions, cost model assumptions, benchmark candidate, alpha feature candidates, execution assumptions, and known limitations.

## Capital Path Suitability Summary

P40 reuses the P39 mixed ETF replay and keeps capital-stage suitability visible for:

- `1000` CNY stage
- `10000` CNY stage
- `100000` CNY stage

## Safety Barrier Status

- Pre-P34 estimated barrier: `185.0%`
- P34 through P40 active barrier: `140.0%`
- Target: `<= 140%`
- P40 does not raise the safety barrier. It adds AI shadow and open-source boundaries to the replay chain under the pruned gate set.

## Validation Commands and Results

`.venv/bin/python -m compileall src`

Result: passed.

`.venv/bin/python -m pytest tests/ai_open_source_provider_small_sample_mixed_etf_replay`

Result: passed.

```text
platform darwin -- Python 3.12.10, pytest-9.1.1
collected 28 items
28 passed in 0.05s
```

`.venv/bin/python -m pytest`

Result: passed.

```text
platform darwin -- Python 3.12.10, pytest-9.1.1
collected 778 items
778 passed in 0.39s
```

## P40 Summary

P40 validates approved local provider-export style data, models AkShare/BaoStock/manual export boundaries, generates deterministic AI shadow recommendations, meta-reviews unsafe recommendations, applies bounded replay adjustments, compares adjusted replay metrics, and emits Qlib/RQAlpha handoff metadata.

## Risks

- P40 uses deterministic local exports only; it does not approve live trading.
- AI shadow outputs are deterministic local stand-ins, not real model judgments.
- Qlib/RQAlpha handoffs are metadata-only and do not run those frameworks.
- Provider export quality must improve before any larger paper loop uses real samples.

## Recommended Next Step

Use P40 handoffs to run the next controlled offline Qlib-compatible evaluation stage, while improving approved provider-export quality and AI alpha proposal quality.

## Code Evidence Snapshot

- `contracts.py`: defines provider boundary, AI shadow, replay adjustment, adjusted replay, backtest handoff, and report contracts.
- `open_source_provider_bridge.py`: validates approved local exports, explicit schema mappings, coverage, OHLCV fields, approval metadata, and source safety.
- `ai_shadow_agents.py`: generates deterministic structured shadow-agent recommendations and meta-review blocks unsafe recommendations.
- `replay_adjustment.py`: converts AI recommendations into bounded replay adjustments and computes adjusted replay metric deltas.
- `comparison.py`: creates Qlib/RQAlpha handoff metadata and adjusted replay impact summaries.
- `report.py`: builds the P40 report, keeps safety barrier at `<= 140%`, and selects the next improvement target.
- `tests`: cover provider boundaries, approval metadata, schema and OHLCV validation, AI roles, meta-review blocking, bounded adjustments, replay deltas, Qlib/RQAlpha handoffs, safety barrier, deterministic ordering, and forbidden runtime behavior.
