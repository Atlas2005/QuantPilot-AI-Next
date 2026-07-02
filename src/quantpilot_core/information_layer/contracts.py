"""Normalized schema contracts for the A-share information layer."""

from __future__ import annotations


NEWS_EVENTS_COLUMNS = (
    "datetime",
    "symbol",
    "source",
    "provider",
    "headline",
    "summary",
    "url",
    "evidence_text",
    "sentiment_score",
    "importance_score",
)

MACRO_POLICY_EVENTS_COLUMNS = (
    "date",
    "source",
    "provider",
    "policy_area",
    "event_type",
    "title",
    "evidence_text",
    "impact_direction",
    "importance_score",
)

SOCIAL_SENTIMENT_EVENTS_COLUMNS = (
    "datetime",
    "symbol",
    "source",
    "provider",
    "platform",
    "topic",
    "evidence_text",
    "sentiment_score",
    "mention_count",
)

NORTHBOUND_HOLDINGS_COLUMNS = (
    "date",
    "symbol",
    "source",
    "provider",
    "holding_shares",
    "holding_value",
    "holding_ratio",
    "net_buy_value",
    "evidence_text",
)

STABILIZATION_FLOW_CLUES_COLUMNS = (
    "date",
    "symbol",
    "source",
    "provider",
    "vehicle_type",
    "flow_value",
    "flow_direction",
    "evidence_text",
    "confidence_score",
)

FUND_HOLDINGS_COLUMNS = (
    "date",
    "symbol",
    "source",
    "provider",
    "fund_code",
    "fund_name",
    "holding_shares",
    "holding_value",
    "portfolio_weight",
    "evidence_text",
)

SHAREHOLDER_SNAPSHOTS_COLUMNS = (
    "date",
    "symbol",
    "source",
    "provider",
    "shareholder_name",
    "holding_shares",
    "holding_ratio",
    "shareholder_rank",
    "evidence_text",
)

DIVIDEND_RECORDS_COLUMNS = (
    "date",
    "symbol",
    "source",
    "provider",
    "cash_dividend_per_share",
    "stock_dividend_ratio",
    "record_date",
    "ex_dividend_date",
    "evidence_text",
)

VALUATION_SNAPSHOTS_COLUMNS = (
    "date",
    "symbol",
    "source",
    "provider",
    "pe_ttm",
    "pb",
    "ps_ttm",
    "market_cap",
    "evidence_text",
)

CONCEPT_MEMBERSHIPS_COLUMNS = (
    "date",
    "symbol",
    "source",
    "provider",
    "concept_name",
    "membership_weight",
    "is_active",
    "evidence_text",
)

MARGIN_TRADING_SNAPSHOTS_COLUMNS = (
    "date",
    "symbol",
    "source",
    "provider",
    "financing_balance",
    "securities_lending_balance",
    "financing_buy_value",
    "repayment_value",
    "evidence_text",
)

MONEYFLOW_SNAPSHOTS_COLUMNS = (
    "date",
    "symbol",
    "source",
    "provider",
    "main_net_inflow",
    "large_net_inflow",
    "retail_net_inflow",
    "turnover_rate",
    "evidence_text",
)

ANNOUNCEMENT_EVENTS_COLUMNS = (
    "datetime",
    "symbol",
    "source",
    "provider",
    "announcement_type",
    "title",
    "url",
    "evidence_text",
    "importance_score",
)

