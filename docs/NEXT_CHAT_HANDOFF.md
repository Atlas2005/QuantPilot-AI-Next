# Next Chat Handoff

## Project Goal

QuantPilot-AI 2.0 is an open-source-first, adapter-first, contract-first, A-share-first AI quant integration platform designed to evolve toward a profitable AI quantitative trading platform through evidence-gated research.

## Current Phase

Phase 6C-3B: isolated RQAlpha prototype probe, implemented by Codex and pending ChatGPT closure review.

## Completed Work

Step 0A through Phase 6C-3A are completed.

Phase 6C-3B created:

- `docs/modules/phase_6c_3b_rqalpha_isolated_prototype/MODULE_KICKOFF_REVIEW.md`
- `docs/modules/phase_6c_3b_rqalpha_isolated_prototype/MODULE_CLOSURE_DRAFT.md`
- `tools/manual_backtest_prototypes/rqalpha_local_fixture_probe.py`
- `tools/manual_backtest_prototypes/summarize_rqalpha_probe.py`

RQAlpha was installed and imported only inside `.venv-prototypes/rqalpha/`. The probe did not run a backtest because fake-fixture-only execution was not proven without RQAlpha data bundle/config setup.

## Current Prohibitions

- do not fetch market data
- do not call external APIs
- do not add RQAlpha or other prototype packages to `pyproject.toml`
- do not run prototype packages outside isolated `.venv-prototypes/<tool-name>/` environments
- do not commercialize, vendor, copy, or integrate RQAlpha before license review
- do not implement production backtest adapters
- do not implement strategy, alpha/factor, portfolio, model, broker, live order, or agent workflows
- do not mark anything trading-ready
- do not claim profitability

## Next Recommended Step

ChatGPT should perform Phase 6C-3B closure review.

Do not move to adapter implementation or final engine selection until approved.

## Key Decisions

- Phase 6C-3B tested RQAlpha only.
- RQAlpha is not a project dependency.
- No final backtest engine selection was made.
- No production RQAlpha adapter exists.
- RQAlpha license/commercial risk remains unresolved.
- Codex is not the project architect.

## Role Split

ChatGPT is the architecture lead and strategic reviewer.

Codex creates files, organizes docs, runs safe validation commands, and produces review packets.

ChatGPT, not Codex, performs module closure review.
