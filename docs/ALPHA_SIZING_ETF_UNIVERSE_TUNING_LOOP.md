# P37 Alpha, Sizing, And ETF Universe Tuning Loop

P37 expands QuantPilot-AI-Next from stock-only tradability tuning into an A-share stock plus exchange-listed ETF universe.

The goal is practical trading readiness. P37 does not add another generic preflight wall. It tunes alpha quality, sizing, and candidate universe selection toward order intents and simulated fills while keeping the active safety barrier at `140%` or below.

## Objective

P37 answers:

- whether the tradable universe includes both stocks and ETFs
- whether ETFs are handled with explicit ETF rules instead of being treated as stocks
- whether ETF categories are present and valid
- whether ETFs improve small-capital diversification and tradability
- whether sizing recommendations reduce zero-trade risk
- whether cost-after-fill remains acceptable
- what should improve next: alpha quality, ETF universe, sizing, cost model, or daily loop realism

## ETF Rule Profiles

ETF handling is explicit:

- ETF minimum trade unit is `100` units
- ETF minimum tick is `0.001`
- equity ETF default settlement is `T+1`
- bond, gold, cross-border, and money-market ETF categories may use `T+0` only when explicitly declared
- ETF fee model is separate from the stock stamp-duty model
- ETF category is mandatory
- ETF candidates cannot silently fall back to `STOCK`

Stocks remain valid candidates. P37 does not hard-block stocks just because ETF candidates exist.

## Universe Logic

The universe selector accepts valid stock candidates and valid ETF candidates, rejects unknown instrument types, rejects ETFs with missing categories, reports stock and ETF counts separately, and ranks valid ETFs as small-capital diversification candidates.

## Sizing Logic

P37 sizing recommendations estimate:

- capital usage
- cost drag
- tradability score
- zero-trade risk reduction

Sizing rounds to valid trade units so odd-lot zero-trade outcomes are less likely. ETF candidates can improve diversification and capital use because they often provide broad exposure with lower per-unit price and no stock stamp-duty model.

## Tuning Logic

P37 produces deterministic tuning decisions with:

- alpha quality score
- sizing score
- tradability score
- cost-after-fill score
- recommended action

Recommended actions include:

- `improve_alpha`
- `reduce_cost_drag`
- `increase_position_size`
- `reduce_position_size`
- `prefer_etf_for_small_capital`
- `keep_candidate`
- `reject_candidate`

## Safety Boundary

P37 does not:

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
- create a live trading route

## Value Orientation

P37 moves the system closer to controlled automated A-share and ETF trading by improving candidate quality, valid ETF-specific rules, practical sizing, and explicit cost-aware tuning.

## Recommended Next Step

Use P37 output as a pure alpha, sizing, and universe tuning layer. Do not use P36/P38 as current default replay/fill/metrics providers.

For provider mixed ETF replay, prefer the R3D `provider_vectorbt_replay` path. The old P36/P39 provider replay path is legacy/reference only; generic replay and portfolio metrics should move to vectorbt, RQAlpha, or Qlib where suitable.

Signal replay and portfolio metrics should prefer vectorbt where feasible. A-share event-driven trading and backtest semantics should move toward RQAlpha, and AI/factor research workflow should target Qlib.
