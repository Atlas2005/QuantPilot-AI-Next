# Next Chat Handoff

## Project Goal

QuantPilot-AI 2.0 is an open-source-first, adapter-first, contract-first, A-share-first AI quant integration platform designed to evolve toward a profitable AI quantitative trading platform through evidence-gated research.

## Current Phase

Phase 6C-1.1: prototype environment isolation policy, implemented by Codex and pending ChatGPT closure review.

## Completed Work

Step 0A through Phase 6C-1 are completed.

Phase 6C-1.1 created:

- `docs/PROTOTYPE_ENVIRONMENT_ISOLATION_POLICY.md`
- `tools/prototype_envs/README.md`
- `tools/prototype_envs/create_prototype_env.ps1`
- `tools/prototype_envs/create_prototype_env.sh`
- `tests/policy/test_prototype_environment_policy.py`
- Phase 6C-1.1 module kickoff and closure draft docs

The patch requires future external-framework prototypes to use isolated `.venv-prototypes/<tool-name>/` environments instead of the main project Python environment.

## Current Prohibitions

- do not fetch market data
- do not call external APIs
- do not install or uninstall packages without explicit approval
- do not add prototype packages to `pyproject.toml`
- do not run Backtrader/RQAlpha/Qlib/deeper vectorbt prototypes in the main project environment
- do not implement production backtest adapters
- do not implement strategy, alpha/factor, portfolio, model, broker, live order, or agent workflows
- do not mark anything trading-ready
- do not claim profitability

## Next Recommended Step

ChatGPT should perform Phase 6C-1.1 closure review.

Do not start Backtrader/RQAlpha/Qlib prototype work until approved.

## Key Decisions

- Prototype environments must live under `.venv-prototypes/<tool-name>/`.
- Prototype outputs remain under `local_artifacts/`.
- Prototype dependencies remain out of project dependency files until a later approved adapter phase.
- Codex is not the project architect.

## Role Split

ChatGPT is the architecture lead and strategic reviewer.

Codex creates files, organizes docs, runs safe validation commands, and produces review packets.

ChatGPT, not Codex, performs module closure review.
