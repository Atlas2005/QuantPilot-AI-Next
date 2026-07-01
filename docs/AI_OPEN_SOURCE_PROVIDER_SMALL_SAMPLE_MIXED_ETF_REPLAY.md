# P40 AI Open-Source Provider Small Sample Mixed ETF Replay

P40 brings AI shadow decisions and open-source provider export boundaries into the mixed stock/ETF paper replay chain.

This is not another pure internal replay or generic safety wall. P40 models approved local exports from mature open-source provider candidates, runs deterministic AI shadow-agent recommendations, applies bounded replay adjustments, and emits Qlib/RQAlpha handoff metadata for later offline evaluation.

## Objective

P40 answers:

- did the stage use approved local provider-export style data?
- which provider boundary was modeled: AkShare, BaoStock, or manual approved export?
- did AI shadow agents produce structured recommendations?
- did meta-review block unsupported or unsafe recommendations?
- did AI-shadow-adjusted replay improve paper metrics?
- did mixed stock+ETF remain useful?
- did the stage create Qlib/RQAlpha handoff metadata?
- is the safety barrier still at or below `140%`?
- what should improve next: real provider export quality, AI alpha proposal quality, ETF selection, sizing, cost model realism, Qlib backtest, or RQAlpha backtest?

## Open-Source Provider Boundaries

P40 models approved local exports from:

- AkShare
- BaoStock
- manual approved export

Default tests do not import AkShare or BaoStock, do not fetch data, and do not write production data assets.

The bridge validates:

- provider name is explicit
- source type is local or deterministic fixture
- remote sources are rejected
- approval metadata is present
- `approved_by`, `approval_reason`, and `export_timestamp` are present
- provider schema mapping is explicit
- stock and ETF rows are both present
- ETF category is explicit
- OHLCV-like fields are present
- symbol/date rows are unique
- dates are normalized deterministically when needed
- rows do not exceed the evaluation window
- close and volume are present

## AI Shadow Agents

P40 adds deterministic shadow-agent output shaped like future DeepSeek structured output. The required roles are:

- market data quality
- alpha research
- ETF selection
- sizing/capital
- cost/execution
- portfolio manager
- meta reviewer

The meta reviewer blocks or downgrades recommendations that make unsupported profitability claims, suggest live trading, ignore cost-after-fill, ignore sample quality defects, suggest broker connection, or bypass A-share/ETF rules.

No DeepSeek or OpenAI runtime is called in default tests.

## Replay Adjustment

AI shadow recommendations are converted into a bounded replay adjustment plan:

- prefer mixed stock+ETF universe
- increase or decrease ETF preference
- adjust position size multiplier within bounds
- reduce turnover when cost drag is high
- require alpha improvement when net PnL after cost is weak
- require provider sample improvement when data quality is weak

Forbidden adjustments are rejected:

- live trade
- broker connect
- account read
- credential handling
- bypass market rules
- ignore cost/tax/slippage
- bypass sample validation
- claim real profitability

## Open-Source Backtest Handoff

P40 creates metadata handoffs for:

- Qlib next-stage offline AI quant backtest
- RQAlpha later event-driven backtest

The handoffs include local sample identifier, provider name, instrument coverage, stock count, ETF count, field mapping, calendar assumptions, cost model assumptions, benchmark candidate, alpha feature candidates, execution assumptions, and known limitations.

P40 does not run Qlib or RQAlpha by default and does not add dependencies.

## Safety Boundary

P40 does not:

- connect to brokers
- read real accounts
- place real orders
- import broker SDKs
- call DeepSeek
- call OpenAI
- make network calls in default tests
- fetch live or remote provider data in default tests
- install packages
- modify project dependencies
- run optional external runtime commands in default tests
- require optional external runtime frameworks for default tests
- add generic preflight-only gates

## Recommended Next Step

Use P40 output to improve approved provider-export quality and AI alpha proposal quality, then run Qlib-compatible offline backtest metadata through the next controlled offline evaluation stage.
