# Next Chat Handoff

## Project Goal

QuantPilot-AI 2.0 is an open-source-first, adapter-first, contract-first, A-share-first AI quant integration platform designed to evolve toward a profitable AI quantitative trading platform through evidence-gated research.

## Current Phase

Phase 1.1: candidate registry refresh patch, implemented by Codex and pending ChatGPT closure review.

## Completed Work

Step 0A planning package was completed.

Step 0B clean skeleton and minimal CI was completed.

Phase 1 candidate registry was completed.

Phase 2 core contracts was completed and pushed.

Phase 1.1 added:

- terminal/product benchmark schema fields
- professional terminal/product benchmark records
- open-source terminal/dashboard candidate records
- license and commercial-risk documentation
- terminal benchmark tests

## Current Prohibitions

- do not implement trading logic
- do not fetch market data
- do not call external APIs
- do not install or import external frameworks
- do not clone or copy terminal/dashboard projects
- do not create dashboard or terminal implementation
- do not create broker/live/order paths
- do not implement backtesting, model training, or agent orchestration
- do not mark anything trading-ready
- do not claim profitability
- do not make final product or terminal architecture selections

## Next Recommended Step

ChatGPT should perform Phase 1.1 closure review.

After approval: commit/push, then Phase 3 kickoff review.

Do not move to Phase 3 until approved.

## Key Decisions

- Professional terminals are benchmarks, not dependencies.
- Proprietary terminals are reference-only.
- FinceptTerminal requires license review before any cloning, copying, integration, commercial use, or derivative work.
- Terminal-like projects are not automatically safe to integrate.
- Future module kickoff reviews must include both open-source search and professional benchmark scan.

## Role Split

ChatGPT is the architecture lead and strategic reviewer.

Codex creates files, organizes docs, runs safe validation commands, and produces review packets.

ChatGPT, not Codex, performs module closure review.

