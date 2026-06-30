# DeepSeek Multi-Agent Contract Preflight

R16 creates a minimal contract and preflight layer for future DeepSeek-backed agents.

## Purpose

QuantPilot-AI-Next is A-share focused, profit-first, capital/account-aware, open-source-first, and Market Reality Sandbox-driven. R16 prepares the AI layer for a future DeepSeek runtime while keeping the current stage contract-only and offline.

## Contract-Only Stage

R16 does not call DeepSeek, does not import a model SDK, does not add API keys, and does not read environment-specific secrets. It defines typed contracts, default role permissions, validation helpers, and a deterministic preflight result.

No network, news crawling, live trading, broker execution, RQAlpha execution, Qlib execution, or real account access is added.

## Roles

R16 defines these roles:

- DATA_AGENT
- NEWS_AGENT
- STATS_AGENT
- FACTOR_AGENT
- MARKET_REGIME_AGENT
- RISK_AGENT
- ACCOUNT_AGENT
- EXECUTION_AGENT
- SUPERVISOR_AGENT

## Permissions

Tool permissions are explicit and role-scoped:

- READ_MARKET_DATA
- READ_NEWS_EVENTS
- READ_ACCOUNT_SNAPSHOT
- COMPUTE_STATISTICS
- GENERATE_FACTOR_CANDIDATE
- PROPOSE_ACTION
- REVIEW_RISK
- REVIEW_COMPLIANCE
- ORCHESTRATE_AGENTS
- WRITE_AUDIT_LOG

Requests using permissions outside their role defaults are rejected by preflight.

## Safety Rules

The validation layer enforces:

- confidence values are between 0 and 1
- action proposals must be typed contracts, not free-form text
- action side is BUY, SELL, or HOLD
- BUY and SELL require positive quantity and non-empty required gates
- HOLD quantity must be zero
- sandbox mode is required for BUY and SELL proposals
- execution agents cannot bypass gates
- supervisors can allow only sandbox decisions, not live trading
- live-trading decision strings are rejected

## Future DeepSeek Runtime

DeepSeek is the intended base model later, but R16 keeps the runtime separate from contracts. Future agent outputs must be converted into typed contracts before they can affect sandbox decisions. Natural-language-only outputs are not valid order proposals.

## Gate-Controlled Automation

R16 allows future AI automation to remain gate-controlled:

agent findings -> typed proposals -> risk/compliance review -> supervisor sandbox decision -> downstream sandbox/paper gates

The supervisor can allow proposals only into sandbox paths. It cannot approve live trading.

## R17 Next Step

R17 should add a fake/offline DeepSeek response adapter that maps deterministic mock model outputs into these typed contracts, still without network calls, API keys, or live execution.
