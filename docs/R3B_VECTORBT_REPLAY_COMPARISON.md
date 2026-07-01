# R3B Vectorbt Replay Comparison

## Summary

R3A added the optional vectorbt replay adapter.

R3B connects existing QuantPilot signal fixtures to vectorbt as a comparison path. It converts dated `TradeSignalCandidate` records into vectorbt-compatible price, entry, and exit inputs.

## Existing Chain Remains

The old paper/fill/replay chain remains the baseline in this patch. R3B does not delete or replace it.

The comparison path lets QuantPilot evaluate mature framework replay output beside the existing chain before any replacement decision.

## Why This Matters

Profitability and executable trading progress require mature open-source replay and analysis. This patch avoids writing another self-built backtest engine and instead prepares the bridge to vectorbt.

## Future Path

Next steps:

- Compare vectorbt replay metrics with the old paper/fill/replay chain.
- Expand framework-backed replay coverage.
- Gradually replace self-built replay and fill modules with vectorbt, RQAlpha, and Qlib-backed paths where practical.
- Keep A-share-specific constraints and account/capital glue in QuantPilot-owned code.

RQAlpha and Qlib remain next-stage integrations.

## Safety Boundary

Missing vectorbt is not a blocker. The comparison returns `framework_missing` when the optional framework is unavailable.

Safety remains fatal-only. Missing optional framework availability should not stop controlled paper replay or trading progress.
