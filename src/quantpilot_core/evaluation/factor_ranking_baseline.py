"""Offline factor-ranking baseline for explainable A-share candidate selection."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field, replace
from pathlib import Path
from typing import Any, Mapping, Sequence

import pandas as pd


FACTOR_RANKING_BASELINE_MODES = (
    "low_volatility_v1",
    "low_volatility_with_trend_filter",
    "low_volatility_with_liquidity_filter",
    "defensive_composite_v1",
    "momentum_reversal_guarded",
)
DEFAULT_FACTOR_RANKING_BASELINE_ARTIFACT_PATH = Path("artifacts/factor_ranking_baseline/latest_report.json")
FACTOR_COLUMNS = (
    "volatility_20d",
    "volatility_60d",
    "momentum_20d",
    "momentum_60d",
    "drawdown_20d",
    "drawdown_60d",
    "liquidity_proxy",
    "trend_filter",
)


@dataclass(frozen=True)
class FactorRankingBaselineConfig:
    """Configuration for deterministic offline factor ranking."""

    ranking_mode: str = "defensive_composite_v1"
    target_symbol_count: int = 10
    as_of_date: str | None = None
    normalization_method: str = "percentile"
    min_liquidity_percentile: float = 0.25
    max_drawdown_guard: float = -0.25
    artifact_path: str | Path | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class FactorScore:
    """Per-symbol factor score and evidence, JSON-serializable via asdict."""

    symbol: str
    as_of_date: str
    volatility_20d: float | None
    volatility_60d: float | None
    momentum_20d: float | None
    momentum_60d: float | None
    drawdown_20d: float | None
    drawdown_60d: float | None
    liquidity_proxy: float | None
    trend_filter: bool
    composite_score: float
    ranking_mode: str
    factor_evidence: Mapping[str, Any]


@dataclass(frozen=True)
class FactorRankingBaselineReport:
    """Explainable factor-ranking report for advisory review or ML export."""

    provider: str | None
    date_range: tuple[str, str] | None
    symbols_requested: tuple[str, ...] | None
    valid_symbols: tuple[str, ...] | None
    ranking_modes: tuple[str, ...]
    ranking_mode: str
    as_of_date: str
    normalization_method: str
    factor_scores: tuple[FactorScore, ...]
    selected_symbols: tuple[str, ...]
    rejected_symbols_with_reasons: tuple[Mapping[str, Any], ...]
    factor_contribution_summary: Mapping[str, Any]
    notes: tuple[str, ...]
    artifact_path: str | None = None


def run_factor_ranking_baseline_v1(
    price_frame: pd.DataFrame,
    config: FactorRankingBaselineConfig | None = None,
    **kwargs: Any,
) -> FactorRankingBaselineReport:
    """Rank symbols from an in-memory OHLCV frame without network, broker, or LLM calls."""

    payload = config or FactorRankingBaselineConfig(**kwargs)
    _validate_config(payload)
    normalized = _normalize_price_frame(price_frame)
    as_of_date = payload.as_of_date or _latest_date(normalized)
    point_in_time = normalized.loc[pd.to_datetime(normalized["date"]) <= pd.Timestamp(as_of_date)].copy()
    if point_in_time.empty:
        raise ValueError("price_frame has no rows on or before as_of_date")

    raw_rows = _compute_raw_factor_rows(point_in_time, as_of_date)
    normalized_rows = _normalize_factor_rows(raw_rows, payload.normalization_method)
    scored_rows = tuple(_score_factor_row(row, payload) for row in normalized_rows)
    ranked_rows = tuple(sorted(scored_rows, key=lambda row: (-row["composite_score"], row["symbol"])))
    valid_symbols = tuple(row["symbol"] for row in ranked_rows if not row.get("missing_factors"))
    selected = tuple(
        row["symbol"]
        for row in ranked_rows
        if not row["rejection_reasons"]
    )[: int(payload.target_symbol_count)]
    selected_set = set(selected)
    rejected = tuple(
        {
            "symbol": row["symbol"],
            "reasons": tuple(row["rejection_reasons"] or (["not_selected_lower_rank"] if row["symbol"] not in selected_set else [])),
            "composite_score": row["composite_score"],
        }
        for row in ranked_rows
        if row["symbol"] not in selected_set
    )
    factor_scores = tuple(_factor_score_from_row(row, payload.ranking_mode) for row in ranked_rows)
    metadata = _report_metadata(payload, normalized, ranked_rows, valid_symbols)
    report = FactorRankingBaselineReport(
        provider=metadata["provider"],
        date_range=metadata["date_range"],
        symbols_requested=metadata["symbols_requested"],
        valid_symbols=metadata["valid_symbols"],
        ranking_modes=metadata["ranking_modes"],
        ranking_mode=payload.ranking_mode,
        as_of_date=str(as_of_date),
        normalization_method=payload.normalization_method,
        factor_scores=factor_scores,
        selected_symbols=selected,
        rejected_symbols_with_reasons=rejected,
        factor_contribution_summary=_factor_contribution_summary(ranked_rows, selected_set),
        notes=_report_notes(payload),
    )
    artifact_path = _write_factor_ranking_report_artifact(report, payload.artifact_path)
    if artifact_path is not None:
        report = replace(report, artifact_path=artifact_path)
        _write_factor_ranking_report_artifact(report, artifact_path)
    return report


def _validate_config(config: FactorRankingBaselineConfig) -> None:
    if config.ranking_mode not in FACTOR_RANKING_BASELINE_MODES:
        raise ValueError(f"unsupported ranking_mode: {config.ranking_mode}")
    if int(config.target_symbol_count) <= 0:
        raise ValueError("target_symbol_count must be positive")
    if config.normalization_method not in {"percentile", "zscore"}:
        raise ValueError("normalization_method must be percentile or zscore")
    if not 0.0 <= float(config.min_liquidity_percentile) <= 1.0:
        raise ValueError("min_liquidity_percentile must be between 0 and 1")


def _report_metadata(
    config: FactorRankingBaselineConfig,
    frame: pd.DataFrame,
    rows: Sequence[Mapping[str, Any]],
    valid_symbols: tuple[str, ...],
) -> Mapping[str, Any]:
    metadata = dict(config.metadata)
    symbols_requested = metadata.get("symbols_requested")
    if symbols_requested is None:
        symbols_requested = tuple(sorted(str(symbol) for symbol in frame["symbol"].dropna().unique()))
    date_range = metadata.get("date_range")
    if date_range is None and not frame.empty:
        date_range = (str(pd.Timestamp(frame["date"].min()).date()), str(pd.Timestamp(frame["date"].max()).date()))
    ranking_modes = metadata.get("ranking_modes")
    if ranking_modes is None:
        ranking_modes = FACTOR_RANKING_BASELINE_MODES
    return {
        "provider": metadata.get("provider", "in_memory_fixture"),
        "date_range": tuple(date_range) if date_range is not None else None,
        "symbols_requested": tuple(str(symbol) for symbol in symbols_requested) if symbols_requested is not None else None,
        "valid_symbols": tuple(metadata.get("valid_symbols", valid_symbols)),
        "ranking_modes": tuple(str(mode) for mode in ranking_modes),
        "scored_symbols": tuple(row["symbol"] for row in rows),
    }


def _report_notes(config: FactorRankingBaselineConfig) -> tuple[str, ...]:
    run_context = str(config.metadata.get("run_context", "fixture"))
    notes = [
        "factor_ranking_baseline_v1",
        "no_broker_live_execution",
        "deepseek_live_disabled",
        "no_external_network_in_tests",
        "no_profitability_claim",
    ]
    if run_context == "manual_real_provider":
        notes.insert(1, "manual_only_real_provider_run")
    else:
        notes.insert(1, "offline_fixture_safe")
    extra_notes = tuple(str(note) for note in config.metadata.get("notes", ()))
    return tuple(dict.fromkeys((*notes, *extra_notes)))


def _normalize_price_frame(price_frame: pd.DataFrame) -> pd.DataFrame:
    if not isinstance(price_frame, pd.DataFrame):
        raise TypeError("price_frame must be a pandas DataFrame")
    required = {"date", "symbol", "close"}
    missing = required - set(price_frame.columns)
    if missing:
        raise ValueError(f"price_frame missing required columns: {sorted(missing)}")
    frame = price_frame.copy()
    frame["date"] = pd.to_datetime(frame["date"]).dt.tz_localize(None)
    frame["symbol"] = frame["symbol"].astype(str)
    frame["close"] = pd.to_numeric(frame["close"], errors="coerce")
    if "volume" in frame.columns:
        frame["volume"] = pd.to_numeric(frame["volume"], errors="coerce")
    else:
        frame["volume"] = 0.0
    if "amount" in frame.columns:
        frame["amount"] = pd.to_numeric(frame["amount"], errors="coerce")
    else:
        frame["amount"] = frame["close"] * frame["volume"]
    frame = frame.dropna(subset=["date", "symbol", "close"])
    frame = frame.loc[frame["close"] > 0].copy()
    return frame.sort_values(["date", "symbol"], kind="stable")


def _latest_date(frame: pd.DataFrame) -> str:
    if frame.empty:
        raise ValueError("price_frame must contain at least one valid row")
    return str(pd.Timestamp(frame["date"].max()).date())


def _compute_raw_factor_rows(frame: pd.DataFrame, as_of_date: str) -> tuple[dict[str, Any], ...]:
    rows: list[dict[str, Any]] = []
    for symbol, group in frame.sort_values(["date", "symbol"], kind="stable").groupby("symbol", sort=True):
        ordered = group.sort_values(["date", "symbol"], kind="stable")
        closes = ordered["close"].astype(float)
        returns = closes.pct_change().dropna()
        amount = ordered["amount"].fillna(ordered["close"] * ordered["volume"]).astype(float)
        row = {
            "symbol": str(symbol),
            "as_of_date": str(as_of_date),
            "volatility_20d": _volatility(returns.tail(20), min_count=5),
            "volatility_60d": _volatility(returns.tail(60), min_count=10),
            "momentum_20d": _momentum(closes.tail(21), min_count=6),
            "momentum_60d": _momentum(closes.tail(61), min_count=11),
            "drawdown_20d": _max_drawdown(closes.tail(20), min_count=5),
            "drawdown_60d": _max_drawdown(closes.tail(60), min_count=10),
            "liquidity_proxy": _liquidity(amount.tail(20)),
        }
        row["trend_filter"] = bool((row["momentum_20d"] or 0.0) > 0.0 and closes.iloc[-1] >= closes.tail(20).mean())
        row["missing_factors"] = tuple(key for key in FACTOR_COLUMNS if row.get(key) is None)
        rows.append(row)
    return tuple(rows)


def _volatility(returns: pd.Series, *, min_count: int) -> float | None:
    clean = returns.dropna()
    if len(clean) < min_count:
        return None
    return round(float(clean.std()), 12)


def _momentum(closes: pd.Series, *, min_count: int) -> float | None:
    clean = closes.dropna()
    if len(clean) < min_count:
        return None
    first = float(clean.iloc[0])
    if first <= 0:
        return None
    return round((float(clean.iloc[-1]) - first) / first, 12)


def _max_drawdown(closes: pd.Series, *, min_count: int) -> float | None:
    clean = closes.dropna()
    if len(clean) < min_count:
        return None
    running_max = clean.cummax()
    drawdowns = clean / running_max - 1.0
    return round(float(drawdowns.min()), 12)


def _liquidity(amount: pd.Series) -> float | None:
    clean = amount.dropna()
    if clean.empty:
        return None
    return round(float(clean.mean()), 6)


def _normalize_factor_rows(rows: Sequence[Mapping[str, Any]], method: str) -> tuple[dict[str, Any], ...]:
    output = [dict(row) for row in rows]
    for column in FACTOR_COLUMNS:
        values = {row["symbol"]: row.get(column) for row in output}
        if column == "trend_filter":
            normalized = {symbol: (1.0 if bool(value) else 0.0) for symbol, value in values.items()}
        elif method == "percentile":
            normalized = _percentile_normalize(values)
        else:
            normalized = _zscore_normalize(values)
        for row in output:
            row[f"{column}_normalized"] = normalized[row["symbol"]]
    return tuple(output)


def _percentile_normalize(values: Mapping[str, Any]) -> Mapping[str, float]:
    valid = sorted((float(value), symbol) for symbol, value in values.items() if value is not None and pd.notna(value))
    if not valid:
        return {symbol: 0.5 for symbol in values}
    if len(valid) == 1:
        result = {valid[0][1]: 0.5}
    else:
        result: dict[str, float] = {}
        index = 0
        while index < len(valid):
            value = valid[index][0]
            end = index
            while end + 1 < len(valid) and valid[end + 1][0] == value:
                end += 1
            percentile = ((index + end) / 2) / (len(valid) - 1)
            for _, symbol in valid[index : end + 1]:
                result[symbol] = percentile
            index = end + 1
    return {symbol: round(float(result.get(symbol, 0.5)), 6) for symbol in values}


def _zscore_normalize(values: Mapping[str, Any]) -> Mapping[str, float]:
    valid_values = [float(value) for value in values.values() if value is not None and pd.notna(value)]
    if len(valid_values) < 2:
        return {symbol: 0.5 for symbol in values}
    series = pd.Series(valid_values, dtype=float)
    std = float(series.std())
    if std == 0.0:
        return {symbol: 0.5 for symbol in values}
    mean = float(series.mean())
    result: dict[str, float] = {}
    for symbol, value in values.items():
        if value is None or pd.isna(value):
            result[symbol] = 0.5
            continue
        result[symbol] = round(1.0 / (1.0 + pow(2.718281828459045, -((float(value) - mean) / std))), 6)
    return result


def _score_factor_row(row: Mapping[str, Any], config: FactorRankingBaselineConfig) -> dict[str, Any]:
    scored = dict(row)
    contributions = _factor_contributions(row, config.ranking_mode)
    rejection_reasons = list(_rejection_reasons(row, config))
    missing_penalty = 0.02 * len(row.get("missing_factors", ()))
    score = max(0.0, min(1.0, sum(contributions.values()) - missing_penalty))
    scored["factor_contributions"] = {key: round(value, 6) for key, value in sorted(contributions.items())}
    scored["composite_score"] = round(score, 6)
    scored["rejection_reasons"] = tuple(rejection_reasons)
    return scored


def _factor_contributions(row: Mapping[str, Any], ranking_mode: str) -> Mapping[str, float]:
    low_vol_20 = 1.0 - float(row["volatility_20d_normalized"])
    low_vol_60 = 1.0 - float(row["volatility_60d_normalized"])
    drawdown_20_safety = float(row["drawdown_20d_normalized"])
    drawdown_60_safety = float(row["drawdown_60d_normalized"])
    liquidity = float(row["liquidity_proxy_normalized"])
    trend = float(row["trend_filter_normalized"])
    momentum_20 = float(row["momentum_20d_normalized"])
    momentum_60 = float(row["momentum_60d_normalized"])
    if ranking_mode in {"low_volatility_v1", "low_volatility_with_trend_filter", "low_volatility_with_liquidity_filter"}:
        return {"low_volatility_20d": 0.60 * low_vol_20, "low_volatility_60d": 0.40 * low_vol_60}
    if ranking_mode == "defensive_composite_v1":
        return {
            "low_volatility_20d": 0.25 * low_vol_20,
            "low_volatility_60d": 0.25 * low_vol_60,
            "drawdown_20d": 0.20 * drawdown_20_safety,
            "drawdown_60d": 0.15 * drawdown_60_safety,
            "liquidity_proxy": 0.10 * liquidity,
            "trend_filter": 0.05 * trend,
        }
    if ranking_mode == "momentum_reversal_guarded":
        return {
            "momentum_20d": 0.35 * momentum_20,
            "momentum_60d": 0.20 * momentum_60,
            "drawdown_60d_guard": 0.25 * drawdown_60_safety,
            "low_volatility_20d": 0.20 * low_vol_20,
        }
    raise ValueError(f"unsupported ranking_mode: {ranking_mode}")


def _rejection_reasons(row: Mapping[str, Any], config: FactorRankingBaselineConfig) -> tuple[str, ...]:
    reasons: list[str] = []
    if row.get("missing_factors"):
        reasons.append("missing_factor_data")
    if config.ranking_mode == "low_volatility_with_trend_filter" and not bool(row["trend_filter"]):
        reasons.append("trend_filter_failed")
    if (
        config.ranking_mode == "low_volatility_with_liquidity_filter"
        and float(row["liquidity_proxy_normalized"]) < float(config.min_liquidity_percentile)
    ):
        reasons.append("liquidity_filter_failed")
    if config.ranking_mode == "momentum_reversal_guarded":
        if (row.get("momentum_20d") or 0.0) <= 0.0:
            reasons.append("momentum_guard_failed")
        if row.get("drawdown_60d") is not None and float(row["drawdown_60d"]) < float(config.max_drawdown_guard):
            reasons.append("drawdown_guard_failed")
    return tuple(reasons)


def _factor_score_from_row(row: Mapping[str, Any], ranking_mode: str) -> FactorScore:
    evidence = {
        "normalized_factors": {
            column: row.get(f"{column}_normalized")
            for column in FACTOR_COLUMNS
        },
        "factor_contributions": row["factor_contributions"],
        "missing_factors": tuple(row.get("missing_factors", ())),
        "rejection_reasons": tuple(row.get("rejection_reasons", ())),
    }
    return FactorScore(
        symbol=str(row["symbol"]),
        as_of_date=str(row["as_of_date"]),
        volatility_20d=row.get("volatility_20d"),
        volatility_60d=row.get("volatility_60d"),
        momentum_20d=row.get("momentum_20d"),
        momentum_60d=row.get("momentum_60d"),
        drawdown_20d=row.get("drawdown_20d"),
        drawdown_60d=row.get("drawdown_60d"),
        liquidity_proxy=row.get("liquidity_proxy"),
        trend_filter=bool(row["trend_filter"]),
        composite_score=float(row["composite_score"]),
        ranking_mode=ranking_mode,
        factor_evidence=evidence,
    )


def _factor_contribution_summary(rows: Sequence[Mapping[str, Any]], selected_set: set[str]) -> Mapping[str, Any]:
    selected_rows = [row for row in rows if row["symbol"] in selected_set]
    if not selected_rows:
        return {"selected_count": 0, "average_contributions": {}, "missing_factor_count": 0}
    keys = sorted({key for row in selected_rows for key in row["factor_contributions"]})
    averages = {
        key: round(sum(float(row["factor_contributions"].get(key, 0.0)) for row in selected_rows) / len(selected_rows), 6)
        for key in keys
    }
    return {
        "selected_count": len(selected_rows),
        "average_contributions": averages,
        "missing_factor_count": sum(len(row.get("missing_factors", ())) for row in rows),
        "rejected_count": len(rows) - len(selected_rows),
    }


def _write_factor_ranking_report_artifact(
    report: FactorRankingBaselineReport,
    artifact_path: str | Path | None,
) -> str | None:
    if artifact_path is None:
        return None
    path = Path(artifact_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(_json_ready(asdict(report)), indent=2, sort_keys=True), encoding="utf-8")
    return str(path)


def _json_ready(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _json_ready(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return [_json_ready(item) for item in value]
    if isinstance(value, list):
        return [_json_ready(item) for item in value]
    return value
