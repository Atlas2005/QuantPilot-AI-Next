# Capital-Aware Fast Compounding Mode

R1 replaces the old framing of "small capital survival mode" with Capital-Aware Fast Compounding Mode.

This mode focuses on capital feasibility, compounding discipline, and controlled capital-test readiness. It does not claim profitability and does not approve live trading.

## Evaluation Scope

Every capital-test candidate should eventually be checked for:

- current funds
- account permissions
- minimum lot size
- tradable instruments
- T+0/T+1 feasibility
- transaction costs
- slippage
- liquidity and capacity
- price-limit risk
- order rejection risk
- concentration and drawdown limits

## Decision Output

The mode should produce one of:

- rejected before validation
- rejected by market reality
- accepted for sandbox review
- accepted as a sandbox order draft
- accepted for paper tracking after future approval

No output is a live order or trading instruction in R1.

## Operating Bias

Capital-aware compounding prefers:

- fewer candidates with stronger feasibility evidence
- explicit cost and slippage assumptions
- strict rejection reasons
- paper feedback before any capital exposure
- auditability over speed when evidence is incomplete

## R1 Relationship

R1 creates the language, architecture target, and integration matrix needed for this mode. It does not implement account connections, broker permissions, or live execution.
