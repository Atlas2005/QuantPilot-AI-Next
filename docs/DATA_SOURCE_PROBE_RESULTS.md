# Data-Source Probe Results

Phase 4B probe results were captured from manual-only local scripts.

This document must not include raw market data rows.

## Provider Results

### Baostock

- Provider attempted: Baostock
- Package installed in this phase: No
- Package import result: available in the local environment
- Probe command run: `python tools/manual_provider_probes/probe_baostock_daily.py`
- Success/failure: failed safely
- Row count: 0
- Returned columns: none
- Mapping coverage versus Phase 3 daily OHLCV contract: 0 of 10 fields mapped because no rows/columns were returned
- Missing contract fields: `symbol`, `trade_date`, `open`, `high`, `low`, `close`, `volume`, `amount`, `adjustment`, `asset_type`
- Major observed error: provider login/network receive error
- Proceed to deeper prototype later: not yet; retry only after ChatGPT review in an approved network/provider environment

### AkShare

- Provider attempted: AkShare
- Package installed in this phase: No
- Package import result: available in the local environment
- Probe command run: `python tools/manual_provider_probes/probe_akshare_daily.py`
- Success/failure: failed safely
- Row count: 0
- Returned columns: none
- Mapping coverage versus Phase 3 daily OHLCV contract: 0 of 10 fields mapped because no rows/columns were returned
- Missing contract fields: `symbol`, `trade_date`, `open`, `high`, `low`, `close`, `volume`, `amount`, `adjustment`, `asset_type`
- Major observed error: network connection failure when reaching provider endpoint
- Proceed to deeper prototype later: not yet; retry only after ChatGPT review in an approved network/provider environment

## Major Risks

- Tiny probe success does not imply production readiness.
- Provider package installation is not a project dependency decision.
- Returned columns may differ by provider version, endpoint, market, or date.
- Mapping coverage does not validate data quality, correctness, survivorship bias, adjustment correctness, or trading readiness.
