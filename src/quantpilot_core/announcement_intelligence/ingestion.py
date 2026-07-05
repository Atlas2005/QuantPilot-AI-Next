"""A-share announcement ingestion and point-in-time normalization."""

from __future__ import annotations

import hashlib
import importlib
import json
import re
from datetime import timedelta
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

import pandas as pd

from quantpilot_core.announcement_intelligence.contracts import ANNOUNCEMENT_EVENT_COLUMNS
from quantpilot_core.data_provider_normalization import canonicalize_a_share_symbol


MARKET_CLOSE_HOUR = 15
DEFAULT_CONTENT_CACHE_DIR = Path(".cache/quantpilot_announcement_content")
DEFAULT_MAX_INPUT_CHARS = 6000
MAX_DETAIL_RESPONSE_BYTES = 2_000_000
CONTENT_CACHE_SCHEMA_VERSION = "announcement_content_cache_v2"
CONTENT_CLASSIFIER_VERSION = "announcement_body_quality_v1"
BODY_SOURCE_VALUES = {"full_text", "provider_summary", "title_fallback", "unavailable"}
AKSHARE_ANNOUNCEMENT_COLUMN_ALIASES: Mapping[str, tuple[str, ...]] = {
    "代码": ("代码", "股票代码", "stock_code", "security_code", "code", "symbol"),
    "名称": ("名称", "股票简称", "short_name", "name"),
    "公告标题": ("公告标题", "title", "notice_title", "headline"),
    "公告类型": ("公告类型", "announcement_type", "announcement_category", "column_name", "type"),
    "公告日期": ("公告日期", "notice_date", "publish_time", "publish_date", "date", "datetime"),
    "网址": ("网址", "source_url", "url", "link", "detail_url"),
}
AKSHARE_REQUIRED_ANNOUNCEMENT_COLUMNS = ("代码", "公告标题", "公告日期")
MAX_PROVIDER_DIAGNOSTIC_COLUMNS = 24
BODY_LIKE_PUNCTUATION = ("。", "；", "，", ".", ";", ",")
BOILERPLATE_TERMS = (
    "返回首页",
    "免责声明",
    "广告",
    "客户端下载",
    "分享到",
    "打印",
    "关闭",
    "PDF原文",
    "查看PDF原文",
    "点击查看PDF原文",
    "郑重声明",
    "东方财富",
    "数据中心",
    "行情中心",
    "财经 焦点 股票",
    "Choice数据",
    "妙想大模型",
    "龙虎榜单",
    "融资融券",
    "条件选股",
    "个股公告查询",
    "公告正文",
    "全球财经快讯",
    "重要股东股权质押数据全览",
    "点击查看",
    "更多公告",
    "公告日期",
    "共 页",
    "上一页",
    "下一页",
    "扫一扫下载APP",
    "版权所有",
    "ICP备",
    "沪公网安备",
    "联系我们",
    "法律声明",
    "隐私保护",
    "友情链接",
    "关注",
    "更多>>",
    "更多＞＞",
    "股吧",
    "博客",
    "搜索",
    "登录",
    "注册",
)


def fetch_akshare_announcement_events(
    *,
    symbols: Sequence[str],
    start_date: str,
    end_date: str,
    akshare_client: Any | None = None,
    enrich_content: bool = True,
    content_cache_dir: str | Path = DEFAULT_CONTENT_CACHE_DIR,
    max_input_chars: int = DEFAULT_MAX_INPUT_CHARS,
) -> pd.DataFrame:
    """Fetch A-share announcements through optional AkShare in manual mode."""

    client = akshare_client or importlib.import_module("ak" + "share")
    requested = {canonicalize_a_share_symbol(symbol) for symbol in symbols}
    rows: list[Mapping[str, Any]] = []
    errors: list[Mapping[str, Any]] = []
    request_count = 0
    successful = 0
    failed = 0
    empty = 0
    raw_rows = 0
    matched_rows = 0
    symbol_statuses: list[Mapping[str, Any]] = []
    if not hasattr(client, "stock_individual_notice_report"):
        raise RuntimeError("AkShare client must expose stock_individual_notice_report for announcement ingestion")
    for symbol in tuple(symbols):
        canonical = canonicalize_a_share_symbol(symbol)
        bare_code = canonical.split(".", 1)[0]
        request_count += 1
        try:
            raw = client.stock_individual_notice_report(
                security=bare_code,
                symbol="全部",
                begin_date=pd.Timestamp(start_date).strftime("%Y%m%d"),
                end_date=pd.Timestamp(end_date).strftime("%Y%m%d"),
            )
        except Exception as exc:
            if _is_akshare_empty_result_keyerror(exc):
                successful += 1
                empty += 1
                symbol_statuses.append(
                    {
                        "symbol": canonical,
                        "request_symbol": bare_code,
                        "status": "empty",
                        "reason": "provider_empty_response",
                        "raw_row_count": 0,
                        "matched_row_count": 0,
                        "diagnostic": "akshare_empty_result_keyerror_code_column",
                    }
                )
                continue
            failed += 1
            symbol_statuses.append(
                {
                    "symbol": canonical,
                    "request_symbol": bare_code,
                    "status": "failed",
                    "reason": "provider_connection_error",
                    "raw_row_count": 0,
                    "matched_row_count": 0,
                }
            )
            errors.append(
                {
                    "symbol": canonical,
                    "exception_type": type(exc).__name__,
                    "exception_message": str(exc),
                    "retry_count": 0,
                }
            )
            continue
        frame = raw if isinstance(raw, pd.DataFrame) else pd.DataFrame(raw)
        successful += 1
        if frame.empty:
            empty += 1
            symbol_statuses.append(
                {
                    "symbol": canonical,
                    "request_symbol": bare_code,
                    "status": "empty",
                    "reason": "provider_empty_response",
                    "raw_row_count": 0,
                    "matched_row_count": 0,
                }
            )
            continue
        frame, schema_error = _normalize_akshare_announcement_schema(frame)
        if schema_error:
            failed += 1
            symbol_statuses.append(
                {
                    "symbol": canonical,
                    "request_symbol": bare_code,
                    "status": "failed",
                    "reason": "provider_schema_error",
                    "raw_row_count": len(frame),
                    "matched_row_count": 0,
                    "observed_columns": schema_error["observed_columns"],
                    "missing_semantic_fields": schema_error["missing_semantic_fields"],
                }
            )
            errors.append(
                {
                    "symbol": canonical,
                    "exception_type": "ProviderSchemaError",
                    "exception_message": "missing required announcement provider fields",
                    "observed_columns": schema_error["observed_columns"],
                    "missing_semantic_fields": schema_error["missing_semantic_fields"],
                    "retry_count": 0,
                }
            )
            continue
        raw_rows += len(frame)
        raw_row_count = len(frame)
        symbol_column = _first_existing_column(frame, AKSHARE_ANNOUNCEMENT_COLUMN_ALIASES["代码"])
        if symbol_column is not None:
            normalized_symbols = frame[symbol_column].map(canonicalize_a_share_symbol)
            frame = frame.loc[normalized_symbols.isin(requested)].copy()
            frame["symbol"] = normalized_symbols.loc[frame.index]
        else:
            frame = frame.copy()
            frame["symbol"] = canonical
        frame = frame.loc[frame["symbol"] == canonical].copy()
        matched_rows += len(frame)
        if frame.empty:
            symbol_statuses.append(
                {
                    "symbol": canonical,
                    "request_symbol": bare_code,
                    "status": "empty",
                    "reason": "requested_symbol_not_present",
                    "raw_row_count": raw_row_count,
                    "matched_row_count": 0,
                }
            )
            continue
        symbol_statuses.append(
            {
                "symbol": canonical,
                "request_symbol": bare_code,
                "status": "matched",
                "reason": "provider_rows_matched",
                "raw_row_count": raw_row_count,
                "matched_row_count": len(frame),
            }
        )
        frame["source"] = "akshare_eastmoney_individual_announcements"
        frame["provider_request_symbol"] = canonical
        rows.extend(frame.to_dict("records"))
    if not rows:
        empty_events = pd.DataFrame(columns=ANNOUNCEMENT_EVENT_COLUMNS)
        empty_events.attrs["run_report"] = _ingestion_report(
            start_date=start_date,
            end_date=end_date,
            requested_symbol_count=len(requested),
            request_count=request_count,
            successful_request_count=successful,
            failed_request_count=failed,
            empty_response_count=empty,
            raw_row_count=raw_rows,
            matched_row_count=matched_rows,
            normalized_event_count=0,
            deduplicated_event_count=0,
            symbol_coverage_count=0,
            errors=tuple(errors),
            symbol_request_statuses=tuple(symbol_statuses),
        )
        return empty_events
    normalized = normalize_a_share_announcement_events(pd.DataFrame(rows), ingestion_time=pd.Timestamp.utcnow().isoformat())
    if enrich_content:
        normalized = enrich_announcement_content(
            normalized,
            detail_client=client,
            cache_dir=content_cache_dir,
            max_input_chars=max_input_chars,
        )
    publish = pd.to_datetime(normalized["publish_time"])
    start = pd.Timestamp(start_date)
    end = pd.Timestamp(end_date) + pd.Timedelta(days=1)
    filtered = normalized.loc[(publish >= start) & (publish < end)].reset_index(drop=True)
    coverage = _symbol_coverage_count(filtered)
    filtered.attrs["run_report"] = _ingestion_report(
        start_date=start_date,
        end_date=end_date,
        requested_symbol_count=len(requested),
        request_count=request_count,
        successful_request_count=successful,
        failed_request_count=failed,
        empty_response_count=empty,
        raw_row_count=raw_rows,
        matched_row_count=matched_rows,
        normalized_event_count=len(filtered),
        deduplicated_event_count=len(filtered),
        symbol_coverage_count=coverage,
        errors=tuple(errors),
        symbol_request_statuses=tuple(symbol_statuses),
    )
    return filtered


def write_announcement_ingestion_artifacts(
    events: pd.DataFrame,
    *,
    events_artifact_path: str | Path,
    report_artifact_path: str | Path,
) -> Mapping[str, Any]:
    """Write canonical event-list and run-report artifacts."""

    events_path = Path(events_artifact_path)
    report_path = Path(report_artifact_path)
    events_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    events_path.write_text(events.to_json(orient="records", force_ascii=False, indent=2), encoding="utf-8")
    report = dict(events.attrs.get("run_report") or {})
    report["events_artifact_path"] = str(events_path)
    report_path.write_text(json.dumps(report, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8")
    return report


def _first_existing_column(frame: pd.DataFrame, candidates: Sequence[str]) -> str | None:
    for candidate in candidates:
        if candidate in frame.columns:
            return candidate
    return None


def _normalize_akshare_announcement_schema(frame: pd.DataFrame) -> tuple[pd.DataFrame, Mapping[str, Any] | None]:
    observed = tuple(str(column) for column in frame.columns[:MAX_PROVIDER_DIAGNOSTIC_COLUMNS])
    semantic_columns: dict[str, str] = {}
    for target, aliases in AKSHARE_ANNOUNCEMENT_COLUMN_ALIASES.items():
        match = _first_existing_column(frame, aliases)
        if match is not None:
            semantic_columns[target] = match
    missing = tuple(column for column in AKSHARE_REQUIRED_ANNOUNCEMENT_COLUMNS if column not in semantic_columns)
    if missing:
        return frame.copy(), {
            "observed_columns": observed,
            "missing_semantic_fields": missing,
        }
    normalized = frame.copy()
    for target, source in semantic_columns.items():
        if target not in normalized.columns:
            normalized[target] = normalized[source]
    return normalized, None


def _is_akshare_empty_result_keyerror(exc: Exception) -> bool:
    return isinstance(exc, KeyError) and tuple(exc.args) == ("代码",)


def normalize_a_share_announcement_events(
    frame: pd.DataFrame,
    *,
    ingestion_time: str | None = None,
    trading_calendar: Sequence[str] | None = None,
) -> pd.DataFrame:
    """Normalize provider rows into strict point-in-time announcement event rows."""

    if not isinstance(frame, pd.DataFrame):
        raise TypeError("announcement frame must be a pandas DataFrame")
    if frame.empty:
        return pd.DataFrame(columns=ANNOUNCEMENT_EVENT_COLUMNS)

    now = ingestion_time or pd.Timestamp.utcnow().isoformat()
    rows: list[dict[str, Any]] = []
    seen: set[str] = set()
    for raw in frame.to_dict("records"):
        title = _first(raw, "title", "headline", "公告标题", "notice_title", default="")
        content = _first(raw, "content", "summary", "evidence_text", "公告内容", "snippet", default=title)
        publish_raw = _first(raw, "publish_time", "datetime", "公告日期", "date", "publish_date", default=None)
        precision = _publish_time_precision(publish_raw)
        publish_time = pd.Timestamp(publish_raw).tz_localize(None) if publish_raw is not None else pd.Timestamp(now).tz_localize(None)
        symbols = _symbols(raw)
        source = str(_first(raw, "source", "provider", default="akshare_announcement"))
        source_url = str(_first(raw, "source_url", "url", "link", "网址", default=""))
        identifier = str(_first(raw, "source_identifier", "id", "公告代码", default="")) or _identifier_from_url(source_url)
        category = str(_first(raw, "announcement_category", "announcement_type", "公告类型", "type", default="other"))
        initial_source = _content_source_from_raw(raw, str(title), str(content))
        classification = _classify_announcement_body(str(title), str(content), declared_source=initial_source)
        content_source = str(classification["content_source"])
        content_payload = _bounded_announcement_content(
            str(title),
            str(classification["retained_text"] or title),
            max_input_chars=DEFAULT_MAX_INPUT_CHARS,
        )
        content_hash = _content_hash(content_payload)
        payload = f"{title}|{content_payload}|{publish_time.isoformat()}|{','.join(symbols)}|{identifier}"
        raw_hash = hashlib.sha256(payload.encode("utf-8")).hexdigest()
        dedupe = hashlib.sha256(f"{publish_time.date()}|{','.join(symbols)}|{title}|{identifier}".encode("utf-8")).hexdigest()
        if dedupe in seen:
            continue
        seen.add(dedupe)
        first_available, derivation = _first_available_time(publish_time, precision, trading_calendar)
        flags = _quality_flags(raw, title, content, symbols, publish_raw)
        if precision == "date":
            flags.add("publish_intraday_time_unavailable")
        rows.append(
            {
                "event_id": f"ann_{raw_hash[:16]}",
                "source": source,
                "source_type": "announcement",
                "title": str(title),
                "content": content_payload,
                "announcement_category": category,
                "provider_announcement_category": category,
                "content_source": content_source,
                "content_quality_status": classification["content_quality_status"],
                "content_quality_reason": classification["content_quality_reason"],
                "content_quality_evidence": classification["content_quality_evidence"],
                "content_char_count": len(content_payload),
                "content_retrieval_status": "not_requested",
                "content_retrieval_error": "",
                "full_text_available": content_source == "full_text" and classification["content_quality_status"] == "usable_full_text",
                "content_hash": content_hash,
                "content_cache_key": "",
                "content_cache_schema_version": "",
                "content_classifier_version": CONTENT_CLASSIFIER_VERSION,
                "content_truncated": len(_normalize_announcement_text(f"{title}\n{classification['retained_text']}")) > DEFAULT_MAX_INPUT_CHARS,
                "max_input_chars": DEFAULT_MAX_INPUT_CHARS,
                "publish_time": publish_time.isoformat(),
                "publish_time_precision": precision,
                "first_available_time": first_available.isoformat(),
                "first_available_time_derivation": derivation,
                "ingestion_time": pd.Timestamp(now).tz_localize(None).isoformat(),
                "affected_symbols": tuple(symbols),
                "affected_industries": _tuple_field(raw, "affected_industries", "industry"),
                "affected_concepts": _tuple_field(raw, "affected_concepts", "concept", "concepts"),
                "source_url": source_url,
                "source_identifier": identifier,
                "raw_content_hash": raw_hash,
                "deduplication_key": dedupe,
                "lineage_observed": ("title", "publish_time", "publish_time_precision", "affected_symbols"),
                "lineage_derived": ("event_id", "raw_content_hash", "deduplication_key", "first_available_time"),
                "lineage_approximated": ("content",) if content_source == "title_fallback" else (),
                "lineage_unavailable": tuple(sorted(flags)),
                "data_quality_flags": tuple(sorted(flags)),
            }
        )
    return pd.DataFrame(rows, columns=ANNOUNCEMENT_EVENT_COLUMNS).sort_values(
        ["first_available_time", "event_id"], kind="stable"
    ).reset_index(drop=True)


def enrich_announcement_content(
    events: pd.DataFrame,
    *,
    detail_client: Any | None = None,
    detail_fetcher: Callable[[Mapping[str, Any]], Mapping[str, Any] | str | None] | None = None,
    cache_dir: str | Path = DEFAULT_CONTENT_CACHE_DIR,
    max_input_chars: int = DEFAULT_MAX_INPUT_CHARS,
) -> pd.DataFrame:
    """Fetch bounded announcement detail text without letting one failure stop the run."""

    if events.empty:
        return events.copy()
    frame = events.copy()
    cache_path = Path(cache_dir)
    for index, event in frame.iterrows():
        raw_event = event.to_dict()
        key = _content_cache_key(raw_event, max_input_chars)
        path = cache_path / f"{key}.json"
        try:
            if path.exists():
                detail = json.loads(path.read_text(encoding="utf-8"))
                status = "cache_hit"
                error = ""
            else:
                detail = _retrieve_detail(raw_event, detail_client=detail_client, detail_fetcher=detail_fetcher)
                status = "retrieved"
                error = ""
                cache_path.mkdir(parents=True, exist_ok=True)
                cache_payload = {
                    **dict(detail),
                    "content_cache_schema_version": CONTENT_CACHE_SCHEMA_VERSION,
                    "content_classifier_version": CONTENT_CLASSIFIER_VERSION,
                }
                path.write_text(json.dumps(cache_payload, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")
                detail = cache_payload
            _apply_content_detail(frame, index, raw_event, detail, status, error, max_input_chars, key)
        except Exception as exc:
            _apply_content_detail(
                frame,
                index,
                raw_event,
                None,
                "fallback_after_error",
                f"{type(exc).__name__}: {exc}",
                max_input_chars,
                key,
            )
    return frame


def _first_available_time(
    publish_time: pd.Timestamp,
    precision: str,
    trading_calendar: Sequence[str] | None,
) -> tuple[pd.Timestamp, str]:
    publish = publish_time.tz_localize(None)
    calendar = tuple(pd.Timestamp(date).normalize() for date in (trading_calendar or ()))
    if precision == "date":
        return (
            _next_session_open(publish.normalize() + timedelta(days=1), calendar),
            "date_only_conservative_next_session",
        )
    if publish.hour >= MARKET_CLOSE_HOUR:
        return (
            _next_session_open(publish.normalize() + timedelta(days=1), calendar),
            "after_market_close_next_session",
        )
    if publish.hour < 9 or (publish.hour == 9 and publish.minute < 30):
        return publish.normalize() + pd.Timedelta(hours=9, minutes=30), "before_open_same_session_open"
    return publish, "observed_intraday_timestamp"


def _next_session_open(start_date: pd.Timestamp, calendar: tuple[pd.Timestamp, ...]) -> pd.Timestamp:
    if calendar:
        for session in calendar:
            if session >= start_date:
                return session + pd.Timedelta(hours=9, minutes=30)
    current = start_date
    while current.weekday() >= 5:
        current += pd.Timedelta(days=1)
    return current + pd.Timedelta(hours=9, minutes=30)


def _symbols(raw: Mapping[str, Any]) -> tuple[str, ...]:
    value = _first(raw, "affected_symbols", "symbols", "symbol", "code", "代码", "股票代码", default="")
    if isinstance(value, (list, tuple, set)):
        items = value
    else:
        items = str(value).replace(";", ",").split(",")
    return tuple(dict.fromkeys(canonicalize_a_share_symbol(item) for item in items if str(item).strip()))


def _tuple_field(raw: Mapping[str, Any], *keys: str) -> tuple[str, ...]:
    value = _first(raw, *keys, default="")
    if isinstance(value, (list, tuple, set)):
        return tuple(str(item) for item in value if str(item).strip())
    return tuple(item.strip() for item in str(value).replace(";", ",").split(",") if item.strip())


def _first(raw: Mapping[str, Any], *keys: str, default: Any = None) -> Any:
    for key in keys:
        if key in raw and not _missing_value(raw[key]) and str(raw[key]).strip():
            return raw[key]
    return default


def _missing_value(value: Any) -> bool:
    if value is None:
        return True
    try:
        return bool(pd.isna(value))
    except (TypeError, ValueError):
        return False


def _quality_flags(raw: Mapping[str, Any], title: Any, content: Any, symbols: tuple[str, ...], publish_raw: Any) -> set[str]:
    flags: set[str] = set()
    if not str(title).strip():
        flags.add("missing_title")
    if not str(content).strip():
        flags.add("missing_content")
    if not symbols:
        flags.add("missing_symbol")
    if publish_raw is None:
        flags.add("missing_publish_time")
    if not _tuple_field(raw, "affected_industries", "industry"):
        flags.add("industry_unavailable")
    return flags


def _retrieve_detail(
    event: Mapping[str, Any],
    *,
    detail_client: Any | None,
    detail_fetcher: Callable[[Mapping[str, Any]], Mapping[str, Any] | str | None] | None,
) -> Mapping[str, Any]:
    if detail_fetcher is not None:
        return _detail_payload(detail_fetcher(event))
    if detail_client is not None:
        for method_name in ("stock_notice_report_detail", "announcement_detail", "stock_announcement_detail"):
            method = getattr(detail_client, method_name, None)
            if callable(method):
                return _detail_payload(method(_detail_identifier(event)))
    url = str(event.get("source_url") or "")
    if url.startswith(("http://", "https://")):
        return _detail_payload(_fetch_url_text(url))
    raise RuntimeError("no announcement detail provider available")


def _detail_identifier(event: Mapping[str, Any]) -> str:
    return str(event.get("source_identifier") or event.get("source_url") or event.get("event_id") or "")


def _detail_payload(value: Mapping[str, Any] | str | None) -> Mapping[str, Any]:
    if value is None:
        return {}
    if isinstance(value, Mapping):
        return dict(value)
    return {"content": str(value), "content_source": "full_text"}


def _fetch_url_text(url: str) -> Mapping[str, Any]:
    request_module = importlib.import_module("urllib." + "request")
    try:
        request = request_module.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with request_module.urlopen(request, timeout=10) as response:
            raw = _bounded_response_read(response)
    except Exception as exc:
        if not _is_certificate_verification_failure(exc):
            raise
        raw = _fetch_url_text_with_requests(url)
    text = raw.decode("utf-8", errors="ignore")
    return {"content": _html_to_text(text), "content_source": "full_text"}


def _fetch_url_text_with_requests(url: str) -> bytes:
    requests_module = importlib.import_module("requests")
    response = requests_module.get(
        url,
        timeout=10,
        headers={"User-Agent": "Mozilla/5.0"},
        stream=True,
        verify=_verified_ca_bundle(),
    )
    response.raise_for_status()
    if hasattr(response, "iter_content"):
        chunks: list[bytes] = []
        total = 0
        for chunk in response.iter_content(chunk_size=65536):
            if not chunk:
                continue
            data = chunk if isinstance(chunk, bytes) else bytes(chunk)
            remaining = MAX_DETAIL_RESPONSE_BYTES - total
            if remaining <= 0:
                break
            chunks.append(data[:remaining])
            total += len(data[:remaining])
            if total >= MAX_DETAIL_RESPONSE_BYTES:
                break
        return b"".join(chunks)
    content = getattr(response, "content", b"")
    if isinstance(content, bytes):
        return content[:MAX_DETAIL_RESPONSE_BYTES]
    text = str(getattr(response, "text", ""))
    return text.encode("utf-8")[:MAX_DETAIL_RESPONSE_BYTES]


def _bounded_response_read(response: Any) -> bytes:
    data = response.read(MAX_DETAIL_RESPONSE_BYTES + 1)
    if not isinstance(data, bytes):
        data = bytes(data)
    return data[:MAX_DETAIL_RESPONSE_BYTES]


def _verified_ca_bundle() -> str | bool:
    try:
        certifi_module = importlib.import_module("certifi")
        return str(certifi_module.where())
    except Exception:
        return True


def _is_certificate_verification_failure(exc: Exception) -> bool:
    return "CERTIFICATE_VERIFY_FAILED" in str(exc) or "certificate verify failed" in str(exc)


def _html_to_text(text: str) -> str:
    without_scripts = re.sub(r"(?is)<(script|style).*?>.*?</\1>", " ", text)
    without_tags = re.sub(r"(?s)<[^>]+>", " ", without_scripts)
    return re.sub(r"&nbsp;|&#160;", " ", without_tags)


def _apply_content_detail(
    frame: pd.DataFrame,
    index: Any,
    event: Mapping[str, Any],
    detail: Mapping[str, Any] | None,
    status: str,
    error: str,
    max_input_chars: int,
    cache_key: str,
) -> None:
    title = str(event.get("title") or "")
    fallback = str(event.get("content") or title)
    detail = detail or {}
    raw_detail = str(
        _first(
            detail,
            "full_text",
            "content",
            "summary",
            "provider_summary",
            "announcement_text",
            default="",
        )
        or ""
    )
    declared_source = str(detail.get("content_source") or ("full_text" if raw_detail else "title_fallback"))
    if declared_source not in BODY_SOURCE_VALUES:
        declared_source = "provider_summary" if raw_detail else "title_fallback"
    if not raw_detail.strip():
        raw_detail = fallback
        declared_source = "title_fallback"
    classification = _classify_announcement_body(title, raw_detail, declared_source=declared_source)
    source = str(classification["content_source"])
    retained_text = str(classification["retained_text"] or fallback or title)
    content = _bounded_announcement_content(title, retained_text, max_input_chars=max_input_chars)
    frame.at[index, "content"] = content
    frame.at[index, "content_source"] = source
    frame.at[index, "content_quality_status"] = classification["content_quality_status"]
    frame.at[index, "content_quality_reason"] = classification["content_quality_reason"]
    frame.at[index, "content_quality_evidence"] = classification["content_quality_evidence"]
    frame.at[index, "content_char_count"] = int(len(content))
    frame.at[index, "content_retrieval_status"] = status if status == "cache_hit" or source != "title_fallback" else ("title_fallback" if not error else status)
    frame.at[index, "content_retrieval_error"] = error
    frame.at[index, "full_text_available"] = source == "full_text" and classification["content_quality_status"] == "usable_full_text"
    frame.at[index, "content_hash"] = _content_hash(content)
    frame.at[index, "content_cache_key"] = cache_key
    frame.at[index, "content_cache_schema_version"] = str(detail.get("content_cache_schema_version") or "legacy_unversioned")
    frame.at[index, "content_classifier_version"] = CONTENT_CLASSIFIER_VERSION
    frame.at[index, "content_truncated"] = len(_normalize_announcement_text(f"{title}\n{retained_text}")) > int(max_input_chars)
    frame.at[index, "max_input_chars"] = int(max_input_chars)
    flags = set(_tuple_field(event, "data_quality_flags"))
    if source == "title_fallback":
        flags.add("content_title_fallback")
    if source == "unavailable":
        flags.add("content_unavailable")
    if classification["content_quality_status"] not in {"usable_full_text", "usable_provider_summary"}:
        flags.add(str(classification["content_quality_reason"]))
    if error:
        flags.add("content_retrieval_failed")
    frame.at[index, "data_quality_flags"] = tuple(sorted(flags))


def _classify_announcement_body(title: str, raw_text: str, *, declared_source: str) -> Mapping[str, Any]:
    source = declared_source if declared_source in BODY_SOURCE_VALUES else "provider_summary"
    normalized_raw = _normalize_whitespace(raw_text)
    title_text = _normalize_announcement_text(title)
    retained_lines, boilerplate_hits = _retained_body_lines(raw_text)
    retained = _normalize_whitespace(" ".join(retained_lines))
    if not retained:
        retained = title_text if title_text else ""
    retained_without_title = _normalize_whitespace(retained.replace(title_text, " ", 1)) if title_text else retained
    evidence = {
        "raw_char_count": len(normalized_raw),
        "retained_char_count": len(retained),
        "retained_without_title_char_count": len(retained_without_title),
        "boilerplate_hit_count": int(boilerplate_hits),
        "boilerplate_dominance": round(float(boilerplate_hits) / max(1, len(_text_lines(raw_text))), 6),
        "body_sentence_count": _body_sentence_count(retained_without_title),
        "body_paragraph_count": _body_paragraph_count(retained_lines),
        "title_duplicate": bool(title_text and retained == title_text),
        "declared_source": source,
        "classifier_version": CONTENT_CLASSIFIER_VERSION,
    }
    if source == "provider_summary":
        if len(retained_without_title) >= 12:
            return _quality_result("usable_provider_summary", "provider_summary_supplied", "provider_summary", retained, evidence)
        return _quality_result("title_fallback", "summary_missing_or_title_only", "title_fallback", title_text, evidence)
    if source == "title_fallback":
        return _quality_result("title_fallback", "title_only_fallback", "title_fallback", title_text, evidence)
    if source == "unavailable" or not normalized_raw:
        return _quality_result("unavailable", "body_unavailable", "unavailable", "", evidence)
    if evidence["boilerplate_dominance"] >= 0.55 or boilerplate_hits >= 8:
        if _looks_body_like(retained_without_title, evidence):
            return _quality_result("usable_full_text", "body_survived_boilerplate_removal", "full_text", retained, evidence)
        return _quality_result("title_fallback", "boilerplate_dominated_page", "title_fallback", title_text, evidence)
    if evidence["title_duplicate"] or len(retained_without_title) < 40:
        return _quality_result("title_fallback", "body_missing_or_title_only", "title_fallback", title_text, evidence)
    if _looks_body_like(retained_without_title, evidence):
        return _quality_result("usable_full_text", "body_like_text_detected", "full_text", retained, evidence)
    return _quality_result("title_fallback", "insufficient_body_structure", "title_fallback", title_text, evidence)


def _quality_result(
    status: str,
    reason: str,
    source: str,
    retained_text: str,
    evidence: Mapping[str, Any],
) -> Mapping[str, Any]:
    return {
        "content_quality_status": status,
        "content_quality_reason": reason,
        "content_quality_evidence": dict(evidence),
        "content_source": source,
        "retained_text": retained_text,
    }


def _looks_body_like(text: str, evidence: Mapping[str, Any]) -> bool:
    if len(text) >= 120 and int(evidence["body_sentence_count"]) >= 1:
        return True
    if len(text) >= 80 and int(evidence["body_sentence_count"]) >= 2:
        return True
    return len(text) >= 80 and int(evidence["body_paragraph_count"]) >= 2


def _retained_body_lines(text: str) -> tuple[tuple[str, ...], int]:
    retained: list[str] = []
    boilerplate_hits = 0
    for line in _text_lines(text):
        normalized = _normalize_whitespace(line)
        if not normalized:
            continue
        hit_count = sum(1 for term in BOILERPLATE_TERMS if term and term in normalized)
        if hit_count:
            boilerplate_hits += hit_count
        if _is_boilerplate_line(normalized, hit_count):
            continue
        retained.append(normalized)
    return tuple(retained), boilerplate_hits


def _is_boilerplate_line(line: str, hit_count: int) -> bool:
    if hit_count >= 2:
        return True
    if hit_count and len(line) <= 48:
        return True
    menu_tokens = sum(1 for token in ("|", ">", ">>", "＞＞", "  ") if token in line)
    if menu_tokens and len(line) <= 80:
        return True
    short_link_like = len(line) <= 20 and not any(mark in line for mark in BODY_LIKE_PUNCTUATION)
    return bool(hit_count and short_link_like)


def _body_sentence_count(text: str) -> int:
    return sum(1 for part in re.split(r"[。！？!?；;]\s*", text) if len(part.strip()) >= 12)


def _body_paragraph_count(lines: Sequence[str]) -> int:
    return sum(1 for line in lines if len(line) >= 24 and any(mark in line for mark in BODY_LIKE_PUNCTUATION))


def _text_lines(text: str) -> tuple[str, ...]:
    return tuple(str(text).replace("\u3000", " ").splitlines())


def _content_source_from_raw(raw: Mapping[str, Any], title: str, content: str) -> str:
    explicit = str(_first(raw, "content_source", default="")).strip()
    if explicit in {"full_text", "provider_summary", "title_fallback"}:
        return explicit
    if not str(content).strip() or str(content).strip() == str(title).strip():
        return "title_fallback"
    return "provider_summary"


def _bounded_announcement_content(title: str, content: str, *, max_input_chars: int) -> str:
    title_text = _normalize_announcement_text(title)
    body = _normalize_announcement_text(content)
    if not body:
        body = title_text
    prefix = f"Title: {title_text}\nContent: "
    budget = max(0, int(max_input_chars) - len(prefix))
    return (prefix + body[:budget]).strip()


def _normalize_announcement_text(text: str) -> str:
    return _normalize_whitespace(" ".join(_retained_body_lines(text)[0]))


def _normalize_whitespace(text: str) -> str:
    return re.sub(r"\s+", " ", str(text).replace("\u3000", " ")).strip()


def _content_hash(content: str) -> str:
    return hashlib.sha256(str(content).encode("utf-8")).hexdigest()


def _content_cache_key(event: Mapping[str, Any], max_input_chars: int) -> str:
    basis = {
        "source_identifier": event.get("source_identifier"),
        "source_url": event.get("source_url"),
        "raw_content_hash": event.get("raw_content_hash"),
        "max_input_chars": int(max_input_chars),
    }
    return hashlib.sha256(json.dumps(basis, ensure_ascii=False, sort_keys=True, default=str).encode("utf-8")).hexdigest()


def _publish_time_precision(value: Any) -> str:
    if value is None:
        return "unavailable"
    text = str(value).strip()
    if not text:
        return "unavailable"
    if ":" in text or ("T" in text and len(text) > 10):
        return "datetime"
    return "date"


def _identifier_from_url(url: str) -> str:
    text = str(url).strip()
    if not text:
        return ""
    return text.rstrip("/").split("/")[-1]


def _symbol_coverage_count(events: pd.DataFrame) -> int:
    symbols: set[str] = set()
    for value in events.get("affected_symbols", pd.Series(dtype=object)):
        items = value if isinstance(value, (list, tuple, set)) else str(value).split(",")
        symbols.update(str(item) for item in items if str(item).strip())
    return len(symbols)


def _ingestion_report(
    *,
    start_date: str,
    end_date: str,
    requested_symbol_count: int,
    request_count: int,
    successful_request_count: int,
    failed_request_count: int,
    empty_response_count: int,
    raw_row_count: int,
    matched_row_count: int,
    normalized_event_count: int,
    deduplicated_event_count: int,
    symbol_coverage_count: int,
    errors: tuple[Mapping[str, Any], ...],
    symbol_request_statuses: tuple[Mapping[str, Any], ...],
) -> Mapping[str, Any]:
    if normalized_event_count > 0 and failed_request_count == 0:
        status = "completed"
    elif normalized_event_count > 0:
        status = "partial"
    else:
        status = "failed"
    return {
        "run_status": status,
        "provider": "akshare",
        "request_mode": "stock_individual_notice_report",
        "start_date": str(start_date),
        "end_date": str(end_date),
        "requested_symbol_count": int(requested_symbol_count),
        "request_count": int(request_count),
        "successful_request_count": int(successful_request_count),
        "failed_request_count": int(failed_request_count),
        "empty_response_count": int(empty_response_count),
        "raw_row_count": int(raw_row_count),
        "matched_row_count": int(matched_row_count),
        "normalized_event_count": int(normalized_event_count),
        "deduplicated_event_count": int(deduplicated_event_count),
        "symbol_coverage_count": int(symbol_coverage_count),
        "symbol_request_statuses": tuple(symbol_request_statuses),
        "pit_audit_passed": True,
        "errors": tuple(errors),
        "events_artifact_path": None,
        "no_profitability_claim": True,
    }
