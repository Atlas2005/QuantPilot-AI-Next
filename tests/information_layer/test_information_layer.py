from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from quantpilot_core.information_layer import (
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
    normalize_announcement_events_frame,
    normalize_concept_memberships_frame,
    normalize_dividend_records_frame,
    normalize_fund_holdings_frame,
    normalize_macro_policy_events_frame,
    normalize_margin_trading_snapshots_frame,
    normalize_moneyflow_snapshots_frame,
    normalize_news_events_frame,
    normalize_northbound_holdings_frame,
    normalize_shareholder_snapshots_frame,
    normalize_social_sentiment_events_frame,
    normalize_stabilization_flow_clues_frame,
    normalize_valuation_snapshots_frame,
)
from quantpilot_core.tool_registry import ToolSideEffectLevel, build_default_tool_registry


INFO_LAYER_CASES = (
    (
        "normalize_news_events_frame",
        normalize_news_events_frame,
        NEWS_EVENTS_COLUMNS,
        {
            "publish_time": ["2026-01-02 09:30:01"],
            "code": ["sz.000001"],
            "source": ["exchange-feed"],
            "vendor": ["fixture-provider"],
            "title": ["Board update"],
            "abstract": ["Short summary"],
            "link": ["local-fixture"],
            "snippet": ["Evidence sentence"],
            "sentiment": ["0.2"],
            "importance": ["0.7"],
        },
    ),
    (
        "normalize_macro_policy_events_frame",
        normalize_macro_policy_events_frame,
        MACRO_POLICY_EVENTS_COLUMNS,
        {
            "publish_date": ["2026-01-02"],
            "source_name": ["policy-calendar"],
            "provider": ["fixture-provider"],
            "area": ["liquidity"],
            "type": ["guidance"],
            "headline": ["Policy note"],
            "evidence": ["Evidence sentence"],
            "direction": ["supportive"],
            "importance": [0.8],
        },
    ),
    (
        "normalize_social_sentiment_events_frame",
        normalize_social_sentiment_events_frame,
        SOCIAL_SENTIMENT_EVENTS_COLUMNS,
        {
            "timestamp": ["2026-01-02 10:00:00"],
            "ts_code": ["000001.SZ"],
            "source": ["social-fixture"],
            "provider": ["fixture-provider"],
            "source_platform": ["forum"],
            "keyword": ["bank reform"],
            "raw_text": ["Evidence sentence"],
            "sentiment": [0.1],
            "mentions": [12],
        },
    ),
    (
        "normalize_northbound_holdings_frame",
        normalize_northbound_holdings_frame,
        NORTHBOUND_HOLDINGS_COLUMNS,
        {
            "trade_date": ["20260102"],
            "instrument": ["000001.SZ"],
            "source": ["northbound-fixture"],
            "provider": ["fixture-provider"],
            "shares": [1000],
            "value": [12000],
            "ratio": [0.03],
            "net_buy": [800],
            "evidence_text": ["Evidence sentence"],
        },
    ),
    (
        "normalize_stabilization_flow_clues_frame",
        normalize_stabilization_flow_clues_frame,
        STABILIZATION_FLOW_CLUES_COLUMNS,
        {
            "date": ["2026-01-02"],
            "symbol": ["000001.SZ"],
            "source": ["stabilization-fixture"],
            "provider": ["fixture-provider"],
            "vehicle": ["broad-etf"],
            "amount": [5000],
            "direction": ["inflow"],
            "evidence_text": ["Evidence sentence"],
            "confidence": [0.6],
        },
    ),
    (
        "normalize_fund_holdings_frame",
        normalize_fund_holdings_frame,
        FUND_HOLDINGS_COLUMNS,
        {
            "report_date": ["2026-01-02"],
            "symbol": ["000001.SZ"],
            "source": ["fund-report"],
            "provider": ["fixture-provider"],
            "fund_id": ["F001"],
            "fund": ["Fixture Fund"],
            "shares": [100],
            "value": [1200],
            "weight": [0.05],
            "snippet": ["Evidence sentence"],
        },
    ),
    (
        "normalize_shareholder_snapshots_frame",
        normalize_shareholder_snapshots_frame,
        SHAREHOLDER_SNAPSHOTS_COLUMNS,
        {
            "date": ["2026-01-02"],
            "code": ["sz.000001"],
            "source": ["holder-report"],
            "provider": ["fixture-provider"],
            "holder_name": ["Fixture Holder"],
            "shares": [100],
            "ratio": [0.01],
            "rank": [1],
            "evidence": ["Evidence sentence"],
        },
    ),
    (
        "normalize_dividend_records_frame",
        normalize_dividend_records_frame,
        DIVIDEND_RECORDS_COLUMNS,
        {
            "date": ["2026-01-02"],
            "symbol": ["000001.SZ"],
            "source": ["dividend-report"],
            "provider": ["fixture-provider"],
            "cash_dividend": [0.1],
            "stock_dividend": [0.0],
            "record_date": ["2026-01-05"],
            "ex_date": ["2026-01-06"],
            "content": ["Evidence sentence"],
        },
    ),
    (
        "normalize_valuation_snapshots_frame",
        normalize_valuation_snapshots_frame,
        VALUATION_SNAPSHOTS_COLUMNS,
        {
            "date": ["2026-01-02"],
            "symbol": ["000001.SZ"],
            "source": ["valuation-fixture"],
            "provider": ["fixture-provider"],
            "pe": [8.2],
            "pb": [0.9],
            "ps": [1.1],
            "total_market_value": [100000],
            "evidence_text": ["Evidence sentence"],
        },
    ),
    (
        "normalize_concept_memberships_frame",
        normalize_concept_memberships_frame,
        CONCEPT_MEMBERSHIPS_COLUMNS,
        {
            "date": ["2026-01-02"],
            "symbol": ["000001.SZ"],
            "source": ["theme-map"],
            "provider": ["fixture-provider"],
            "theme": ["banking"],
            "weight": [0.4],
            "active": ["true"],
            "evidence_text": ["Evidence sentence"],
        },
    ),
    (
        "normalize_margin_trading_snapshots_frame",
        normalize_margin_trading_snapshots_frame,
        MARGIN_TRADING_SNAPSHOTS_COLUMNS,
        {
            "trade_date": ["20260102"],
            "symbol": ["000001.SZ"],
            "source": ["margin-fixture"],
            "provider": ["fixture-provider"],
            "margin_balance": [10000],
            "short_balance": [200],
            "financing_buy": [300],
            "repayment": [100],
            "evidence_text": ["Evidence sentence"],
        },
    ),
    (
        "normalize_moneyflow_snapshots_frame",
        normalize_moneyflow_snapshots_frame,
        MONEYFLOW_SNAPSHOTS_COLUMNS,
        {
            "date": ["2026-01-02"],
            "symbol": ["000001.SZ"],
            "source": ["moneyflow-fixture"],
            "provider": ["fixture-provider"],
            "main_inflow": [1000],
            "large_inflow": [600],
            "retail_inflow": [-200],
            "turnover": [0.04],
            "evidence_text": ["Evidence sentence"],
        },
    ),
    (
        "normalize_announcement_events_frame",
        normalize_announcement_events_frame,
        ANNOUNCEMENT_EVENTS_COLUMNS,
        {
            "publish_time": ["2026-01-02 15:01:00"],
            "symbol": ["000001.SZ"],
            "source": ["announcement-feed"],
            "provider": ["fixture-provider"],
            "type": ["earnings"],
            "headline": ["Announcement title"],
            "link": ["local-fixture"],
            "snippet": ["Evidence sentence"],
            "importance": [0.9],
        },
    ),
)


@pytest.mark.parametrize(("tool_name", "normalizer", "columns", "fixture"), INFO_LAYER_CASES)
def test_information_layer_normalizers_emit_contract_columns(
    tool_name: str,
    normalizer,
    columns: tuple[str, ...],
    fixture: dict[str, list[object]],
) -> None:
    normalized = normalizer(pd.DataFrame(fixture))

    assert tuple(normalized.columns) == columns
    assert len(normalized) == 1
    assert normalized.loc[0, "source"]
    assert normalized.loc[0, "provider"] == "fixture-provider"
    assert normalized.loc[0, "evidence_text"] == "Evidence sentence"
    if "symbol" in normalized.columns:
        assert normalized.loc[0, "symbol"] == "000001.SZ"
    if "date" in normalized.columns:
        assert normalized.loc[0, "date"] == "2026-01-02"
    if "datetime" in normalized.columns:
        assert normalized.loc[0, "datetime"].startswith("2026-01-02T")
    assert tool_name.startswith("normalize_")


def test_information_layer_requires_pandas_frame_and_required_evidence() -> None:
    with pytest.raises(TypeError, match="pandas DataFrame"):
        normalize_news_events_frame(frame=[])

    with pytest.raises(ValueError, match="symbol must not contain missing values"):
        normalize_news_events_frame(
            pd.DataFrame(
                {
                    "datetime": ["2026-01-02 09:30:00"],
                    "symbol": [None],
                    "source": ["fixture"],
                    "provider": ["fixture-provider"],
                    "evidence_text": ["Evidence sentence"],
                }
            )
        )

    with pytest.raises(ValueError, match="missing required columns: evidence_text"):
        normalize_news_events_frame(
            pd.DataFrame(
                {
                    "datetime": ["2026-01-02 09:30:00"],
                    "symbol": ["000001.SZ"],
                    "source": ["fixture"],
                    "provider": ["fixture-provider"],
                }
            )
        )


def test_information_layer_tools_are_listed_and_execute_through_registry() -> None:
    registry = build_default_tool_registry()
    names = registry.list_names()

    for tool_name, _, _, fixture in INFO_LAYER_CASES:
        assert tool_name in names
        tool = registry.get(tool_name)
        assert tool.side_effect_level is ToolSideEffectLevel.PURE_IN_MEMORY

        result = registry.execute(tool_name, frame=pd.DataFrame(fixture))

        assert result.ok is True
        assert isinstance(result.output, pd.DataFrame)
        assert result.side_effect_level is ToolSideEffectLevel.PURE_IN_MEMORY


def test_information_layer_has_no_forbidden_runtime_scope() -> None:
    package_root = Path(__file__).parents[2] / "src" / "quantpilot_core" / "information_layer"
    source = "\n".join(path.read_text() for path in package_root.glob("*.py")).lower()

    forbidden_terms = (
        "requests",
        "urllib",
        "http",
        "socket",
        "token",
        "api_key",
        "broker",
        "live",
        "qrun",
        "deepseek",
    )
    assert all(term not in source for term in forbidden_terms)
