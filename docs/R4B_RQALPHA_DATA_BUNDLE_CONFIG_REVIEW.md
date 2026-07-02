# R4B RQAlpha Data Bundle Config Review

R4B reviews historical RQAlpha data bundle, config, and local-fixture evidence for the optional R4A A-share adapter.

This stage does not run RQAlpha, does not add an RQAlpha dependency, and does not create or mutate local artifacts. It reads existing repository evidence and turns that evidence into structured local review output.

R4B does not create a backtest engine, fill simulator, portfolio accounting layer, or fake metrics. QuantPilot should keep only A-share/provider/account/broker/agent-facing glue and normalized contracts while relying on mature frameworks where they fit.

RQAlpha remains the mature-framework target for A-share event-driven backtest semantics. The current evidence shows install/import review value, but R4B does not prove local runtime execution and does not claim production or live readiness.

Missing RQAlpha, data bundle, or config evidence must not block vectorbt, Qlib, or future DeepSeek multi-agent work. Those workflows remain independent from this review layer.

A future R4C may attempt an isolated local RQAlpha prototype only if data bundle and config requirements are explicit. Any such work should remain isolated from the main project environment and avoid production adapter, broker, live-trading, dependency, or final engine-selection claims.
