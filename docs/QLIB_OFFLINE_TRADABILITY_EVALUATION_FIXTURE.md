# P35 Qlib Offline Tradability Evaluation Fixture

P35 moves QuantPilot-AI-Next from gate pruning into offline tradability evaluation.

It creates deterministic A-share-like fixture data, deterministic signals, expected order intents, simulated fills, cost-after-fill metrics, zero-trade diagnosis, and Qlib-compatible metadata without importing or running Qlib.

## Purpose

P34 reduced the estimated safety barrier from `185%` to `140%` and proved the project can simulate fills under A-share constraints. P35 packages that fillability into an offline evaluation fixture that can later support a controlled Qlib runtime spike.

P35 answers:

- Did the fixture produce signals?
- Did signals become order intents?
- Did order intents become simulated fills?
- Was fill rate above zero?
- Was net PnL after cost positive, zero, or negative?
- If zero fills occurred, what exact reasons explain them?
- Is the safety barrier still overblocking the evaluation?
- What should improve next?

## Fixture Contents

The deterministic fixture includes:

- A-share-like daily bars for `000001.SZ` and `600000.SH`
- deterministic buy and sell signals
- expected order intent count
- expected simulated fill count
- expected fee / slippage / tax value
- expected zero-trade reason distribution

The fixture is local-only and does not fetch data or write production assets.

## Evaluation Logic

P35 reuses the P34 tradability and fill simulation loop.

It computes:

- raw signal count
- order intent count
- fillable order count
- simulated fill count
- fill rate
- zero-trade reason distribution
- estimated fee / slippage / tax
- net PnL after cost
- capital used ratio
- deterministic max drawdown estimate
- deterministic turnover estimate
- Qlib compatibility notes

## Qlib-Compatible Metadata

P35 represents the fixture through metadata compatible with a future offline Qlib workflow:

- local-only dataset URI
- explicit calendar
- explicit benchmark
- explicit factor metric handoff
- runtime execution disabled

Default tests do not import Qlib, do not run qrun, and do not require Qlib as a dependency.

## Safety Barrier

P35 must not raise the safety barrier above the P34 target. The fixture report keeps the barrier at `140%` or below while measuring fillability.

## Safety Boundary

P35 does not:

- connect to brokers
- read real accounts
- place real orders
- import broker SDKs
- call DeepSeek
- call OpenAI
- make network calls in default tests
- install packages
- modify project dependencies
- run Qlib or qrun
- require Qlib for default tests

## Recommended Next Step

Use P35 fixture results to decide whether the next improvement should target alpha quality, sizing, liquidity/tradability, cost model accuracy, or data fixture quality before any optional Qlib runtime spike proceeds.
