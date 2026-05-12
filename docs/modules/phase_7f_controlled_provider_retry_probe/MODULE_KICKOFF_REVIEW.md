# Phase 7F Module Kickoff Review

## Status

ChatGPT approved this Phase 7F kickoff before Codex implementation.

## Purpose

Phase 7F creates a controlled provider retry readiness probe layer for AkShare and Baostock. This is a readiness probe, not data integration, not provider approval, and not alpha validation.

## Upstream

- Phase 4A/4B provider probe framework
- Phase 7E real-data readiness gate

## Downstream

- provider readiness review
- larger local fixture preparation
- real-data validation only after explicit approval

## Language / Runtime Decision

`src/` remains Python standard library only. Manual scripts under `tools/manual_provider_probes/` may attempt optional provider imports inside guarded script bodies, but those provider packages do not become project dependencies.

## Allowed Scope

- standard-library readiness summary types and validators
- static provider probe policy metadata
- manual-only AkShare and Baostock retry probe scripts
- documentation and tests that do not touch the network or providers

## Prohibited Scope

- no approved data source
- no production data-source adapter
- no provider API client in `src/`
- no token or secrets handling
- no raw data commit
- no large data fetch
- no real factor validation
- no real alpha claim
- no backtest
- no strategy tournament
- no broker/live/order path

## Success Criteria

- provider retry probe policy exists and remains conservative
- summary validation rejects adapter or alpha-validation approval
- manual scripts write summaries only under `local_artifacts/provider_probes/`
- tests require no provider packages and no internet
- review packet confirms no probes were run in this implementation
