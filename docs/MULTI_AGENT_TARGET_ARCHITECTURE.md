# Multi-Agent Target Architecture

R1 defines a target multi-agent architecture for later implementation. No agent runtime is installed or integrated in R1.

The target architecture is audit-first and gate-driven. Agents should produce evidence, review packets, or blocked states. They must not create live trading or broker execution paths without future explicit approval.

## Target Agents

- Data Agent: manages approved data adapters, schema checks, data freshness, and provider failure state.
- News/Event Agent: tracks event inputs and source provenance after approved sources exist.
- Sector/Concept Agent: maps securities to sector and concept context.
- Signal Agent: creates candidate signals from approved factor or model workflows.
- Fundamental/Valuation Agent: reviews valuation, earnings, and fundamental context where available.
- Factor Agent: manages factor definitions, neutralization assumptions, and factor diagnostics.
- Validation Agent: checks leakage, OOS, walk-forward, sample size, and evidence gates.
- Capital & Permission Agent: evaluates funds, permissions, tradable instruments, lot size, and T+0/T+1 feasibility.
- Risk & Cost Agent: estimates transaction costs, slippage, drawdown, turnover, liquidity, and capacity limits.
- Portfolio Agent: ranks candidates against current exposure and portfolio constraints.
- Execution Gate Agent: blocks unsafe, unsupported, or unapproved order drafts.
- Auditor Agent: records timestamped decisions, data lineage, safety flags, and evidence summaries.
- Updater Agent: monitors upstream dependency, license, version, and maintenance risk.
- Report Agent: produces human-readable candidate packets and review summaries.

## Control Model

Agents should exchange structured artifacts rather than free-form trading instructions.

Every candidate moving toward capital testing must carry:

- data source and timestamp lineage
- signal and validation evidence
- market rule feasibility
- capital and permission feasibility
- cost and slippage assumptions
- risk limits
- rejection reasons where blocked
- audit trail

## Runtime Candidate Policy

LangGraph, OpenAI Agents SDK, CrewAI, and AutoGen are R1 architecture benchmarks only. They are not installed, imported, selected, or approved in R1.

Agent orchestration remains blocked until the Market Reality Sandbox, data approval gates, and execution gate contracts are ready.
