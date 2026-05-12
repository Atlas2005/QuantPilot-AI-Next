# Controlled Provider Retry Probe

Phase 7F creates a controlled retry readiness probe for AkShare and Baostock after the Phase 7E real-data readiness gate.

This phase does not approve either provider. It does not create production adapters, provider clients in `src/`, real alpha evidence, or trading readiness.

## Why Retry Probes Are Needed

Earlier provider probes established that real provider behavior must be captured carefully. Phase 7E then made real-data readiness explicit. Phase 7F is a narrow step that checks whether tiny manual samples can be summarized and mapped against the Phase 3 daily OHLCV contract.

## Manual Commands

These scripts are manual-only and are not run by CI:

```powershell
python tools\manual_provider_probes\run_akshare_retry_probe.py
python tools\manual_provider_probes\run_baostock_retry_probe.py
```

The scripts use guarded optional imports. If a provider package is missing or a network/provider call fails, the script should write a conservative JSON summary instead of failing open.

## Output Location

Summaries must be written under:

```text
local_artifacts/provider_probes/
```

Raw full provider datasets must not be committed and must not be written under tracked `data/`.

## What Success Means

A successful tiny probe means only that the provider returned a small sample and some fields appeared mappable.

It does not mean:

- provider approval
- adapter approval
- data quality approval
- alpha evidence
- statistical significance
- backtest readiness
- trading readiness

## What Failure Means

A failed, skipped, or inconclusive probe is acceptable if it is safely captured. Provider failures must be logged and not silently ignored.

## Next Review

ChatGPT must review Phase 7F output before any larger real-data validation, provider approval, external analytics install, or strategy tournament work begins.
