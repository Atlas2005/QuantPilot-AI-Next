# P38 Mixed Stock ETF Daily Paper Evaluation

P38 compares stock-only daily paper evaluation against mixed stock plus exchange-listed ETF daily paper evaluation.

This phase is not another generic safety or preflight wall. It measures whether ETF inclusion improves the trading path created by P34 through P37: order intents, simulated fills, zero-trade diagnosis, capital usage, cost drag, and net PnL after cost.

R3F retires P38 from current default replay/fill/metrics usage. This package is legacy/reference compatibility only and should not be treated as the current default provider, signal replay, fill, or portfolio metrics path.

## Objective

P38 answers:

- did mixed stock+ETF outperform stock-only on fillability?
- did mixed stock+ETF reduce zero-trade days?
- did mixed stock+ETF improve capital usage?
- did mixed stock+ETF improve net PnL after cost?
- did ETF inclusion create excessive cost drag?
- is the safety barrier still at or below `140%`?
- should the mixed universe become the next-stage paper loop default?

## Deterministic Scenarios

P38 creates two local deterministic scenarios:

- `stock_only`: A-share stock candidates only
- `mixed_stock_etf`: A-share stock plus exchange-listed ETF candidates

Both scenarios use:

- the same initial capital
- the same evaluation window
- deterministic signal candidates
- deterministic sizing assumptions
- local paper simulation only

No real data is fetched. No broker is connected. No orders are placed.

## Comparison Metrics

P38 reuses the P36 daily paper trading loop and compares:

- trading day count
- raw signal count
- order intent count
- simulated fill count
- fill rate
- zero-trade day count
- zero-trade reason distribution
- cost / tax / slippage total
- gross PnL estimate
- net PnL after cost
- average and max capital usage
- turnover estimate
- drawdown estimate
- suspected overblocking days

## ETF Impact Summary

The ETF impact summary reports whether the mixed stock+ETF scenario improves:

- fill rate
- zero-trade day count
- capital usage
- diversification proxy
- cost drag
- net PnL after cost
- small-capital suitability

## Capital Path Suitability

P38 evaluates whether ETF inclusion helps at:

- `1000` CNY stage
- `10000` CNY stage
- `100000` CNY stage

The report states whether ETF inclusion helps, whether stock-only remains viable, whether mixed stock+ETF is viable, and whether mixed universe should be the next default at each stage.

## Safety Boundary

P38 does not:

- connect to brokers
- read real accounts
- place real orders
- import broker SDKs
- call DeepSeek
- call OpenAI
- make network calls in default tests
- install packages
- modify project dependencies
- run optional external runtime commands in default tests
- require optional external runtime frameworks for default tests
- add generic preflight-only gates

## Value Orientation

P38 is profit-path oriented. It tests whether adding ETFs improves practical daily paper tradability instead of assuming that ETF support is valuable by design.

The mixed stock+ETF path should advance only when it improves fillability, capital use, cost drag, or net PnL after cost while keeping hard safety boundaries intact.

## Recommended Next Step

Use the P38 comparison report only for legacy/reference comparison or migration audit.

Current replacement-first direction: signal replay and portfolio metrics should prefer vectorbt where feasible. A-share event-driven trading and backtest semantics should move toward RQAlpha, and AI/factor research workflow should target Qlib. Keep only A-share/account/capital glue in QuantPilot code.
