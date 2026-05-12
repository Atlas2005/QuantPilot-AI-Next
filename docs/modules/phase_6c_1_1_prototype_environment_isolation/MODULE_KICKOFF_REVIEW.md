# Phase 6C-1.1 Module Kickoff Review

This document records the ChatGPT-approved kickoff review for Phase 6C-1.1. Codex is not the project architect and is only implementing the scoped policy and guardrail patch.

## Purpose

Prevent future manual prototype packages from polluting the main project Python environment.

## Upstream

Phase 6C-1 ran the manual vectorbt prototype against the fake Phase 3 fixture.

## Issue Observed

The local vectorbt install changed the main Python environment and downgraded an already-present pandas version. Future prototype work must run in isolated environments.

## Downstream

This policy supports future Backtrader, RQAlpha, Qlib, and deeper vectorbt prototypes.

## Scope

Allowed:

- document isolated prototype environment policy
- add helper scripts for future environment creation
- add tests for policy guardrails
- update review packet and handoff docs

Prohibited:

- no new framework install
- no uninstall
- no real backtest
- no adapter implementation
- no market data/API use
- no broker/live/order path
- no final engine selection

## Success Criteria

- Isolated prototype environment policy exists.
- Helper scripts create `.venv-prototypes/<tool-name>/` without installing packages.
- `.venv-prototypes/` is gitignored.
- Tests prove prototype packages remain out of `pyproject.toml`.
- Review packet records that no install, uninstall, backtest, or adapter work occurred.
