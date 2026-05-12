# Data-Source Prototype Policy

Phase 4A creates a manual-only harness for future data-source prototype planning.

## Why Manual-Only

Data-source prototypes can involve provider terms, network calls, rate limits, tokens, vendor accounts, and unclear data quality. Manual review keeps those risks outside CI and outside the core package until ChatGPT approves a specific prototype.

## CI Rule

Real data fetching is disabled in CI. CI may validate local templates, local fixtures, and standard-library code only.

## Tokens and Secrets

APIs, tokens, credentials, and secrets are not introduced in Phase 4A.

## Future Phase 4B Scope

Future Phase 4B may manually test candidates such as AkShare, Baostock, Tushare, OpenBB, and SimTradeData-style approaches only after ChatGPT approval. Those runs should remain controlled, documented, and outside automatic CI.

## Field Mapping Before Adapters

Field mapping comes before adapter implementation so future prototypes can compare provider outputs against the Phase 3 daily OHLCV contract before any framework is allowed into the core system.

## Output Contract

Any future prototype output must conform to the Phase 3 daily bar schema before it can be considered for adapter work.

## SimTradeData Policy

SimTradeData is architecture-reference only until license review. Do not clone, copy, integrate, commercialize, or create derivative work before explicit review.

