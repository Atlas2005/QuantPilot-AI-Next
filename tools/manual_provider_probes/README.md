# Manual Provider Probes

These probes are manual-only and are not run in CI.

Raw provider outputs must stay under `local_artifacts/`, which is ignored by git. Do not commit raw CSV or JSON market data.

Provider packages used by these scripts are not project dependencies and must not be added to `pyproject.toml`.

Probe results are not investment advice. A successful probe does not mean production readiness, provider selection, data quality approval, or trading readiness.

