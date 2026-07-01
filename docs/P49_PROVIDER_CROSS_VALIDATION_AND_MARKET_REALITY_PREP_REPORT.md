# P49 Provider Cross-Validation and Market-Reality Prep Report

## Status

P49 adds a minimal provider cross-validation layer and Tushare normalized daily-bar support.

This phase starts after P48 BaoStock broader real-provider sample completion. P49 does not claim profitability, does not simulate fills, and does not add a generic blocking safety gate. Its purpose is to prepare provider reconciliation before moving into A-share market-reality modeling.

## Branch

`p49-provider-cross-validation-and-market-reality-prep`

## Implemented Changes

### 1. Tushare Provider Identity

Updated:

`src/quantpilot_core/real_data_provider/contracts.py`

Added:

`ProviderName.TUSHARE`

This allows Tushare records to use the same provider identity mechanism as AkShare and BaoStock.

### 2. Tushare Daily-Bar Adapter and Normalizer

Added:

`src/quantpilot_core/real_data_provider/tushare_adapter.py`

Key behavior:

- Supports optional Tushare dependency detection.
- Supports injected fake clients for offline deterministic tests.
- Does not require live Tushare API calls in pytest.
- Normalizes Tushare daily rows into existing `NormalizedDailyBar`.
- Uses `ProviderName.TUSHARE`.
- Requests fields:
  - `ts_code`
  - `trade_date`
  - `open`
  - `high`
  - `low`
  - `close`
  - `vol`
  - `amount`
  - `pct_chg`

Normalization notes:

- Tushare `vol` is normalized to share-level volume for comparison.
- Tushare `amount` is normalized to CNY-level notional for comparison.
- Volume and amount remain secondary validation fields because provider unit semantics can differ.

### 3. Provider Cross-Validation Module

Added:

`src/quantpilot_core/provider_cross_validation/`

Files:

- `__init__.py`
- `contracts.py`
- `comparison.py`
- `report.py`

The module compares two collections of existing `NormalizedDailyBar` records.

It reuses existing provider contracts and does not define a new market-data record type.

## Comparison Design

### Symbol Canonicalization

The module normalizes common A-share symbol formats:

| Input | Canonical |
|---|---|
| `sz.000001` | `000001.SZ` |
| `sh.600519` | `600519.SH` |
| `000001.SZ` | `000001.SZ` |
| `600519.SH` | `600519.SH` |

This allows BaoStock-style symbols and Tushare-style symbols to be compared without changing the existing BaoStock adapter output.

### Primary Fields

Primary fields:

- `open`
- `high`
- `low`
- `close`

Primary price mismatches are classified as:

`fatal`

This does not block execution by default. It only marks the discrepancy as high severity for later reconciliation.

### Secondary Fields

Secondary fields:

- `volume`
- `amount`

Secondary mismatches are classified as:

`warning`

Reason:

Provider unit semantics can differ, especially for volume and amount fields. These fields should inform reconciliation but should not automatically block downstream research.

### Coverage Differences

Coverage gaps are classified as:

`warning`

Examples:

- missing left-provider record
- missing right-provider record

Coverage differences should be reviewed, but this module does not reject or block provider data by default.

## Report Contents

The generated provider cross-validation report includes:

- `left_provider`
- `right_provider`
- `left_count`
- `right_count`
- `common_count`
- `missing_left_count`
- `missing_right_count`
- `fatal_issue_count`
- `warning_issue_count`
- `issues`
- `market_reality_notes`

The report explicitly records:

- Provider agreement on OHLC is a prerequisite for later tradability modeling.
- Volume and amount discrepancies are secondary because provider unit semantics can differ.
- This module does not claim profitability and does not simulate fills.

## Validation

Command:

`.venv/bin/python -m pytest tests/provider_cross_validation tests/real_data_provider -q`

Result:

`32 passed in 0.01s`

## Project Alignment

P49 remains aligned with QuantPilot-AI-Next requirements:

- Profit-first, but no premature profitability claim.
- Integration-first, reusing existing `NormalizedDailyBar` and provider contracts.
- A-share focused via symbol canonicalization and provider reconciliation.
- No live broker or live trading.
- No live provider calls in pytest.
- No `.external/` artifact changes.
- No generic overblocking safety gate.
- Prepares market-reality modeling instead of expanding abstract preflight layers.

## What P49 Does Not Do

P49 does not:

- claim profitability
- simulate fills
- run broker execution
- create live orders
- replace BaoStock with Tushare
- make Tushare mandatory for offline tests
- block downstream use by default
- create a new market-data contract

## Next Phase

The next phase should move toward A-share market-reality modeling.

Recommended next phase:

`P50 A-share Market Reality Sandbox v1`

P50 should focus on:

- T+1 sellability
- 100-share board-lot constraints
- cash constraints
- commission
- stamp duty
- slippage
- limit-up / limit-down tradability
- suspension handling
- volume / capacity limits
- ETF-specific rule differences
- conversion from factor signal to executable candidate
- preparation for fill simulation and paper ledger integration
