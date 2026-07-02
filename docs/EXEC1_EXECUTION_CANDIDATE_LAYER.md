# EXEC1 Execution Candidate Layer

EXEC1 converts RESEARCH1 committee output into deterministic offline execution candidates. It is the bridge from diagnostics into replayable simulated intents: target exposure, position intent, order intent, cost estimate, slippage estimate, and post-cost ranking.

This layer does not connect to accounts, credentials, market data services, order routing, or model APIs. It consumes supplied in-memory research reports, optional current-position weights or notionals, optional last prices, and explicit assumptions.

## Scope

- Package: `src/quantpilot_core/execution_candidate/`
- Public functions:
  - `build_execution_candidate`
  - `build_execution_candidate_report`
- Tool registry entries:
  - `build_execution_candidate`
  - `build_execution_candidate_report`
- Side-effect level: `PURE_IN_MEMORY`

EXEC1 preserves INFO, RESEARCH, vectorbt, and Qlib signal-bridge behavior. It adds an offline candidate construction layer after research diagnostics.

## Contracts

`ExecutionAssumption`

- `capital`
- `lot_size`, default `100`
- `min_notional`
- `max_position_weight`
- `commission_rate`
- `stamp_tax_rate`
- `slippage_bps`
- `allow_fractional_shares`, default `False`

`PositionIntent`

- `symbol`
- `target_weight`
- `current_weight`
- `target_notional`
- `confidence`
- `rationale`
- `limitations`

`OrderIntent`

- `symbol`
- `side`: `BUY`, `SELL`, or `NOOP`
- `quantity`
- `notional`
- `estimated_cost`
- `estimated_slippage`
- `estimated_total_drag`
- `reason`

`ExecutionCandidate`

- `target`
- `composite_score`
- `target_weight`
- `confidence`
- `position_intents`
- `order_intents`
- `estimated_cost`
- `estimated_slippage`
- `estimated_total_drag`
- `cost_after_score`
- `limitations`

`ExecutionCandidateReport`

- `candidates`
- `ranking`
- `assumptions`
- `portfolio_exposure`
- `total_estimated_cost`
- `total_estimated_slippage`
- `limitations`

## Deterministic Sizing

For a positive committee score, target weight increases with score and confidence:

```text
target_weight =
  max_position_weight
  * positive_composite_score
  * confidence
  * risk_conflict_multiplier
```

For weak or negative scores, target weight becomes `0.0`, which can create a simulated sell intent when an existing current position is supplied.

Conflict evidence, bear evidence, and weak confidence reduce sizing and execution score. They do not remove the candidate.

## Order Intent Construction

EXEC1 compares target notional with current notional:

- `BUY` when target notional is above current notional
- `SELL` when target notional is below current notional
- `NOOP` only when the derived quantity rounds to zero, the rounded notional is below `min_notional`, target equals current, or no usable last price is supplied

By default, A-share-like lot rounding is applied:

- `lot_size = 100`
- fractional shares disabled
- quantity is rounded down to the nearest lot

## Cost And Ranking

Estimated cost includes:

- commission on buys and sells
- stamp tax on sells
- slippage from `slippage_bps`

Total drag is:

```text
estimated_total_drag = estimated_cost + estimated_slippage
```

Post-cost score is:

```text
cost_after_score = composite_score - estimated_total_drag / capital
```

Reports rank candidates by `cost_after_score`, then confidence, then symbol for deterministic ties.

## Validation

```bash
PYTHONPATH=.:src .venv/bin/python -m pytest tests/execution_candidate tests/tool_registry tests/research_committee tests/information_agents tests/qlib_signal_integration tests/vectorbt_integration -q
PYTHONPATH=.:src .venv/bin/python -m pytest -q
git diff --check
```
