# P39 Real Provider Mixed ETF Paper Replay

P39 moves QuantPilot-AI-Next from deterministic fixture-only mixed stock/ETF comparison toward provider-gated local sample replay.

This phase still uses offline deterministic tests. It does not fetch live provider data, connect to brokers, read accounts, place orders, call LLM runtimes, install packages, or require optional runtime frameworks.

## Objective

P39 answers:

- did the provider-like local sample include both stocks and ETFs?
- did mixed stock+ETF replay produce simulated fills?
- was fill rate positive?
- were zero-trade days reduced or explained?
- was net PnL after cost positive, zero, or negative?
- did data quality block replay?
- did ETF inclusion remain useful under provider-like local samples?
- is the safety barrier still at or below `140%`?
- what should improve next: provider sample quality, alpha quality, ETF selection, sizing, cost model realism, or daily loop realism?

## Provider-Gated Local Sample Boundary

P39 consumes local sample records shaped like provider-gated daily bars. The bridge validates:

- source URI is local-only
- stock and ETF instrument types are present
- ETF category is explicit
- required OHLCV-like fields are present
- dates are sorted
- duplicate symbol/date rows are rejected
- rows do not exceed the evaluation window
- close and volume are present and positive
- mixed replay includes both stock and ETF candidates

Default tests use only deterministic in-repo fixtures constructed in test code. No real provider API is called.

## Replay Logic

Accepted samples are converted into a mixed stock/ETF daily paper replay using the existing P36 daily paper loop concepts.

P39 computes:

- trading day count
- stock and ETF candidate counts
- order intent count
- simulated fill count
- fill rate
- zero-trade day count and reasons
- cost / tax / slippage
- average and max capital usage
- net PnL after cost
- provider sample quality flags
- ETF impact notes
- small-capital suitability notes

## Comparison With P38

P39 compares provider-like replay against the P38 deterministic mixed stock/ETF baseline and reports whether local provider-like samples preserve fillability, expose data-quality blockers, change zero-trade behavior, change cost drag, change capital usage, or change net PnL after cost.

## Capital Path Suitability

P39 reports suitability for:

- `1000` CNY stage
- `10000` CNY stage
- `100000` CNY stage

Each stage states whether ETF inclusion helps, whether stock-only remains viable, whether mixed stock+ETF is viable, and whether mixed stock+ETF should remain the next paper-loop default.

## Safety Boundary

P39 does not:

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

## Value Orientation

P39 is profit-path oriented. It checks whether the mixed stock/ETF paper loop remains useful when driven by provider-like local samples rather than pure deterministic fixtures.

The point is to advance toward controlled automated A-share/ETF paper evaluation while keeping hard safety boundaries intact.

## Recommended Next Step

Use P39 replay results to improve provider sample quality and then feed approved provider-gated stock/ETF samples into the next daily paper loop with alpha, sizing, and cost-model tuning.
