"""Deterministic in-memory normalizers for A-share information inputs."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import pandas as pd

from quantpilot_core.data_provider_normalization import canonicalize_a_share_symbol
from quantpilot_core.information_layer.contracts import (
    ANNOUNCEMENT_EVENTS_COLUMNS,
    CONCEPT_MEMBERSHIPS_COLUMNS,
    DIVIDEND_RECORDS_COLUMNS,
    FUND_HOLDINGS_COLUMNS,
    MACRO_POLICY_EVENTS_COLUMNS,
    MARGIN_TRADING_SNAPSHOTS_COLUMNS,
    MONEYFLOW_SNAPSHOTS_COLUMNS,
    NEWS_EVENTS_COLUMNS,
    NORTHBOUND_HOLDINGS_COLUMNS,
    SHAREHOLDER_SNAPSHOTS_COLUMNS,
    SOCIAL_SENTIMENT_EVENTS_COLUMNS,
    STABILIZATION_FLOW_CLUES_COLUMNS,
    VALUATION_SNAPSHOTS_COLUMNS,
)


COMMON_ALIASES: dict[str, tuple[str, ...]] = {
    "symbol": ("symbol", "ts_code", "code", "ticker", "instrument"),
    "source": ("source", "source_name", "channel"),
    "provider": ("provider", "vendor", "data_provider"),
    "evidence_text": ("evidence_text", "evidence", "snippet", "content", "raw_text"),
    "url": ("url", "link"),
    "date": ("date", "trade_date", "report_date", "publish_date"),
    "datetime": ("datetime", "timestamp", "time", "publish_time", "pub_time"),
}

SCHEMA_ALIASES: dict[str, dict[str, tuple[str, ...]]] = {
    "news_events": {
        "headline": ("headline", "title"),
        "summary": ("summary", "abstract"),
        "sentiment_score": ("sentiment_score", "sentiment"),
        "importance_score": ("importance_score", "importance"),
    },
    "macro_policy_events": {
        "policy_area": ("policy_area", "area"),
        "event_type": ("event_type", "type"),
        "title": ("title", "headline"),
        "impact_direction": ("impact_direction", "direction"),
        "importance_score": ("importance_score", "importance"),
    },
    "social_sentiment_events": {
        "platform": ("platform", "source_platform"),
        "topic": ("topic", "keyword"),
        "sentiment_score": ("sentiment_score", "sentiment"),
        "mention_count": ("mention_count", "mentions"),
    },
    "northbound_holdings": {
        "holding_shares": ("holding_shares", "shares"),
        "holding_value": ("holding_value", "value"),
        "holding_ratio": ("holding_ratio", "ratio"),
        "net_buy_value": ("net_buy_value", "net_buy"),
    },
    "stabilization_flow_clues": {
        "vehicle_type": ("vehicle_type", "vehicle"),
        "flow_value": ("flow_value", "amount"),
        "flow_direction": ("flow_direction", "direction"),
        "confidence_score": ("confidence_score", "confidence"),
    },
    "fund_holdings": {
        "fund_code": ("fund_code", "fund_id"),
        "fund_name": ("fund_name", "fund"),
        "holding_shares": ("holding_shares", "shares"),
        "holding_value": ("holding_value", "value"),
        "portfolio_weight": ("portfolio_weight", "weight"),
    },
    "shareholder_snapshots": {
        "shareholder_name": ("shareholder_name", "holder_name"),
        "holding_shares": ("holding_shares", "shares"),
        "holding_ratio": ("holding_ratio", "ratio"),
        "shareholder_rank": ("shareholder_rank", "rank"),
    },
    "dividend_records": {
        "cash_dividend_per_share": ("cash_dividend_per_share", "cash_dividend"),
        "stock_dividend_ratio": ("stock_dividend_ratio", "stock_dividend"),
        "record_date": ("record_date",),
        "ex_dividend_date": ("ex_dividend_date", "ex_date"),
    },
    "valuation_snapshots": {
        "pe_ttm": ("pe_ttm", "pe"),
        "pb": ("pb",),
        "ps_ttm": ("ps_ttm", "ps"),
        "market_cap": ("market_cap", "total_market_value"),
    },
    "concept_memberships": {
        "concept_name": ("concept_name", "concept", "theme"),
        "membership_weight": ("membership_weight", "weight"),
        "is_active": ("is_active", "active"),
    },
    "margin_trading_snapshots": {
        "financing_balance": ("financing_balance", "margin_balance"),
        "securities_lending_balance": ("securities_lending_balance", "short_balance"),
        "financing_buy_value": ("financing_buy_value", "financing_buy"),
        "repayment_value": ("repayment_value", "repayment"),
    },
    "moneyflow_snapshots": {
        "main_net_inflow": ("main_net_inflow", "main_inflow"),
        "large_net_inflow": ("large_net_inflow", "large_inflow"),
        "retail_net_inflow": ("retail_net_inflow", "retail_inflow"),
        "turnover_rate": ("turnover_rate", "turnover"),
    },
    "announcement_events": {
        "announcement_type": ("announcement_type", "type"),
        "title": ("title", "headline"),
        "importance_score": ("importance_score", "importance"),
    },
}

NUMERIC_FIELDS = {
    "sentiment_score",
    "importance_score",
    "mention_count",
    "holding_shares",
    "holding_value",
    "holding_ratio",
    "net_buy_value",
    "flow_value",
    "confidence_score",
    "portfolio_weight",
    "shareholder_rank",
    "cash_dividend_per_share",
    "stock_dividend_ratio",
    "pe_ttm",
    "pb",
    "ps_ttm",
    "market_cap",
    "membership_weight",
    "financing_balance",
    "securities_lending_balance",
    "financing_buy_value",
    "repayment_value",
    "main_net_inflow",
    "large_net_inflow",
    "retail_net_inflow",
    "turnover_rate",
}

DATE_FIELDS = {"date", "record_date", "ex_dividend_date"}
DATETIME_FIELDS = {"datetime"}
BOOLEAN_FIELDS = {"is_active"}
REQUIRED_BASE_FIELDS = {"source", "provider", "evidence_text"}


def normalize_news_events_frame(frame: pd.DataFrame) -> pd.DataFrame:
    return _normalize_information_frame("news_events", frame, NEWS_EVENTS_COLUMNS)


def normalize_macro_policy_events_frame(frame: pd.DataFrame) -> pd.DataFrame:
    return _normalize_information_frame("macro_policy_events", frame, MACRO_POLICY_EVENTS_COLUMNS)


def normalize_social_sentiment_events_frame(frame: pd.DataFrame) -> pd.DataFrame:
    return _normalize_information_frame("social_sentiment_events", frame, SOCIAL_SENTIMENT_EVENTS_COLUMNS)


def normalize_northbound_holdings_frame(frame: pd.DataFrame) -> pd.DataFrame:
    return _normalize_information_frame("northbound_holdings", frame, NORTHBOUND_HOLDINGS_COLUMNS)


def normalize_stabilization_flow_clues_frame(frame: pd.DataFrame) -> pd.DataFrame:
    return _normalize_information_frame("stabilization_flow_clues", frame, STABILIZATION_FLOW_CLUES_COLUMNS)


def normalize_fund_holdings_frame(frame: pd.DataFrame) -> pd.DataFrame:
    return _normalize_information_frame("fund_holdings", frame, FUND_HOLDINGS_COLUMNS)


def normalize_shareholder_snapshots_frame(frame: pd.DataFrame) -> pd.DataFrame:
    return _normalize_information_frame("shareholder_snapshots", frame, SHAREHOLDER_SNAPSHOTS_COLUMNS)


def normalize_dividend_records_frame(frame: pd.DataFrame) -> pd.DataFrame:
    return _normalize_information_frame("dividend_records", frame, DIVIDEND_RECORDS_COLUMNS)


def normalize_valuation_snapshots_frame(frame: pd.DataFrame) -> pd.DataFrame:
    return _normalize_information_frame("valuation_snapshots", frame, VALUATION_SNAPSHOTS_COLUMNS)


def normalize_concept_memberships_frame(frame: pd.DataFrame) -> pd.DataFrame:
    return _normalize_information_frame("concept_memberships", frame, CONCEPT_MEMBERSHIPS_COLUMNS)


def normalize_margin_trading_snapshots_frame(frame: pd.DataFrame) -> pd.DataFrame:
    return _normalize_information_frame("margin_trading_snapshots", frame, MARGIN_TRADING_SNAPSHOTS_COLUMNS)


def normalize_moneyflow_snapshots_frame(frame: pd.DataFrame) -> pd.DataFrame:
    return _normalize_information_frame("moneyflow_snapshots", frame, MONEYFLOW_SNAPSHOTS_COLUMNS)


def normalize_announcement_events_frame(frame: pd.DataFrame) -> pd.DataFrame:
    return _normalize_information_frame("announcement_events", frame, ANNOUNCEMENT_EVENTS_COLUMNS)


def _normalize_information_frame(
    schema_name: str,
    frame: pd.DataFrame,
    columns: tuple[str, ...],
) -> pd.DataFrame:
    source = _require_frame(frame, schema_name)
    aliases = {**COMMON_ALIASES, **SCHEMA_ALIASES.get(schema_name, {})}
    required = _required_columns(columns)
    resolved = {column: _resolve_input_column(source, column, aliases) for column in columns}
    missing = tuple(column for column in required if resolved[column] is None)
    if missing:
        raise ValueError(f"{schema_name} input missing required columns: {', '.join(missing)}")

    data: dict[str, pd.Series] = {}
    for column in columns:
        input_column = resolved[column]
        values = _empty_series(source) if input_column is None else source[input_column]
        data[column] = _coerce_column(values, column)

    normalized = pd.DataFrame(data)
    _require_non_missing(normalized, required, schema_name)
    sort_columns = [column for column in ("symbol", "date", "datetime", "source") if column in columns]
    return normalized.sort_values(sort_columns, kind="stable").reset_index(drop=True)


def _required_columns(columns: tuple[str, ...]) -> tuple[str, ...]:
    required = set(REQUIRED_BASE_FIELDS)
    if "symbol" in columns:
        required.add("symbol")
    if "datetime" in columns:
        required.add("datetime")
    if "date" in columns:
        required.add("date")
    return tuple(column for column in columns if column in required)


def _resolve_input_column(
    frame: pd.DataFrame,
    output_column: str,
    aliases: Mapping[str, tuple[str, ...]],
) -> str | None:
    for candidate in aliases.get(output_column, (output_column,)):
        if candidate in frame.columns:
            return candidate
    return None


def _coerce_column(values: pd.Series, column: str) -> pd.Series:
    if column == "symbol":
        return _symbol_series(values)
    if column in DATE_FIELDS:
        return _date_series(values)
    if column in DATETIME_FIELDS:
        return _datetime_series(values)
    if column in NUMERIC_FIELDS:
        return _numeric_series(values)
    if column in BOOLEAN_FIELDS:
        return _boolean_series(values)
    return values.fillna("").astype(str)


def _require_frame(frame: pd.DataFrame, schema_name: str) -> pd.DataFrame:
    if not isinstance(frame, pd.DataFrame):
        raise TypeError(f"{schema_name} input must be a pandas DataFrame")
    if frame.empty:
        raise ValueError(f"{schema_name} input must be non-empty")
    return frame.copy()


def _require_non_missing(frame: pd.DataFrame, columns: tuple[str, ...], schema_name: str) -> None:
    missing = tuple(column for column in columns if frame[column].isna().any() or (frame[column] == "").any())
    if missing:
        raise ValueError(f"{schema_name} input has missing required values: {', '.join(missing)}")


def _empty_series(frame: pd.DataFrame) -> pd.Series:
    return pd.Series([pd.NA] * len(frame), index=frame.index)


def _symbol_series(values: pd.Series) -> pd.Series:
    if values.isna().any() or (values.astype(str).str.strip() == "").any():
        raise ValueError("symbol must not contain missing values")
    return values.map(canonicalize_a_share_symbol).astype("string")


def _date_series(values: pd.Series) -> pd.Series:
    return pd.to_datetime(values, errors="raise").dt.strftime("%Y-%m-%d")


def _datetime_series(values: pd.Series) -> pd.Series:
    return pd.to_datetime(values, errors="raise").dt.strftime("%Y-%m-%dT%H:%M:%S")


def _numeric_series(values: pd.Series) -> pd.Series:
    return pd.to_numeric(values.replace("", pd.NA), errors="raise").astype("Float64")


def _boolean_series(values: pd.Series) -> pd.Series:
    def coerce(value: Any) -> bool | pd.NA:
        if pd.isna(value) or value == "":
            return pd.NA
        if isinstance(value, bool):
            return value
        normalized = str(value).strip().lower()
        if normalized in {"1", "true", "yes", "y", "active"}:
            return True
        if normalized in {"0", "false", "no", "n", "inactive"}:
            return False
        raise ValueError(f"cannot coerce boolean value: {value}")

    return values.map(coerce).astype("boolean")
