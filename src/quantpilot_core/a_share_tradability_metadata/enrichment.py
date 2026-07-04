"""A-share tradability metadata normalization for existing execution paths."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any, Mapping, Sequence


@dataclass(frozen=True)
class FieldMetadata:
    provider: str
    fetched_at: str | None
    quality: str
    fallback_reason: str | None = None
    unavailable_reason: str | None = None
    approximation_used: bool = False
    derived_from_approximate_input: bool = False
    lineage: tuple[str, ...] = ()


@dataclass(frozen=True)
class SecurityMasterRecord:
    symbol: str
    exchange: str | None = None
    board: str | None = None
    listing_date: str | None = None
    delisting_status: str | None = None
    is_st: bool | None = None
    source: str = "fixture"
    effective_start: str = "0001-01-01"
    effective_end: str | None = None
    data_quality: str = "fixture"
    unavailable_reason: str | None = None


@dataclass(frozen=True)
class TradabilityOverrideRecord:
    trade_date: str
    symbol: str
    is_suspended: bool | None = None
    upper_limit: float | None = None
    lower_limit: float | None = None
    source: str = "fixture"
    data_quality: str = "fixture"
    unavailable_reason: str | None = None


@dataclass(frozen=True)
class CorporateActionRecord:
    symbol: str
    ex_date: str
    action_type: str
    cash_dividend: float | None = None
    split_ratio: float | None = None
    rights_issue: Mapping[str, Any] | None = None
    adjust_factor: float | None = None
    source: str = "fixture"
    data_quality: str = "fixture"


@dataclass(frozen=True)
class AShareTradabilityMetadataConfig:
    security_master_records: tuple[SecurityMasterRecord, ...] = ()
    tradability_overrides: tuple[TradabilityOverrideRecord, ...] = ()
    corporate_actions: tuple[CorporateActionRecord, ...] = ()
    fetched_at: str | None = None
    primary_price_provider: str = "baostock"
    infer_board_from_symbol_prefix: bool = True
    enabled: bool = True
    price_basis: Mapping[str, str] = field(
        default_factory=lambda: {
            "raw_or_unadjusted": "unadjusted_adjustment_none",
            "forward_adjusted": "unavailable",
            "backward_adjusted": "unavailable",
            "feature": "unadjusted_adjustment_none",
            "label": "unadjusted_adjustment_none",
            "benchmark": "unadjusted_adjustment_none",
            "execution": "unadjusted_adjustment_none",
        }
    )

    @classmethod
    def from_metadata(cls, metadata: Mapping[str, Any]) -> "AShareTradabilityMetadataConfig":
        raw = metadata.get("a_share_tradability_metadata", {})
        if not isinstance(raw, Mapping):
            raw = {}
        return cls(
            security_master_records=tuple(_security_record(row) for row in raw.get("security_master_records", ()) or ()),
            tradability_overrides=tuple(_tradability_record(row) for row in raw.get("tradability_overrides", ()) or ()),
            corporate_actions=tuple(_corporate_action_record(row) for row in raw.get("corporate_actions", ()) or ()),
            fetched_at=raw.get("fetched_at"),
            primary_price_provider=str(raw.get("primary_price_provider", "baostock")),
            infer_board_from_symbol_prefix=bool(raw.get("infer_board_from_symbol_prefix", True)),
            enabled=bool(raw.get("enabled", metadata.get("a_share_tradability_metadata_enrichment_v1", False))),
            price_basis=dict(raw.get("price_basis", {})) or cls().price_basis,
        )


def enrich_market_rows(
    rows: Mapping[str, Mapping[str, Any]],
    *,
    config: AShareTradabilityMetadataConfig,
) -> Mapping[str, Mapping[str, Any]]:
    if not config.enabled:
        return rows
    return {symbol: _enrich_row(symbol, dict(row), config) for symbol, row in rows.items()}


def _enrich_row(symbol: str, row: dict[str, Any], config: AShareTradabilityMetadataConfig) -> Mapping[str, Any]:
    trade_date = _date_str(row.get("date") or row.get("trade_date"))
    security = _security_as_of(config.security_master_records, symbol, trade_date)
    override = _tradability_override(config.tradability_overrides, symbol, trade_date)
    field_meta: dict[str, FieldMetadata] = {}

    exchange = _exchange_from_symbol(symbol)
    board = security.board if security and security.board else _board_from_symbol(symbol, trade_date, config)
    if security and security.exchange:
        exchange = security.exchange
    row["exchange"] = exchange
    row["board"] = board
    provider_is_st = _optional_bool(row.get("is_st"))
    provider_trade_status = row.get("trade_status") or row.get("tradestatus")
    row["listing_date"] = security.listing_date if security else None
    row["delisting_status"] = security.delisting_status if security else None
    row["is_st"] = security.is_st if security and security.is_st is not None else provider_is_st
    row["risk_flag"] = "st" if row["is_st"] is True else "normal" if row["is_st"] is False else None
    row["security_master_source"] = security.source if security else "symbol_prefix"

    field_meta["board_classification"] = _meta(
        security.source if security and security.board else "symbol_prefix",
        config,
        "high" if security and security.board else "derived",
        None if board else "board_unavailable",
        approximation_used=security is None and board is not None,
    )
    field_meta["historical_st_status"] = _meta(
        security.source if security and security.is_st is not None else config.primary_price_provider if provider_is_st is not None else "none",
        config,
        security.data_quality if security and security.is_st is not None else "provider_row" if provider_is_st is not None else "unavailable",
        None if (security and security.is_st is not None) or provider_is_st is not None else "historical_st_status_unavailable",
    )
    field_meta["delisting_status"] = _meta(
        security.source if security and security.delisting_status is not None else "none",
        config,
        security.data_quality if security and security.delisting_status is not None else "unavailable",
        None if security and security.delisting_status is not None else "delisting_status_unavailable",
    )

    if override and override.is_suspended is not None:
        row["is_suspended"] = bool(override.is_suspended)
        field_meta["suspension_status"] = _meta(override.source, config, override.data_quality)
    elif provider_trade_status is not None:
        row["is_suspended"] = str(provider_trade_status).strip() == "0"
        field_meta["suspension_status"] = _meta(config.primary_price_provider, config, "provider_row")
    elif "is_suspended" in row:
        field_meta["suspension_status"] = _meta(config.primary_price_provider, config, "provider_row")
    else:
        row["is_suspended"] = None
        field_meta["suspension_status"] = _meta("none", config, "unavailable", "suspension_status_unavailable")

    if override and override.upper_limit is not None and override.lower_limit is not None:
        row["upper_limit"] = float(override.upper_limit)
        row["lower_limit"] = float(override.lower_limit)
        field_meta["price_limit_fields"] = _meta(override.source, config, override.data_quality)
    else:
        _derive_price_limits(
            row,
            board=board,
            is_st=row["is_st"],
            config=config,
            field_meta=field_meta,
            board_approximation_used=field_meta["board_classification"].approximation_used,
        )

    high = _float(row.get("high"))
    low = _float(row.get("low"))
    close = _float(row.get("close"))
    upper = _float(row.get("upper_limit"))
    lower = _float(row.get("lower_limit"))
    row["one_price_upper_limit"] = bool(high > 0 and low > 0 and upper > 0 and abs(high - low) <= 1e-6 and close >= upper - 1e-6)
    row["one_price_lower_limit"] = bool(high > 0 and low > 0 and lower > 0 and abs(high - low) <= 1e-6 and close <= lower + 1e-6)
    field_meta["one_price_limit_state"] = _meta(
        field_meta["price_limit_fields"].provider,
        config,
        field_meta["price_limit_fields"].quality,
        field_meta["price_limit_fields"].unavailable_reason,
        approximation_used=field_meta["price_limit_fields"].approximation_used,
    )

    row["tradable"] = None if row.get("is_suspended") is None else not bool(row.get("is_suspended"))
    row["valid_ohlc"] = all(_float(row.get(key)) > 0 for key in ("open", "high", "low", "close"))
    row["available_volume"] = row.get("available_volume", row.get("volume"))
    field_meta["daily_volume"] = _meta(
        config.primary_price_provider if row.get("volume") is not None else "none",
        config,
        "provider_row" if row.get("volume") is not None else "unavailable",
        None if row.get("volume") is not None else "daily_volume_unavailable",
    )
    field_meta["order_side_volume_participation_input"] = _meta(
        "daily_volume",
        config,
        "approximation",
        fallback_reason="true_order_side_volume_participation_unavailable",
        approximation_used=True,
    )

    actions = _corporate_actions_as_of(config.corporate_actions, symbol, trade_date)
    row["corporate_actions"] = tuple(action.__dict__ for action in actions)
    row["price_basis_metadata"] = dict(config.price_basis)
    field_meta["corporate_action_fields"] = _meta(
        actions[0].source if actions else "none",
        config,
        actions[0].data_quality if actions else "unavailable",
        None if actions else "corporate_action_fields_unavailable",
    )
    field_meta["adjusted_unadjusted_price_basis"] = _meta(config.primary_price_provider, config, "explicit")

    row["tradability_metadata_fields"] = {name: meta.__dict__ for name, meta in sorted(field_meta.items())}
    row["tradability_metadata_source"] = "a_share_tradability_metadata_enrichment_v1"
    return row


def _derive_price_limits(
    row: dict[str, Any],
    *,
    board: str | None,
    is_st: bool | None,
    config: AShareTradabilityMetadataConfig,
    field_meta: dict[str, FieldMetadata],
    board_approximation_used: bool,
) -> None:
    if row.get("upper_limit") is not None and row.get("lower_limit") is not None:
        field_meta["price_limit_fields"] = _meta(
            config.primary_price_provider,
            config,
            "provider_row",
            lineage=("direct_provider_limits",),
        )
        return
    previous_close = _float(row.get("previous_close"))
    pct = _price_limit_pct(board, is_st)
    if previous_close > 0 and pct is not None and is_st is not None:
        row["upper_limit"] = round(previous_close * (1 + pct), 6)
        row["lower_limit"] = round(previous_close * (1 - pct), 6)
        field_meta["price_limit_fields"] = _meta(
            "point_in_time_board_st_regime",
            config,
            "derived_with_approximate_input" if board_approximation_used else "derived",
            fallback_reason="provider_explicit_price_limits_unavailable",
            approximation_used=board_approximation_used,
            derived_from_approximate_input=board_approximation_used,
            lineage=(
                "previous_close",
                "board_classification:symbol_prefix_approximation" if board_approximation_used else "board_classification:observed",
                "historical_st_status",
                "trade_date_regime",
            ),
        )
        return
    field_meta["price_limit_fields"] = _meta(
        "none",
        config,
        "unavailable",
        "price_limit_requires_previous_close_and_point_in_time_board_st_status",
    )


def _price_limit_pct(board: str | None, is_st: bool | None) -> float | None:
    if is_st is None:
        return None
    if is_st is True:
        return 0.05
    if board in {"star", "chinext"}:
        return 0.20
    if board in {"main", "sme"}:
        return 0.10
    return None


def _security_as_of(records: Sequence[SecurityMasterRecord], symbol: str, trade_date: str) -> SecurityMasterRecord | None:
    candidates = [
        record
        for record in records
        if record.symbol == symbol and _effective(record.effective_start, record.effective_end, trade_date)
    ]
    if not candidates:
        return None
    return sorted(candidates, key=lambda record: record.effective_start)[-1]


def _tradability_override(records: Sequence[TradabilityOverrideRecord], symbol: str, trade_date: str) -> TradabilityOverrideRecord | None:
    for record in records:
        if record.symbol == symbol and record.trade_date == trade_date:
            return record
    return None


def _corporate_actions_as_of(records: Sequence[CorporateActionRecord], symbol: str, trade_date: str) -> tuple[CorporateActionRecord, ...]:
    return tuple(record for record in records if record.symbol == symbol and record.ex_date <= trade_date)


def _effective(start: str, end: str | None, trade_date: str) -> bool:
    return str(start) <= trade_date and (end is None or trade_date <= str(end))


def _board_from_symbol(symbol: str, trade_date: str, config: AShareTradabilityMetadataConfig) -> str | None:
    if not config.infer_board_from_symbol_prefix:
        return None
    code = symbol.split(".")[0]
    if code.startswith("688") and trade_date >= "2019-07-22":
        return "star"
    if code.startswith("300") and trade_date >= "2020-08-24":
        return "chinext"
    if code.startswith("002"):
        return "sme"
    if code.startswith(("000", "001", "600", "601", "603", "605")):
        return "main"
    return None


def _exchange_from_symbol(symbol: str) -> str | None:
    if symbol.endswith(".SH"):
        return "SH"
    if symbol.endswith(".SZ"):
        return "SZ"
    return None


def _security_record(row: Any) -> SecurityMasterRecord:
    if isinstance(row, SecurityMasterRecord):
        return row
    return SecurityMasterRecord(**dict(row))


def _tradability_record(row: Any) -> TradabilityOverrideRecord:
    if isinstance(row, TradabilityOverrideRecord):
        return row
    return TradabilityOverrideRecord(**dict(row))


def _corporate_action_record(row: Any) -> CorporateActionRecord:
    if isinstance(row, CorporateActionRecord):
        return row
    return CorporateActionRecord(**dict(row))


def _meta(
    provider: str,
    config: AShareTradabilityMetadataConfig,
    quality: str,
    unavailable_reason: str | None = None,
    *,
    fallback_reason: str | None = None,
    approximation_used: bool = False,
    derived_from_approximate_input: bool = False,
    lineage: tuple[str, ...] = (),
) -> FieldMetadata:
    return FieldMetadata(
        provider=provider,
        fetched_at=config.fetched_at or datetime.utcnow().replace(microsecond=0).isoformat() + "Z",
        quality=quality,
        fallback_reason=fallback_reason,
        unavailable_reason=unavailable_reason,
        approximation_used=approximation_used,
        derived_from_approximate_input=derived_from_approximate_input,
        lineage=lineage,
    )


def _date_str(value: Any) -> str:
    if isinstance(value, datetime):
        return value.date().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    text = str(value)
    if " " in text:
        text = text.split(" ", 1)[0]
    if "T" in text:
        text = text.split("T", 1)[0]
    return text


def _float(value: Any) -> float:
    try:
        if value is None:
            return 0.0
        numeric = float(value)
        if numeric != numeric:
            return 0.0
        return numeric
    except (TypeError, ValueError):
        return 0.0


def _optional_bool(value: Any) -> bool | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    text = str(value).strip()
    if text in {"1", "true", "True", "TRUE"}:
        return True
    if text in {"0", "false", "False", "FALSE"}:
        return False
    return None
