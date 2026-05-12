# Phase 6C-3B Module Kickoff Review

This document records the ChatGPT-approved kickoff review for Phase 6C-3B. Codex is not the project architect and is only implementing the scoped isolated RQAlpha prototype probe.

## Purpose

Run a controlled, isolated, manual-only RQAlpha prototype probe.

## Upstream

- Phase 6A backtest engine evaluation
- Phase 6B prototype isolation plan
- Phase 6C-1 vectorbt prototype
- Phase 6C-1.1 environment isolation
- Phase 6C-2 Backtrader prototype
- Phase 6C-3A RQAlpha preflight

## Downstream

- RQAlpha closure review
- possible backtest engine shortlist review
- future adapter decision

## Scope

Allowed:

- install RQAlpha only inside `.venv-prototypes/rqalpha/`
- run one safe metadata and fake-fixture feasibility probe
- write local artifacts only under `local_artifacts/backtest_prototypes/rqalpha/`
- summarize results in docs

Prohibited:

- no real market data
- no provider/API use
- no production adapter
- no final engine selection
- no broker/live/order path
- no live trading, broker, mod-ctp, mod-vnpy, or execution functionality
- no commercial integration before license review

## Success Criteria

- RQAlpha installation is isolated from the main project environment.
- The probe imports RQAlpha only from the isolated environment.
- Fake-fixture-only feasibility is recorded safely.
- Any data bundle/config/provider blocker is captured without falling back to real data.
- Review packet records installation path, validation, risks, and next step.
