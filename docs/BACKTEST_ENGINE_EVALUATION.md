# Backtest Engine Evaluation

QuantPilot-AI 2.0 should not self-build a serious backtest engine before evaluating mature alternatives.

## Why Engine Selection Comes First

Backtesting is a high-risk foundation. A weak engine can create false confidence, hide market-rule errors, distort costs and slippage, or encourage overfitting. Engine candidates must be assessed before implementation or integration begins.

## Candidate Categories

- vectorized research
- event driven
- ML research platform
- full trading platform
- A-share oriented
- lightweight educational

## Evaluation Dimensions

- A-share rule fit
- T+1 support or adaptability
- lot size support or adaptability
- limit-up/down handling
- suspension handling
- fee/slippage support
- event-driven vs vectorized architecture
- ML research suitability
- Windows compatibility
- license/commercial risk
- live-trading isolation risk
- adapter feasibility

## No Selection in Phase 6A

Phase 6A does not install, import, run, prototype, or select any engine. It creates static metadata and validation rules only.

## Phase 6B Later

Phase 6B may propose controlled manual prototypes for a short list of candidates after ChatGPT review. Any future integration must go through adapters and contract tests.

