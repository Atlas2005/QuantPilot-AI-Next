# P36 Daily Paper Trading Loop With Tradability Metrics

P36 moves QuantPilot-AI-Next from single-window fillability checks into a deterministic multi-day paper trading loop.

This is still offline and local. It does not connect to a broker, read a real account, place orders, call LLM runtimes, fetch market data, install packages, or require optional runtime frameworks.

## Objective

P36 answers whether the project can run a small daily paper-trading cycle after P34 gate pruning and P35 offline tradability fixtures:

- consume a deterministic multi-day fixture
- accept daily signal candidates
- convert candidates into order intents
- simulate A-share tradability and fills
- update local paper cash and positions
- aggregate tradability, cost, turnover, drawdown, and zero-trade diagnostics
- recommend the next adjustment target

This is not another generic safety wall. It is a profit-path measurement loop that keeps the active safety barrier at `140%` or below.

## Daily Loop Boundary

The daily loop reuses the existing P34 tradability and fill simulation. It applies the same A-share controls:

- 100-share lot
- T+1 sellable quantity
- price limit
- suspension
- available cash
- available position
- commission
- stamp duty
- slippage

After each day, P36 updates local paper cash and positions deterministically. Buy fills increase position and reduce cash by gross notional plus costs. Sell fills reduce position and increase cash by gross notional net of costs.

## Metrics

P36 reports:

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
- safety barrier percent

The report also answers:

- whether at least one day traded
- whether multiple days produced order intents
- whether fill rate was positive
- whether net PnL was positive, zero, or negative
- whether zero-trade days occurred
- which exact causes explain zero-trade days
- whether the next improvement should target alpha quality, sizing, tradability, cost model, or data quality

## Safety Boundary

P36 does not:

- connect to brokers
- read real accounts
- place real orders
- import broker SDKs
- call DeepSeek
- call OpenAI
- make network calls in default tests
- install packages
- modify project dependencies
- run optional external runtime frameworks
- add a live trading route

## Value Orientation

P36 keeps the project oriented toward controlled automated A-share trading by measuring whether the system can produce order intents, simulated fills, cost-aware outcomes, and daily improvement signals.

The key shift is practical: instead of adding more broad gates, P36 checks whether the reduced gate set allows a tradable paper loop while preserving hard A-share, capital, and broker-safety boundaries.

## Recommended Next Step

Use P36 output to decide whether the next phase should improve alpha quality, trade sizing, tradability constraints, cost model realism, or deterministic data quality before any broker-facing work is considered.
