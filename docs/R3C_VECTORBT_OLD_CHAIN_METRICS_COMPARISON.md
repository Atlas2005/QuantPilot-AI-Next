# R3C Vectorbt Old-Chain Metrics Comparison

## Objective

R3C adds an advisory metrics comparison between QuantPilot's existing paper/fill/replay chain and the optional vectorbt replay comparison path introduced in R3A/R3B.

This patch does not delete, replace, or block the old replay chain. It creates a small bridge for comparing already-computed old-chain metrics against vectorbt replay outputs so replacement decisions can be evidence-based.

R3A added the optional vectorbt replay adapter. R3B connected QuantPilot signal fixtures to vectorbt replay input. R3C compares vectorbt metrics with old paper/fill/replay metrics.

## Why This Exists

QuantPilot is moving from self-built replay components toward mature open-source engines where practical. vectorbt is the first mature replay candidate because it is a widely used pandas/NumPy-based framework for fast portfolio analysis and signal replay.

The existing chain still provides project-specific A-share tradability and paper-ledger behavior. R3C compares metrics from both paths before any replacement is attempted.

## Compared Metrics

R3C can map old-chain metrics from:

- daily paper tradability metrics
- mixed stock/ETF scenario evaluation results
- real-provider mixed ETF paper replay results

It compares those against vectorbt comparison outputs for:

- simulated fill count versus vectorbt trade count
- old-chain turnover estimate versus vectorbt turnover proxy
- old-chain drawdown estimate versus vectorbt max drawdown

Old-chain net PnL after cost and vectorbt total return are reported but not treated as directly interchangeable.

## Advisory Only

R3C is not an execution gate. It does not reject trades, block paper replay, or require vectorbt to be installed.

If vectorbt is missing, the comparison reports `vectorbt_framework_missing`. That is useful setup information, not a project-level blocker.

If vectorbt input is invalid, the comparison reports `vectorbt_invalid_input` while leaving the old chain available.

## Replacement Readiness Signals

The comparison can highlight:

- both paths traded and are ready for side-by-side trials
- old chain produced zero trades while vectorbt traded, which may indicate overblocking
- vectorbt produced zero trades while old chain traded, which may indicate signal conversion or framework assumption differences
- both paths produced no trades, which points back to signal quality rather than framework replacement

These are advisory statuses for engineering decisions, not hard safety gates.

## Next Step

Run repeated side-by-side samples using the same signal fixtures and provider-derived offline samples. If vectorbt consistently matches or improves useful replay evidence, future cleanup can gradually replace self-built replay/fill components with mature framework-backed paths while preserving fatal A-share operational checks.

Keep A-share, account, and capital glue in QuantPilot code where it is project-specific. Retire only the generic replay mechanics once mature framework-backed paths have enough side-by-side evidence.
