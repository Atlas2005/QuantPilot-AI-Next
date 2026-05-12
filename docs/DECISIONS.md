# Decisions

## Step 0A Decisions

- QuantPilot-AI-Next is the official next-generation project for QuantPilot-AI 2.0.
- The old v2 project is a legacy research archive only.
- Step 0A is planning package only.
- Codex is not the project architect.
- ChatGPT owns architecture review and strategic decisions.
- Codex owns file creation, documentation organization, validation commands, and review packet production.
- Open-source candidates are recorded but not selected.
- Agent orchestration is late-stage.
- No source implementation is allowed in Step 0A.
- No dependency installation is allowed in Step 0A.
- No market data, API, broker, backtest, model, live trading, or order path is allowed in Step 0A.

## Step 0B Decisions

- ChatGPT approved the Step 0B kickoff before Codex implementation.
- Step 0B may create a minimal `src` layout Python package.
- Runtime dependencies remain empty.
- `pytest` is allowed as a dev/test dependency only.
- No quant, data-source, broker, ML, or agent framework integration is allowed in Step 0B.
- Safety flags default to false.
- The package remains not trading-ready.

## Phase 1 Decisions

- ChatGPT approved the Phase 1 kickoff before Codex implementation.
- Phase 1 creates candidate registry foundation only.
- Phase 1 makes no final technical selection.
- Phase 1 adds no dependency installation.
- Every candidate remains registry-only until ChatGPT-led module review.
- External frameworks must later enter through adapters and contract tests.
- Candidate metadata is static and stored in `data/open_source_candidates/candidates.json`.
- Candidate validation uses Python standard library only.

## Phase 2 Decisions

- ChatGPT approved the Phase 2 kickoff before Codex implementation.
- Phase 2 creates contracts only.
- Phase 2 creates no real adapters.
- Phase 2 makes no final engine selection.
- Phase 2 adds no external imports.
- Agent skill contract exists only as a late-stage boundary, not an implementation.
- Market rule contract exists only as a boundary before the actual market rule engine phase.
- Core contracts expose descriptive metadata and scope warnings only.
