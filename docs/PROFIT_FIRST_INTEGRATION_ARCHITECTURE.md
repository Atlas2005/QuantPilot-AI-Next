# Profit-First Integration Architecture

R1 resets QuantPilot-AI-Next toward a profit-first, integration-first architecture for a 30-day v0.1 Capital-Test MVP.

This is an architecture reset only. The system is not trading-ready, does not connect to brokers, does not fetch real market data, and does not create order execution.

## Architecture Principle

Every future module should move the project closer to controlled capital testing through one of these outcomes:

- real data-backed signal validation after approved data gates
- realistic market simulation
- capital-aware trade candidate review
- sandbox order draft generation
- paper tracking
- execution-readiness review

Modules that only improve policy, taxonomy, or internal research machinery should be deferred unless they unblock one of those outcomes.

## Integration-First Rule

Before building major modules from scratch, QuantPilot should review mature external tools for:

- data access
- market simulation
- backtesting
- factor analytics
- data quality
- agent orchestration
- reporting
- execution-gateway benchmarking

Candidate decisions should use `adopt`, `wrap`, `prototype`, `benchmark_only`, `defer`, or `avoid`. R1 records intent only and approves no dependency installation.

## Capital-Test MVP Flow

The target v0.1 flow is:

1. Data candidates enter through reviewed provider adapters after approval.
2. Signals are generated with reproducible inputs and timestamp audit.
3. Validation checks sample split, OOS, walk-forward readiness, and leakage risk.
4. Market Reality Sandbox evaluates A-share feasibility, costs, slippage, and fill risk.
5. Capital & Permission checks convert ideas into feasible sandbox order drafts.
6. Risk & Cost reviews exposure, concentration, drawdown, turnover, and expected frictions.
7. Execution Gate blocks anything that violates safety, evidence, or permission rules.
8. Report Agent produces auditable trade candidate packets.

## R1 Non-Goals

- no live trading
- no broker connection
- no real order execution
- no real data fetch
- no package installation
- no `pyproject.toml` dependency changes
- no profitability claim
- no final framework selection

## Required Artifact

The R1 integration matrix lives at:

```text
data/integration_reset/r1_integration_replacement_matrix.json
```

The matrix is intentionally machine-readable so future modules can test that R1 safety fields remain disabled.
