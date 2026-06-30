# P34 Gate Pruning And Tradability Fill Loop

P34 shifts QuantPilot-AI-Next from accumulating preflight walls toward controlled automated trading readiness.

The goal is not to weaken true safety. The goal is to keep hard blocks only where a single trade can create leakage, invalid A-share behavior, account/capital violation, credential exposure, or an unapproved real-broker path. Everything else should become warning, diagnostic, frozen, or removed so the system can measure whether signals are actually tradable.

## Gate Pruning

P34 keeps hard blocks for:

- PIT / no future leakage
- A-share 100-share lot
- T+1 sellable quantity
- price limit
- suspension
- insufficient cash
- insufficient position
- credential leakage
- real broker order path disabled before approved small-capital stage

P34 downgrades:

- small-capital readiness checks that are too strict for a single simulated trade
- multi-agent orchestration completeness
- non-critical metric absence
- release hardening checks unrelated to one trade
- generic manual approval language not tied to capital risk

P34 freezes:

- broker SDK research expansion
- new generic safety/preflight expansion

The baseline audit starts around `185%` safety barrier and reduces the active barrier to `140%` or less while preserving hard trade-risk gates.

## Tradability Loop

P34 converts `TradeSignalCandidate` records into `OrderIntent` records, then applies deterministic A-share tradability rules:

- 100-share lot
- T+1 sellable quantity
- price limit
- suspension
- available cash
- available position
- commission
- stamp duty
- slippage

Fill simulation is local and deterministic. It does not connect to brokers, read accounts, place orders, call LLMs, or fetch market data.

## Report Metrics

`FillSimulationReport` records:

- raw signal count
- order intent count
- hard rejected count
- soft warning count
- fillable order count
- simulated fill count
- zero-trade reason distribution
- fee / slippage / tax
- capital used ratio
- deterministic net PnL after cost estimate
- suspected overblocking
- next action recommendation

## Value Orientation

P34 is explicitly profit-path oriented. It removes or downgrades overblocking that prevents tradability measurement, while retaining hard controls that protect against invalid A-share orders, capital/account errors, and forbidden real-broker execution.

This is the first step after P33 that asks: can the project generate executable order intents and simulated fills?

## Safety Boundary

P34 does not:

- connect to brokers
- read real accounts
- place real orders
- import broker SDKs
- call DeepSeek
- call OpenAI
- call the network in default tests
- install packages
- create real-money execution paths

## Recommended Next Step

Use P34 fillability diagnostics to decide whether the next phase should improve signal quality, tune account sizing, or repair the top hard rejection reason before any broker-facing work resumes.
