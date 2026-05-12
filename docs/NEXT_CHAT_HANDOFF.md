# Next Chat Handoff

## Project Goal

QuantPilot-AI 2.0 is an open-source-first, adapter-first, contract-first, A-share-first AI quant integration platform designed to evolve toward a profitable AI quantitative trading platform through evidence-gated research.

## Current Phase

Phase 5: A-share market rule foundation, implemented by Codex and pending ChatGPT closure review.

## Completed Work

Step 0A through Phase 4B are completed.

Phase 5 created:

- `src/quantpilot_core/market_rules/types.py`
- `src/quantpilot_core/market_rules/profile.py`
- `src/quantpilot_core/market_rules/a_share.py`
- `data/market_rule_profiles/a_share_basic_v0_1.json`
- market rule profile tests
- A-share rule behavior tests
- `docs/A_SHARE_MARKET_RULES.md`
- Phase 5 module kickoff and closure draft docs

## Current Prohibitions

- do not fetch market data
- do not call external APIs
- do not install packages
- do not import external frameworks
- do not implement broker, live trading, or real order submission paths
- do not run backtests
- do not implement strategy, alpha/factor, portfolio, model, or agent workflows
- do not mark anything trading-ready
- do not claim profitability

## Next Recommended Step

ChatGPT should perform Phase 5 closure review.

Do not move to Phase 6 until approved.

## Key Decisions

- Market rule profiles are configurable and source-versioned.
- Current profile values are provisional and manual-review-required.
- Official SSE/SZSE/BSE rules must be refreshed before real use.
- Fee, slippage, corporate action, and special-case handling remains deferred.
- Codex is not the project architect.

## Role Split

ChatGPT is the architecture lead and strategic reviewer.

Codex creates files, organizes docs, runs safe validation commands, and produces review packets.

ChatGPT, not Codex, performs module closure review.

