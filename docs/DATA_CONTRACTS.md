# Data Contracts

Phase 3 introduces a provisional local data contract for A-share daily OHLCV research data.

## Purpose

The data contract defines the expected shape of local daily bar fixtures before any real data source is connected.

## Why Local Fixtures Come First

Local fixtures make validation reproducible and safe. They let the project test schema and parsing behavior without market data downloads, API keys, vendor accounts, or provider-specific assumptions.

## Daily OHLCV Schema

The provisional daily bar schema version is `0.1.0`.

Required fields:

- `symbol`
- `trade_date`
- `open`
- `high`
- `low`
- `close`
- `volume`
- `amount`
- `adjustment`
- `asset_type`

Numeric fields:

- `open`
- `high`
- `low`
- `close`
- `volume`
- `amount`

## Adjustment Type Limitation

Adjustment type is currently only a marker: `raw`, `qfq`, `hfq`, or `unknown`.

Phase 3 does not calculate adjusted prices, compare adjustment methods, or verify vendor adjustment correctness.

## A-Share Symbol Format Limitation

Fixtures use examples such as `000001.SZ` and `600000.SH`, but Phase 3 does not enforce a complete A-share symbol grammar.

## No Real Trading Calendar Yet

Phase 3 checks `YYYY-MM-DD` formatting and per-symbol ascending order only. It does not check real exchange calendars, holidays, suspensions, or actual trading days.

## Future Framework Relationship

Future phases may evaluate Pandera, Great Expectations, DuckDB, Parquet, PyArrow, Polars, or other tools through the candidate registry and adapter/contract process. Phase 3 does not install or import them.

## Future Data-Source Relationship

Future controlled prototypes may evaluate AkShare, Baostock, Tushare, OpenBB, or other sources after ChatGPT-led review. Phase 3 does not connect to any provider.

