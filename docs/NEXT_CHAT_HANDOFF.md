# Next Chat Handoff

## Project Goal

QuantPilot-AI 2.0 is an open-source-first, adapter-first, contract-first, A-share-first AI quant integration platform designed to evolve toward a profitable AI quantitative trading platform through evidence-gated research.

## Current Phase

Phase 0B: clean skeleton and minimal CI, completed by Codex and pending ChatGPT closure review.

## Completed Work

Step 0A planning package was completed and pushed.

Step 0B created:

- `pyproject.toml`
- `.gitignore`
- `.github/workflows/ci.yml`
- `src/quantpilot_core/__init__.py`
- `src/quantpilot_core/contracts/__init__.py`
- `src/quantpilot_core/contracts/base.py`
- `src/quantpilot_core/registry/__init__.py`
- `src/quantpilot_core/registry/base.py`
- `src/quantpilot_core/safety/__init__.py`
- `src/quantpilot_core/safety/flags.py`
- `src/quantpilot_core/config/__init__.py`
- `src/quantpilot_core/config/project.py`
- `tests/__init__.py`
- `tests/smoke/test_imports.py`
- `tests/smoke/test_safety_flags.py`
- `tests/contracts/test_contract_skeleton.py`
- `tests/smoke/test_no_forbidden_scope.py`
- `docs/modules/phase_0b_skeleton/MODULE_KICKOFF_REVIEW.md`
- `docs/modules/phase_0b_skeleton/MODULE_CLOSURE_DRAFT.md`

## Current Prohibitions

- do not implement trading logic
- do not fetch market data
- do not call external APIs
- do not install packages except project dev validation dependency pytest if needed
- do not import quant, data-source, broker, ML, or agent frameworks
- do not run backtests
- do not train models
- do not connect brokers
- do not create broker/live trading/order paths
- do not mark anything trading-ready
- do not claim profitability
- do not create automatic dependency merge logic
- do not blindly integrate open-source frameworks

## Next Recommended Step

ChatGPT should perform Step 0B closure review.

After review, ChatGPT may approve revisions or approve moving to Phase 1: open-source candidate registry.

## Key Decisions

- Old v2 is legacy research archive only.
- Open-source alternatives must be reviewed before major custom modules.
- External frameworks must later enter through adapters and contract tests.
- Core contracts must be defined before implementation.
- A-share market realism is the core project differentiator.
- Agent orchestration is late-stage, not early-stage.
- Step 0B runtime dependencies remain empty.
- `pytest` is dev/test only.
- All safety flags default false.

## Role Split

ChatGPT is the architecture lead and strategic reviewer.

Codex creates files, organizes docs, runs safe validation commands, and produces review packets.

ChatGPT, not Codex, performs module closure review.

## Review Process

Every major module requires:

1. ChatGPT-led kickoff review.
2. Codex implementation within approved scope.
3. Codex validation summary.
4. ChatGPT-led closure review.
5. ChatGPT-led next module readiness review.

## What Not To Do

Do not install candidate frameworks, fetch data, add trading logic, add broker paths, create backtest/model/agent implementations, or make trading-readiness/profitability claims.

