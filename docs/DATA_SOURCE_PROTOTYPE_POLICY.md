# Data-Source Prototype Policy

Phase 4A creates a manual-only harness for future data-source prototype planning.

## Why Manual-Only

Data-source prototypes can involve provider terms, network calls, rate limits, tokens, vendor accounts, and unclear data quality. Manual review keeps those risks outside CI and outside the core package until ChatGPT approves a specific prototype.

## CI Rule

Real data fetching is disabled in CI. CI may validate local templates, local fixtures, and standard-library code only.

Phase 4B raw outputs must stay in `local_artifacts/`, which is ignored by git.

## Tokens and Secrets

APIs, tokens, credentials, and secrets are not introduced in Phase 4A.

Provider packages must not be added to `pyproject.toml` during manual probes.

## Future Phase 4B Scope

Future Phase 4B may manually test candidates such as AkShare, Baostock, Tushare, OpenBB, and SimTradeData-style approaches only after ChatGPT approval. Those runs should remain controlled, documented, and outside automatic CI.

Probe success is not production approval and does not imply provider selection, data quality approval, adapter readiness, or trading readiness.

## Field Mapping Before Adapters

Field mapping comes before adapter implementation so future prototypes can compare provider outputs against the Phase 3 daily OHLCV contract before any framework is allowed into the core system.

## Output Contract

Any future prototype output must conform to the Phase 3 daily bar schema before it can be considered for adapter work.

## Real Data Readiness Gate

Real data cannot be used for alpha validation until the Phase 7E readiness gate is satisfied.

Raw provider data must not be committed. Provider reliability and schema mapping are required before larger use. Provider failures must be logged and must not be silently ignored.

## Phase 7F Controlled Retry Probes

Phase 7F allows only controlled manual provider retry probes for AkShare and Baostock.

Outputs must go under `local_artifacts/provider_probes/`. Raw full datasets must not be committed, production adapters must not be created, and no provider is approved without ChatGPT closure review.

Probe success does not prove alpha, approve data quality, approve a provider, or authorize larger validation.

## SimTradeData Policy

SimTradeData is architecture-reference only until license review. Do not clone, copy, integrate, commercialize, or create derivative work before explicit review.
