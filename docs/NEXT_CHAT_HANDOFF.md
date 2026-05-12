# Next Chat Handoff

## Project Goal

QuantPilot-AI 2.0 is an open-source-first, adapter-first, contract-first, A-share-first AI quant integration platform designed to evolve toward a profitable AI quantitative trading platform through evidence-gated research.

## Current Phase

Phase 0A: planning package only.

## Completed Work

Created the Step 0A planning document set:

- README
- project positioning
- strategic handoff
- open-source-first policy
- module selection policy
- language architecture
- dependency update policy
- legacy migration policy
- open-source candidate universe
- roadmap
- success metrics
- first 30 days plan
- workflow automation policy
- module governance policy
- module review template
- current project state
- decisions
- next step decision
- review packet

## Current Prohibitions

- do not create `src/` code
- do not implement trading logic
- do not fetch market data
- do not install packages
- do not import external frameworks
- do not run backtests
- do not train models
- do not connect brokers
- do not create broker/live trading/order paths
- do not create live trading flags
- do not mark anything trading-ready
- do not claim profitability
- do not create automatic dependency merge logic
- do not blindly integrate open-source frameworks

## Next Recommended Step

ChatGPT should perform a Step 0A closure review and decide whether Phase 0B should begin.

Phase 0B should create a clean project skeleton and minimal CI only after ChatGPT approval.

## Key Decisions

- Old v2 is legacy research archive only.
- Open-source alternatives must be reviewed before major custom modules.
- External frameworks must later enter through adapters and contract tests.
- Core contracts must be defined before implementation.
- A-share market realism is the core project differentiator.
- Agent orchestration is late-stage, not early-stage.

## Role Split

ChatGPT is the architecture lead and strategic reviewer.

Codex creates files, organizes docs, runs safe validation commands, and produces review packets.

## Review Process

Every major module requires:

1. ChatGPT-led kickoff review.
2. Codex implementation within approved scope.
3. Codex validation summary.
4. ChatGPT-led closure review.
5. ChatGPT-led next module readiness review.

## What Not To Do

Do not install candidate frameworks, fetch data, create source code, add trading logic, add broker paths, create agent orchestration, or make trading-readiness/profitability claims.

