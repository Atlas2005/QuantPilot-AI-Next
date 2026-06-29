# QuantPilot-AI-Next

QuantPilot-AI-Next is the official next-generation project for QuantPilot-AI 2.0.

QuantPilot-AI 2.0 is planned as a profit-first, integration-first, adapter-first, contract-first, A-share-first AI quant research and trading decision platform. The project is designed to move toward controlled capital testing through evidence-gated research, realistic A-share market modeling, reproducible validation, paper feedback, and formal readiness review.

## Current Phase

The repository is in R7: Real A-share Small Sample Data Gate, implemented by Codex and pending ChatGPT closure review.

The repository contains planning docs, safety gates, core contracts, local fixtures, candidate registries, market-rule foundations, prototype evidence, the R1 integration reset matrix, R1.1 open-source integration enforcement guardrails, R2 Market Reality Sandbox contracts, the R3 Provider-Sandbox Fixture Bridge, the R4 Controlled Provider Probe Execution Gate, the R5 Controlled Mock Provider Probe Run, the R6 Controlled Provider Adapter Probe Plan, and the R7 Real A-share Small Sample Data Gate. It must not contain broker connection, live trading path, real order execution path, provider API calls, real market data ingestion, production data assets, or unapproved agent execution workflow.

## Legacy v2 Position

The old QuantPilot-AI v2 repository and `v2-real-data` branch are legacy research archives only.

They may be referenced for lessons learned, guardrail ideas, CI/reference discipline, A-share constraint history, and failure or architecture-debt history. They must not be copied as the new core architecture, and old custom backtester, ML trainer, factor builder, order generator, or execution modules must not be migrated as new core.

## Safety Notice

This project is not trading-ready.

This project is not financial advice.

No live trading, broker connection, or real order execution exists at this stage.

No profitability claim may be made without clean data, realistic market rules, sample-out validation, walk-forward/OOS evidence, paper feedback, and risk-adjusted performance review.

All safety defaults in the Phase 0B skeleton are false.

## Role Split

ChatGPT is the architecture lead for professional planning, module kickoff review, open-source alternative assessment, upstream/downstream consistency review, module closure retrospective, and final review before commit.

Codex is responsible for creating files, organizing documentation, running validation commands, and producing concise review packets. Codex must not independently decide the strategic roadmap, module order, open-source selection, or trading-readiness judgment.

## Planning Index

- [Project Positioning](docs/PROJECT_POSITIONING.md)
- [Strategic Handoff](docs/STRATEGIC_HANDOFF.md)
- [Open-Source-First Policy](docs/OPEN_SOURCE_FIRST_POLICY.md)
- [Module Selection Policy](docs/MODULE_SELECTION_POLICY.md)
- [Language Architecture](docs/LANGUAGE_ARCHITECTURE.md)
- [Dependency Update Policy](docs/DEPENDENCY_UPDATE_POLICY.md)
- [Legacy Migration Policy](docs/LEGACY_MIGRATION_POLICY.md)
- [Open-Source Candidate Universe](docs/OPEN_SOURCE_CANDIDATE_UNIVERSE.md)
- [Roadmap](docs/QUANTPILOT_AI_2_0_ROADMAP.md)
- [Success Metrics](docs/SUCCESS_METRICS.md)
- [First 30 Days Plan](docs/FIRST_30_DAYS_PLAN.md)
- [Workflow Automation Policy](docs/WORKFLOW_AUTOMATION_POLICY.md)
- [Module Governance Policy](docs/MODULE_GOVERNANCE_POLICY.md)
- [Module Review Template](docs/MODULE_REVIEW_TEMPLATE.md)
- [Current Project State](docs/CURRENT_PROJECT_STATE.md)
- [Decisions](docs/DECISIONS.md)
- [Next Chat Handoff](docs/NEXT_CHAT_HANDOFF.md)
- [Next Step Decision](docs/NEXT_STEP_DECISION.md)
- [Review Packet](docs/REVIEW_PACKET.md)
- [Profit-First Integration Architecture](docs/PROFIT_FIRST_INTEGRATION_ARCHITECTURE.md)
- [Multi-Agent Target Architecture](docs/MULTI_AGENT_TARGET_ARCHITECTURE.md)
- [Market Reality Sandbox Architecture](docs/MARKET_REALITY_SANDBOX_ARCHITECTURE.md)
- [Market Reality Sandbox Contracts](docs/MARKET_REALITY_SANDBOX_CONTRACTS.md)
- [Provider-Sandbox Fixture Bridge](docs/PROVIDER_SANDBOX_FIXTURE_BRIDGE.md)
- [Controlled Provider Probe Gate](docs/CONTROLLED_PROVIDER_PROBE_GATE.md)
- [Controlled Mock Provider Probe Run](docs/CONTROLLED_MOCK_PROVIDER_PROBE_RUN.md)
- [Controlled Provider Adapter Probe Plan](docs/CONTROLLED_PROVIDER_ADAPTER_PROBE_PLAN.md)
- [Real A-share Small Sample Data Gate](docs/REAL_A_SHARE_SMALL_SAMPLE_DATA_GATE.md)
- [Capital-Aware Fast Compounding Mode](docs/CAPITAL_AWARE_FAST_COMPOUNDING_MODE.md)
- [Open-Source Replacement Strategy](docs/OPEN_SOURCE_REPLACEMENT_STRATEGY.md)
- [Open-Source Integration Enforcement](docs/OPEN_SOURCE_INTEGRATION_ENFORCEMENT.md)
- [Upstream Dependency Intelligence Layer](docs/UPSTREAM_DEPENDENCY_INTELLIGENCE_LAYER.md)
- [Thirty-Day Capital-Test MVP Plan](docs/THIRTY_DAY_CAPITAL_TEST_MVP_PLAN.md)
